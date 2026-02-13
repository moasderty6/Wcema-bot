import os
import time
import asyncio
import aiohttp
import psycopg2
from psycopg2 import pool
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
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
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)

POINTS_PER_USDT = 1000
MIN_WITHDRAW_POINTS = 10 * POINTS_PER_USDT
TRADE_COST = 100
TRADE_REWARD = 250
TRADE_DURATION = 60

# ================= DATABASE SETUP =================
# استخدام ThreadedConnectionPool لضمان استقرار الربط مع FastAPI
db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, DATABASE_URL)

def db_query(query, params=(), fetch=False, fetchall=False):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch: return cur.fetchone()
            if fetchall: return cur.fetchall()
            conn.commit()
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
        active_trade BOOLEAN DEFAULT FALSE,
        awaiting_wallet BOOLEAN DEFAULT FALSE
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

# ================= PRICE FETCHING =================
price_cache = {"price": None, "time": 0}

async def get_price(symbol="BTC"):
    now = time.time()
    if price_cache["price"] and now - price_cache["time"] < 10:
        return price_cache["price"]

    try:
        async with aiohttp.ClientSession() as session:
            headers = {"X-CMC_PRO_API_KEY": CMC_KEY}
            params = {"symbol": symbol, "convert": "USDT"}
            async with session.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest", 
                                   headers=headers, params=params) as r:
                data = await r.json()
                price = round(float(data["data"][symbol]["quote"]["USDT"]["price"]), 2)
                price_cache["price"] = price
                price_cache["time"] = now
                return price
    except Exception as e:
        print(f"Price Error: {e}")
        return 60000.0

# ================= UI DASHBOARD =================
def dashboard(user):
    uid, points, trades, wins, wallet, active, awaiting = user
    usdt = points / POINTS_PER_USDT
    wallet_display = wallet if wallet else "🚫 Not Set"

    text = (
        "<b>💎 Trading Dashboard</b>\n\n"
        f"💰 <b>Points:</b> <code>{points}</code>\n"
        f"💵 <b>Balance:</b> <code>{usdt:.2f} USDT</code>\n"
        "--------------------------\n"
        f"📊 <b>Total Trades:</b> <code>{trades}</code>\n"
        f"🏆 <b>Total Wins:</b> <code>{wins}</code>\n"
        f"🔗 <b>Wallet:</b> <code>{wallet_display}</code>"
    )

    keyboard = [
        [InlineKeyboardButton("📈 UP (Long)", callback_data="trade_up"),
         InlineKeyboardButton("📉 DOWN (Short)", callback_data="trade_down")],
        [InlineKeyboardButton("💳 Set Wallet", callback_data="set_wallet"),
         InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    text, kb = dashboard(user)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    if data == "set_wallet":
        db_query("UPDATE users SET awaiting_wallet=TRUE WHERE user_id=%s", (uid,))
        await q.message.reply_text("📌 <b>Please send your USDT TRC20 address:</b>", parse_mode=ParseMode.HTML)
        await q.answer()
        return

    if data == "withdraw":
        if user[1] < MIN_WITHDRAW_POINTS:
            await q.answer("⚠️ Min withdrawal is 10 USDT!", show_alert=True)
            return
        if not user[4]:
            await q.answer("⚠️ Please set your wallet first!", show_alert=True)
            return

        amount = user[1] / POINTS_PER_USDT
        db_query("INSERT INTO withdrawals(user_id, wallet, amount_usdt) VALUES(%s,%s,%s)", (uid, user[4], amount))
        db_query("UPDATE users SET points=0 WHERE user_id=%s", (uid,))
        
        await context.bot.send_message(ADMIN_ID, f"🔔 <b>New Withdrawal!</b>\nUser: {uid}\nWallet: {user[4]}\nAmount: {amount} USDT", parse_mode=ParseMode.HTML)
        await q.message.reply_text("✅ Withdrawal request sent to admin.")
        await q.answer()
        return

    if data in ["trade_up", "trade_down"]:
        if user[5]: # active_trade
            await q.answer("⚠️ You already have a trade running!", show_alert=True)
            return
        if user[1] < TRADE_COST:
            await q.answer("❌ Not enough points!", show_alert=True)
            return

        direction = "up" if data == "trade_up" else "down"
        entry_price = await get_price()

        db_query("UPDATE users SET points=points-%s, trades=trades+1, active_trade=TRUE WHERE user_id=%s", (TRADE_COST, uid))
        
        await q.edit_message_text(
            f"🚀 <b>Trade Placed!</b>\n\nDirection: {'📈 UP' if direction=='up' else '📉 DOWN'}\n"
            f"Entry Price: <code>${entry_price}</code>\n"
            f"Time Remaining: {TRADE_DURATION}s",
            parse_mode=ParseMode.HTML
        )

        # تشغيل المؤقت لإنهاء الصفقة
        context.job_queue.run_once(finish_trade, TRADE_DURATION, data={
            "uid": uid, "start": entry_price, "direction": direction, "msg_id": q.message.message_id, "chat_id": q.message.chat_id
        })
        await q.answer()

async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job.data
    uid, start_p, direction, msg_id, chat_id = job["uid"], job["start"], job["direction"], job["msg_id"], job["chat_id"]

    end_p = await get_price()
    win = (end_p > start_p and direction == "up") or (end_p < start_p and direction == "down")

    if win:
        db_query("UPDATE users SET points=points+%s, wins=wins+1 WHERE user_id=%s", (TRADE_REWARD, uid))
    
    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s", (uid,))
    
    result_text = "✅ <b>WIN!</b>" if win else "❌ <b>LOSS</b>"
    final_msg = f"{result_text}\n\nEntry: ${start_p}\nExit: ${end_p}"
    
    await context.bot.edit_message_text(final_msg, chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML)
    
    # إرسال لوحة التحكم الجديدة
    user = get_user(uid)
    text, kb = dashboard(user)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def handle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    if user[6]: # awaiting_wallet
        wallet = update.message.text.strip()
        if not wallet.startswith("T") or len(wallet) < 30:
            await update.message.reply_text("❌ Invalid TRC20 address. Try again.")
            return

        db_query("UPDATE users SET wallet=%s, awaiting_wallet=FALSE WHERE user_id=%s", (wallet, uid))
        await update.message.reply_text("✅ Wallet address saved!")
        # إظهار الداشبورد
        text, kb = dashboard(get_user(uid))
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ================= FASTAPI & BOT INIT =================
app = FastAPI()
# إضافة JobQueue هنا مهمة جداً لضمان عمل التداول
ptb_app = ApplicationBuilder().token(TOKEN).build()

@app.on_event("startup")
async def on_startup():
    init_db()
    ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CallbackQueryHandler(handle_buttons))
    ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet))
    
    await ptb_app.initialize()
    await ptb_app.start()
    # تعيين الـ Webhook
    webhook_url = f"{RENDER_URL}/{TOKEN}"
    await ptb_app.bot.set_webhook(webhook_url)
    print(f"Webhook set to: {webhook_url}")

@app.post(f"/{TOKEN}")
async def webhook(req: Request):
    data = await req.json()
    await ptb_app.process_update(Update.de_json(data, ptb_app.bot))
    return "ok"

@app.get("/")
async def home():
    return {"status": "running"}

if __name__ == "__main__":
    import uvicorn
    # بورت الافتراضي 10000 لـ Render
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
