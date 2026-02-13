import os
import time
import aiohttp
import psycopg2
from psycopg2 import pool
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
CMC_KEY = os.getenv("CMC_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

POINTS_PER_USDT = 1000
MIN_WITHDRAW_USDT = 10
MIN_WITHDRAW_POINTS = MIN_WITHDRAW_USDT * POINTS_PER_USDT

# ================= FASTAPI =================
app = FastAPI()

# ================= DATABASE =================
db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)

def db_query(query, params=(), fetch=False):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchone() if fetch else None
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

# ================= BTC PRICE =================
price_cache = {"price": None, "time": 0}

async def get_price(symbol="BTC"):
    now = time.time()
    if price_cache["price"] and now - price_cache["time"] < 10:
        return price_cache["price"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={"X-CMC_PRO_API_KEY": CMC_KEY},
                params={"symbol": symbol, "convert": "USDT"},
            ) as r:
                data = await r.json()
                price = round(float(data["data"][symbol]["quote"]["USDT"]["price"]), 2)
                price_cache["price"] = price
                price_cache["time"] = now
                return price
    except:
        return 60000.0

# ================= MENU =================
def main_menu(user):
    uid, points, trades, wins, wallet, active = user
    usdt = points / POINTS_PER_USDT
    wallet_display = wallet if wallet else "Not Set"

    text = (
        "<b>💎 Dashboard</b>\n\n"
        f"💰 Points: <code>{points}</code>\n"
        f"💵 USDT: <code>{usdt:.2f}</code>\n"
        f"📊 Trades: <code>{trades}</code>\n"
        f"🏆 Wins: <code>{wins}</code>\n"
        f"🔗 Wallet: <code>{wallet_display}</code>"
    )

    keyboard = [
        [InlineKeyboardButton("🎲 Start Trade", callback_data="trade")],
        [
            InlineKeyboardButton("💳 Set Wallet", callback_data="set_wallet"),
            InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
        ],
    ]

    return text, InlineKeyboardMarkup(keyboard)

# ================= TELEGRAM HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    text, kb = main_menu(user)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    # ================= SET WALLET =================
    if data == "set_wallet":
        context.user_data["await_wallet"] = True
        await q.message.reply_text("📌 Send your USDT TRC20 wallet:")
        return

    # ================= WITHDRAW =================
    if data == "withdraw":
        if user[1] < MIN_WITHDRAW_POINTS:
            await q.message.reply_text("⚠️ Minimum withdrawal is 10 USDT")
            return

        if not user[4]:
            await q.message.reply_text("⚠️ Please set wallet first")
            return

        amount = user[1] / POINTS_PER_USDT

        db_query(
            "INSERT INTO withdrawals(user_id,wallet,amount_usdt) VALUES(%s,%s,%s)",
            (uid, user[4], amount),
        )

        db_query("UPDATE users SET points=0 WHERE user_id=%s", (uid,))

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 Withdrawal Request\nUser: {uid}\nWallet: {user[4]}\nAmount: {amount} USDT",
        )

        await q.message.reply_text("✅ Withdrawal request sent")
        return

    # ================= TRADE =================
    if data == "trade":
        if user[5]:
            await q.message.reply_text("⚠️ You already have an active trade")
            return

        if user[1] < 100:
            await q.message.reply_text("❌ Not enough points")
            return

        price = await get_price()

        db_query(
            "UPDATE users SET points=points-100, trades=trades+1, active_trade=TRUE WHERE user_id=%s",
            (uid,),
        )

        await q.edit_message_text(
            f"⏳ Trade Started...\nEntry Price: ${price}\nDuration: 60 seconds"
        )

        context.job_queue.run_once(
            finish_trade,
            60,
            data={"uid": uid, "start": price, "message": q.message},
        )

# ================= FINISH TRADE =================
async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    uid = job.data["uid"]
    start_price = job.data["start"]
    message = job.data["message"]

    end_price = await get_price()
    win = end_price > start_price

    if win:
        db_query(
            "UPDATE users SET points=points+250, wins=wins+1 WHERE user_id=%s",
            (uid,),
        )

    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s", (uid,))

    result_text = (
        f"{'✅ WIN!' if win else '❌ LOSS'}\nFinal Price: ${end_price}"
    )

    await message.edit_text(result_text)

    user = get_user(uid)
    text, kb = main_menu(user)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ================= SAVE WALLET =================
async def handle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_wallet"):
        wallet = update.message.text.strip()

        if not wallet.startswith("T") or len(wallet) < 30:
            await update.message.reply_text("❌ Invalid TRC20 address")
            return

        db_query(
            "UPDATE users SET wallet=%s WHERE user_id=%s",
            (wallet, update.effective_user.id),
        )

        context.user_data["await_wallet"] = False
        await update.message.reply_text("✅ Wallet saved")

# ================= INIT BOT =================
ptb_app = Application.builder().token(TOKEN).build()

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet))

@app.on_event("startup")
async def on_startup():
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(f"{RENDER_URL}/{TOKEN}")

@app.post(f"/{TOKEN}")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return "ok"

@app.get("/")
async def home():
    return "Bot Running"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))