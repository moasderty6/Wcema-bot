import os
import asyncio
import time
import threading
import aiohttp
from flask import Flask, request
from psycopg2 import pool
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# ================= CONFIG =================

TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
CMC_KEY = os.getenv("CMC_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

POINTS_PER_USDT = 1000
MIN_WITHDRAW_POINTS = 10000  # 10 USDT

app = Flask(__name__)

# ================= TEXTS =================

STRINGS = {
    "en": {
        "welcome": "<b>👋 Welcome to TradeBot!</b>",
        "dashboard": "<b>💎 Dashboard</b>\n\n💰 Points: <code>{}</code>\n💵 USDT: <code>{:.2f}</code>\n📊 Trades: <code>{}</code>\n🏆 Wins: <code>{}</code>\n🔗 Wallet: <code>{}</code>",
        "up": "🚀 Up",
        "down": "📉 Down",
        "wallet": "💳 Set Wallet",
        "withdraw": "💸 Withdraw",
        "active": "⚠️ Active trade already!",
        "low": "❌ Not enough points!",
        "monitor": "⏳ Monitoring...\nEntry: ${}",
        "win": "✅ WIN!\nPrice: ${}",
        "loss": "❌ LOSS\nPrice: ${}",
        "min_withdraw": "⚠️ Minimum withdrawal is 10 USDT",
        "no_wallet": "⚠️ Please set wallet first",
        "wallet_saved": "✅ Wallet saved!",
        "invalid_wallet": "❌ Invalid TRC20 address",
    },
    "ar": {
        "welcome": "<b>👋 أهلاً بك في بوت التداول!</b>",
        "dashboard": "<b>💎 لوحة التحكم</b>\n\n💰 النقاط: <code>{}</code>\n💵 دولار: <code>{:.2f}</code>\n📊 الصفقات: <code>{}</code>\n🏆 الفوز: <code>{}</code>\n🔗 المحفظة: <code>{}</code>",
        "up": "🚀 صعود",
        "down": "📉 هبوط",
        "wallet": "💳 تعيين المحفظة",
        "withdraw": "💸 سحب",
        "active": "⚠️ لديك صفقة مفتوحة!",
        "low": "❌ نقاط غير كافية!",
        "monitor": "⏳ جاري المراقبة...\nسعر الدخول: ${}",
        "win": "✅ ربح!\nالسعر: ${}",
        "loss": "❌ خسارة\nالسعر: ${}",
        "min_withdraw": "⚠️ الحد الأدنى للسحب 10 دولار",
        "no_wallet": "⚠️ يرجى تعيين المحفظة",
        "wallet_saved": "✅ تم حفظ المحفظة",
        "invalid_wallet": "❌ عنوان غير صحيح",
    },
}

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
        active_trade BOOLEAN DEFAULT FALSE,
        lang TEXT DEFAULT 'en'
    )
    """)
    db_query("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        wallet TEXT,
        amount FLOAT,
        status TEXT DEFAULT 'pending'
    )
    """)

def get_user(uid):
    user = db_query("SELECT * FROM users WHERE user_id=%s", (uid,), fetch=True)
    if not user:
        db_query("INSERT INTO users (user_id) VALUES (%s)", (uid,))
        return get_user(uid)
    return user

# ================= BTC =================

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
                price = round(float(data["data"]["BTC"]["quote"]["USDT"]["price"]), 2)
                btc_cache["price"] = price
                btc_cache["time"] = now
                return price
    except:
        return 60000.0

# ================= MENU =================

def main_menu(user):
    uid, points, trades, wins, wallet, active, lang = user
    txt = STRINGS[lang]
    usdt = points / POINTS_PER_USDT
    wallet_display = wallet if wallet else "Not Set"

    text = txt["dashboard"].format(points, usdt, trades, wins, wallet_display)

    kb = [
        [InlineKeyboardButton(txt["up"], callback_data="t_up"),
         InlineKeyboardButton(txt["down"], callback_data="t_down")],
        [InlineKeyboardButton(txt["wallet"], callback_data="set_wallet")],
        [InlineKeyboardButton(txt["withdraw"], callback_data="withdraw")]
    ]

    return text, InlineKeyboardMarkup(kb)

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
    txt = STRINGS[user[6]]

    if q.data == "set_wallet":
        context.user_data["await_wallet"] = True
        await q.message.reply_text("Send TRC20 wallet:")
        return

    if q.data == "withdraw":
        if user[1] < MIN_WITHDRAW_POINTS:
            await q.answer(txt["min_withdraw"], show_alert=True)
            return
        if not user[4]:
            await q.answer(txt["no_wallet"], show_alert=True)
            return

        amount = user[1] / POINTS_PER_USDT
        db_query("INSERT INTO withdrawals (user_id,wallet,amount) VALUES (%s,%s,%s)",
                 (uid, user[4], amount))
        db_query("UPDATE users SET points=0 WHERE user_id=%s", (uid,))

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 Withdrawal\nUser: {uid}\nWallet: {user[4]}\nAmount: {amount} USDT"
        )

        await q.answer("Request sent ✅", show_alert=True)
        return

    if q.data.startswith("t_"):
        if user[5]:
            await q.answer(txt["active"], show_alert=True)
            return
        if user[1] < 100:
            await q.answer(txt["low"], show_alert=True)
            return

        price = await get_btc()

        db_query("UPDATE users SET points=points-100,trades=trades+1,active_trade=TRUE WHERE user_id=%s", (uid,))
        await q.edit_message_text(txt["monitor"].format(price), parse_mode=ParseMode.HTML)

        context.job_queue.run_once(finish_trade, 60, data={
            "uid": uid,
            "start": price,
            "dir": "up" if q.data == "t_up" else "down",
            "msg_id": q.message.message_id
        })

async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    user = get_user(data["uid"])
    txt = STRINGS[user[6]]

    end_price = await get_btc()

    win = (data["dir"] == "up" and end_price > data["start"]) or \
          (data["dir"] == "down" and end_price < data["start"])

    if win:
        db_query("UPDATE users SET points=points+250,wins=wins+1 WHERE user_id=%s", (data["uid"],))

    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s", (data["uid"],))

    final_text = txt["win"].format(end_price) if win else txt["loss"].format(end_price)

    await context.bot.edit_message_text(
        chat_id=data["uid"],
        message_id=data["msg_id"],
        text=final_text,
        parse_mode=ParseMode.HTML
    )

    await asyncio.sleep(3)
    user = get_user(data["uid"])
    text, kb = main_menu(user)
    await context.bot.send_message(data["uid"], text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ================= TELEGRAM INIT =================

ptb_app = Application.builder().token(TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))

@app.post(f"/{TOKEN}")
def webhook():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    asyncio.run(ptb_app.process_update(update))
    return "ok", 200

@app.route("/")
def home():
    return "Bot Running", 200

async def init_bot():
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(f"{RENDER_URL}/{TOKEN}")

def start_bot():
    asyncio.run(init_bot())

threading.Thread(target=start_bot).start()