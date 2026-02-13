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
        active_trade BOOLEAN DEFAULT FALSE,
        lang TEXT DEFAULT 'en'
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

async def get_price(symbol="BTC"):
    now = time.time()
    if btc_cache["price"] and now - btc_cache["time"] < 10:
        return btc_cache["price"]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={"X-CMC_PRO_API_KEY": CMC_KEY},
                params={"symbol": symbol, "convert": "USDT"},
            ) as r:
                data = await r.json()
                price = round(float(data["data"][symbol]["quote"]["USDT"]["price"]),2)
                btc_cache["price"] = price
                btc_cache["time"] = now
                return price
    except:
        return 60000.0

# ================= TEXTS =================
STRINGS = {
    "en": {
        "choose_lang":"🌍 Choose your language:",
        "welcome":"<b>👋 Welcome!</b>",
        "dashboard":"<b>💎 Dashboard</b>\n\n💰 Points: <code>{}</code>\n💵 USDT: <code>{:.2f}</code>\n📊 Trades: <code>{}</code>\n🏆 Wins: <code>{}</code>\n🔗 Wallet: <code>{}</code>",
        "trade":"🎲 Start Trade",
        "wallet":"💳 Set Wallet",
        "withdraw":"💸 Withdraw",
        "active_trade":"⚠️ You have an active trade!",
        "low_points":"❌ Not enough points!",
        "monitor":"⏳ Trade Active...\nEntry Price: ${}\nDuration: 60s",
        "win":"✅ WIN!\nPrice: ${}\n+250 Points",
        "loss":"❌ LOSS\nPrice: ${}\n-100 Points",
        "send_wallet":"📌 Send your USDT TRC20 wallet:",
        "wallet_saved":"✅ Wallet saved!",
        "invalid_wallet":"❌ Invalid TRC20 address",
        "withdraw_min":"⚠️ Minimum 10 USDT",
        "withdraw_no_wallet":"⚠️ Set wallet first",
        "withdraw_sent":"✅ Withdrawal request sent",
        "lang_btn":"🌐 Change Language"
    },
    "ar": {
        "choose_lang":"🌍 اختر لغتك:",
        "welcome":"<b>👋 أهلاً بك!</b>",
        "dashboard":"<b>💎 لوحة التحكم</b>\n\n💰 النقاط: <code>{}</code>\n💵 دولار: <code>{:.2f}</code>\n📊 الصفقات: <code>{}</code>\n🏆 الفوز: <code>{}</code>\n🔗 المحفظة: <code>{}</code>",
        "trade":"🎲 بدء المراهنة",
        "wallet":"💳 تعيين المحفظة",
        "withdraw":"💸 سحب",
        "active_trade":"⚠️ لديك صفقة مفتوحة!",
        "low_points":"❌ نقاط غير كافية!",
        "monitor":"⏳ جارٍ المراقبة...\nسعر الدخول: ${}\nالمدة: 60 ثانية",
        "win":"✅ ربح!\nالسعر: ${}\n+250 نقاط",
        "loss":"❌ خسارة\nالسعر: ${}\n-100 نقاط",
        "send_wallet":"📌 أرسل عنوان محفظتك USDT TRC20:",
        "wallet_saved":"✅ تم حفظ المحفظة!",
        "invalid_wallet":"❌ عنوان غير صالح",
        "withdraw_min":"⚠️ الحد الأدنى 10 دولار",
        "withdraw_no_wallet":"⚠️ عيّن المحفظة أولاً",
        "withdraw_sent":"✅ تم إرسال طلب السحب",
        "lang_btn":"🌐 تغيير اللغة"
    }
}

# ================= MENU =================
def main_menu(user):
    uid, points, trades, wins, wallet, active, lang = user
    txt = STRINGS[lang]
    usdt = points/POINTS_PER_USDT
    wallet_display = wallet if wallet else ("Not Set" if lang=="en" else "غير محدد")
    text = txt["dashboard"].format(points, usdt, trades, wins, wallet_display)
    keyboard = [
        [InlineKeyboardButton(txt["trade"], callback_data="trade")],
        [InlineKeyboardButton(txt["wallet"], callback_data="set_wallet"),
         InlineKeyboardButton(txt["withdraw"], callback_data="withdraw")],
        [InlineKeyboardButton(txt["lang_btn"], callback_data="change_lang")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ================= TELEGRAM HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
         InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")]
    ]
    await update.message.reply_text("🌍 Choose your language / اختر اللغة:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    # Language
    if data.startswith("lang_"):
        lang = data.split("_")[1]
        db_query("UPDATE users SET lang=%s WHERE user_id=%s",(lang,uid))
        user = get_user(uid)
        text,kb = main_menu(user)
        await q.edit_message_text(
    STRINGS[lang]["welcome"] + "\n\n" + text,
    reply_markup=kb,
    parse_mode=ParseMode.HTML
)
        return

    lang = user[6] or "en"
    txt = STRINGS[lang]

    # Change language
    if data=="change_lang":
        kb = [[InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
               InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")]]
        await q.edit_message_text(txt["choose_lang"], reply_markup=InlineKeyboardMarkup(kb))
        return

    # Wallet
    if data=="set_wallet":
        context.user_data["await_wallet"]=True
        await q.message.reply_text(txt["send_wallet"])
        return

    # Withdraw
    if data=="withdraw":
        if user[1]<MIN_WITHDRAW_POINTS:
            await q.message.reply_text(txt["withdraw_min"])
            return
        if not user[4]:
            await q.message.reply_text(txt["withdraw_no_wallet"])
            return
        amount = user[1]/POINTS_PER_USDT
        db_query("INSERT INTO withdrawals(user_id,wallet,amount_usdt) VALUES(%s,%s,%s)",(uid,user[4],amount))
        db_query("UPDATE users SET points=0 WHERE user_id=%s",(uid,))
        await context.bot.send_message(ADMIN_ID,f"💸 Withdrawal\nUser: {uid}\nWallet: {user[4]}\nAmount: {amount} USDT")
        await q.message.reply_text(txt["withdraw_sent"])
        return

    # Trade
    if data=="trade":
        if user[5]:
            await q.message.reply_text(txt["active_trade"])
            return
        if user[1]<100:
            await q.message.reply_text(txt["low_points"])
            return
        price = await get_price()
        db_query("UPDATE users SET points=points-100,trades=trades+1,active_trade=TRUE WHERE user_id=%s",(uid,))
        await q.edit_message_text(txt["monitor"].format(price))
        context.job_queue.run_once(finish_trade,60,data={"uid":uid,"start":price,"direction":"up","message":q.message})

async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    uid = job.data["uid"]
    start = job.data["start"]
    message = job.data["message"]
    end = await get_price()
    win = end>start
    if win:
        db_query("UPDATE users SET points=points+250,wins=wins+1 WHERE user_id=%s",(uid,))
    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s",(uid,))
    await message.edit_text(f"{'✅ WIN!' if win else '❌ LOSS'}\nPrice: {end}")
    user = get_user(uid)
    text,kb = main_menu(user)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def handle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_wallet"):
        wallet = update.message.text.strip()
        if not wallet.startswith("T") or len(wallet)<30:
            await update.message.reply_text(STRINGS["en"]["invalid_wallet"])
            return
        db_query("UPDATE users SET wallet=%s WHERE user_id=%s",(wallet,update.effective_user.id))
        context.user_data["await_wallet"]=False
        await update.message.reply_text(STRINGS["en"]["wallet_saved"])

# ================= INIT BOT =================
ptb_app = Application.builder().token(TOKEN).build()
ptb_app.add_handler(CommandHandler("start",start))
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

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT",10000)))