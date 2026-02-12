import os
import time
import aiohttp
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
from psycopg2 import pool

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CMC_KEY = os.getenv("CMC_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

POINTS_PER_USDT = 1000
MIN_WITHDRAW_USDT = 10
MIN_WITHDRAW_POINTS = MIN_WITHDRAW_USDT * POINTS_PER_USDT

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
async def get_btc(symbol="BTC"):
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
                price = round(float(data["data"][symbol]["quote"]["USDT"]["price"]), 2)
                btc_cache["price"] = price
                btc_cache["time"] = now
                return price
    except:
        return 60000.0

# ================= TEXTS =================
STRINGS = {
    "en": {...},  # نفس المحتوى السابق
    "ar": {...}
}

# ================= MENU =================
def main_menu(user):
    uid, points, trades, wins, wallet, active, lang = user
    txt = STRINGS[lang]
    usdt = points / POINTS_PER_USDT
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
ptb_app = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
           InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")]]
    await update.message.reply_text("🌍 Choose your language / اختر اللغة:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    if data.startswith("lang_"):
        lang = data.split("_")[1]
        db_query("UPDATE users SET lang=%s WHERE user_id=%s", (lang, uid))
        user = get_user(uid)
        text, kb = main_menu(user)
        await q.edit_message_text(STRINGS[lang]["welcome"], parse_mode=ParseMode.HTML)
        await q.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    lang = user[6] or "en"
    txt = STRINGS[lang]

    # باقي الوظائف (Trade, Wallet, Withdraw) كما في كودك السابق
    ...

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))

# ================= FASTAPI =================
api = FastAPI()

@api.on_event("startup")
async def startup():
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(f"{RENDER_URL}/{TOKEN}")

@api.post(f"/{TOKEN}")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}

@api.get("/")
async def home():
    return {"status":"Bot Running"}

# ================= RUN =================
if __name__=="__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))