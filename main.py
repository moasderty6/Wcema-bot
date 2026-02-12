import os, asyncio, time, aiohttp
import psycopg2
from psycopg2 import pool
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # ضع ايديك هنا

DB_URI = os.getenv("DATABASE_URL")
CMC_KEY = os.getenv("CMC_KEY")

POINTS_PER_USDT = 1000
MIN_WITHDRAW_USDT = 10
MIN_WITHDRAW_POINTS = MIN_WITHDRAW_USDT * POINTS_PER_USDT

app = Flask(__name__)

# -------------------- DATABASE POOL --------------------

db_pool = pool.SimpleConnectionPool(1, 20, DB_URI)

def db_query(query, params=(), fetch=False, fetchall=False):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        result = None
        if fetch:
            result = cur.fetchone()
        if fetchall:
            result = cur.fetchall()
        conn.commit()
        cur.close()
        return result
    finally:
        db_pool.putconn(conn)

def init_db():
    db_query("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        points INT DEFAULT 1000,
        lang TEXT DEFAULT 'en',
        trades INT DEFAULT 0,
        wins INT DEFAULT 0,
        wallet TEXT,
        active_trade BOOLEAN DEFAULT FALSE
    )
    """)
    
    db_query("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        wallet TEXT,
        amount_usdt FLOAT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

def get_user(uid):
    user = db_query("SELECT * FROM users WHERE user_id=%s", (uid,), fetch=True)
    if not user:
        db_query("INSERT INTO users (user_id) VALUES (%s)", (uid,))
        return get_user(uid)
    return user

# -------------------- BTC PRICE --------------------

btc_cache = {"price": None, "time": 0}

async def get_btc():
    now = time.time()
    if btc_cache["price"] and now - btc_cache["time"] < 10:
        return btc_cache["price"]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={'X-CMC_PRO_API_KEY': CMC_KEY},
                params={'symbol': 'BTC', 'convert': 'USDT'}
            ) as r:
                data = await r.json()
                price = round(float(data['data']['BTC']['quote']['USDT']['price']), 2)
                btc_cache["price"] = price
                btc_cache["time"] = now
                return price
    except:
        return None

# -------------------- UI --------------------

def main_menu(user):
    points = user[1]
    usdt = points / POINTS_PER_USDT
    
    text = (
        f"<b>💎 Dashboard</b>\n\n"
        f"💰 Points: <code>{points}</code>\n"
        f"💵 USDT: <code>{usdt:.2f}</code>\n"
        f"📊 Trades: <code>{user[3]}</code>\n"
        f"🏆 Wins: <code>{user[4]}</code>\n"
        f"🔗 Wallet: <code>{user[5] or 'Not Set'}</code>"
    )

    kb = [
        [InlineKeyboardButton("🚀 Up", callback_data="t_up"),
         InlineKeyboardButton("📉 Down", callback_data="t_down")],
        [InlineKeyboardButton("💳 Set Wallet", callback_data="set_wallet")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    return text, InlineKeyboardMarkup(kb)

# -------------------- TRADE FINISH --------------------

async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    uid = job.data["uid"]
    start_price = job.data["start"]
    direction = job.data["direction"]
    message = job.data["msg"]

    end_price = await get_btc()
    win = (direction == "up" and end_price > start_price) or \
          (direction == "down" and end_price < start_price)

    if win:
        db_query("UPDATE users SET points=points+250, wins=wins+1 WHERE user_id=%s", (uid,))

    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s", (uid,))
    user = get_user(uid)

    await message.edit_text(
        f"{'✅ Win' if win else '❌ Loss'}\nPrice: {end_price}",
        parse_mode=ParseMode.HTML
    )

    await asyncio.sleep(3)
    text, kb = main_menu(user)
    await message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# -------------------- HANDLERS --------------------

async def start(update, context):
    uid = update.effective_user.id
    user = get_user(uid)
    text, kb = main_menu(user)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def handle_cb(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    # -------- SET WALLET --------
    if data == "set_wallet":
        await q.message.reply_text("Send your USDT TRC20 wallet address:")
        context.user_data["await_wallet"] = True
        return

    # -------- WITHDRAW --------
    if data == "withdraw":
        if user[1] < MIN_WITHDRAW_POINTS:
            await q.message.reply_text("❌ Minimum withdrawal is 10 USDT")
            return
        if not user[5]:
            await q.message.reply_text("❌ Please set wallet first")
            return

        amount = user[1] / POINTS_PER_USDT

        db_query("""
        INSERT INTO withdrawals (user_id, wallet, amount_usdt)
        VALUES (%s,%s,%s)
        """, (uid, user[5], amount))

        db_query("UPDATE users SET points=0 WHERE user_id=%s", (uid,))

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 New Withdrawal\nUser: {uid}\nWallet: {user[5]}\nAmount: {amount} USDT"
        )

        await q.message.reply_text("✅ Withdrawal request sent.")
        return

    # -------- TRADE --------
    if data.startswith("t_"):
        if user[6]:
            await q.message.reply_text("⚠️ You already have active trade.")
            return

        if user[1] < 100:
            await q.message.reply_text("❌ Not enough points")
            return

        start_price = await get_btc()
        db_query("""
        UPDATE users SET points=points-100, trades=trades+1, active_trade=TRUE
        WHERE user_id=%s
        """, (uid,))

        await q.edit_message_text(f"⌛ Monitoring...\nEntry: {start_price}")

        context.job_queue.run_once(
            finish_trade,
            60,
            data={
                "uid": uid,
                "start": start_price,
                "direction": "up" if data=="t_up" else "down",
                "msg": q.message
            }
        )

async def handle_message(update, context):
    if context.user_data.get("await_wallet"):
        wallet = update.message.text.strip()
        if not wallet.startswith("T") or len(wallet) < 30:
            await update.message.reply_text("❌ Invalid TRC20 address")
            return

        db_query("UPDATE users SET wallet=%s WHERE user_id=%s",
                 (wallet, update.effective_user.id))
        context.user_data["await_wallet"] = False
        await update.message.reply_text("✅ Wallet saved successfully")

# -------------------- INIT --------------------

ptb_app = Application.builder().token(TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))
ptb_app.add_handler(CommandHandler("wallet", handle_message))
ptb_app.add_handler(CommandHandler("message", handle_message))

@app.post(f"/{TOKEN}")
async def respond():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    await ptb_app.process_update(update)
    return "ok"

@app.route('/')
def home():
    return "Bot Running"

async def init():
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(f"{RENDER_URL}/{TOKEN}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))