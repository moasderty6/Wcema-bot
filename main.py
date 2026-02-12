import os
import asyncio
import time
import threading
import aiohttp
import psycopg2
from psycopg2 import pool
from flask import Flask, request
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

# ================= CONFIG =================

TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
CMC_KEY = os.getenv("CMC_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

POINTS_PER_USDT = 1000
MIN_WITHDRAW_USDT = 10
MIN_WITHDRAW_POINTS = MIN_WITHDRAW_USDT * POINTS_PER_USDT

app = Flask(__name__)

# ================= DATABASE =================

db_pool = pool.SimpleConnectionPool(1, 20, DATABASE_URL)

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

btc_cache = {"price": None, "time": 0}

async def get_btc():
    now = time.time()
    if btc_cache["price"] and now - btc_cache["time"] < 10:
        return btc_cache["price"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={"X-CMC_PRO_API_KEY": CMC_KEY},
                params={"symbol": "BTC", "convert": "USDT"},
            ) as r:
                data = await r.json()
                price = round(
                    float(data["data"]["BTC"]["quote"]["USDT"]["price"]), 2
                )
                btc_cache["price"] = price
                btc_cache["time"] = now
                return price
    except:
        return None

# ================= MENU =================

def main_menu(user):
    points = user[1]
    usdt = points / POINTS_PER_USDT

    text = (
        f"<b>💎 Dashboard</b>\n\n"
        f"💰 Points: <code>{points}</code>\n"
        f"💵 USDT: <code>{usdt:.2f}</code>\n"
        f"📊 Trades: <code>{user[2]}</code>\n"
        f"🏆 Wins: <code>{user[3]}</code>\n"
        f"🔗 Wallet: <code>{user[4] or 'Not Set'}</code>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🚀 Up", callback_data="t_up"),
            InlineKeyboardButton("📉 Down", callback_data="t_down"),
        ],
        [InlineKeyboardButton("💳 Set Wallet", callback_data="set_wallet")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
    ]

    return text, InlineKeyboardMarkup(keyboard)

# ================= TRADE =================

async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    uid = job.data["uid"]
    start_price = job.data["start"]
    direction = job.data["direction"]
    message = job.data["message"]

    end_price = await get_btc()
    win = (direction == "up" and end_price > start_price) or \
          (direction == "down" and end_price < start_price)

    if win:
        db_query(
            "UPDATE users SET points=points+250, wins=wins+1 WHERE user_id=%s",
            (uid,),
        )

    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s", (uid,))
    user = get_user(uid)

    await message.edit_text(
        f"{'✅ Win' if win else '❌ Loss'}\nPrice: {end_price}"
    )

    await asyncio.sleep(3)
    text, kb = main_menu(user)
    await message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ================= HANDLERS =================

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

    # Set Wallet
    if data == "set_wallet":
        context.user_data["await_wallet"] = True
        await q.message.reply_text("Send your USDT TRC20 wallet address:")
        return

    # Withdraw
    if data == "withdraw":
        if user[1] < MIN_WITHDRAW_POINTS:
            await q.message.reply_text("Minimum withdrawal is 10 USDT")
            return

        if not user[4]:
            await q.message.reply_text("Please set wallet first")
            return

        amount = user[1] / POINTS_PER_USDT

        db_query(
            "INSERT INTO withdrawals (user_id,wallet,amount_usdt) VALUES (%s,%s,%s)",
            (uid, user[4], amount),
        )

        db_query("UPDATE users SET points=0 WHERE user_id=%s", (uid,))

        await context.bot.send_message(
            ADMIN_ID,
            f"New Withdrawal\nUser: {uid}\nWallet: {user[4]}\nAmount: {amount} USDT",
        )

        await q.message.reply_text("Withdrawal request sent.")
        return

    # Trade
    if data.startswith("t_"):
        if user[5]:
            await q.message.reply_text("You already have active trade.")
            return

        if user[1] < 100:
            await q.message.reply_text("Not enough points.")
            return

        start_price = await get_btc()

        db_query(
            "UPDATE users SET points=points-100,trades=trades+1,active_trade=TRUE WHERE user_id=%s",
            (uid,),
        )

        await q.edit_message_text(f"Monitoring...\nEntry: {start_price}")

        context.job_queue.run_once(
            finish_trade,
            60,
            data={
                "uid": uid,
                "start": start_price,
                "direction": "up" if data == "t_up" else "down",
                "message": q.message,
            },
        )

async def handle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_wallet"):
        wallet = update.message.text.strip()

        if not wallet.startswith("T") or len(wallet) < 30:
            await update.message.reply_text("Invalid TRC20 address")
            return

        db_query(
            "UPDATE users SET wallet=%s WHERE user_id=%s",
            (wallet, update.effective_user.id),
        )

        context.user_data["await_wallet"] = False
        await update.message.reply_text("Wallet saved successfully")

# ================= TELEGRAM INIT =================

ptb_app = Application.builder().token(TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet))

# ================= WEBHOOK =================

@app.post(f"/{TOKEN}")
def webhook():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    asyncio.run(ptb_app.process_update(update))
    return "ok", 200

@app.route("/")
def home():
    return "Bot Running", 200

# ================= START BOT THREAD =================

async def init():
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(f"{RENDER_URL}/{TOKEN}")

def start_bot():
    asyncio.run(init())

threading.Thread(target=start_bot).start()