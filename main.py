import os
import time
import asyncio
import aiohttp
import logging
from contextlib import asynccontextmanager
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CMC_KEY = os.getenv("CMC_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
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
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None
    finally:
        db_pool.putconn(conn)

def init_db():
    # تحديث الجدول لإضافة الأعمدة الناقصة إذا لم تكن موجودة
    db_query("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, points INT DEFAULT 1000, trades INT DEFAULT 0, wins INT DEFAULT 0, wallet TEXT, active_trade BOOLEAN DEFAULT FALSE, lang TEXT DEFAULT 'en')")
    # التأكد من وجود الأعمدة يدوياً (في حال كان الجدول قديماً)
    try:
        db_query("ALTER TABLE users ADD COLUMN IF NOT EXISTS active_trade BOOLEAN DEFAULT FALSE")
        db_query("ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT DEFAULT 'en'")
    except: pass
    
    db_query("CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, user_id BIGINT, wallet TEXT, amount_usdt FLOAT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

def get_user(uid):
    user = db_query("SELECT user_id, points, trades, wins, wallet, active_trade, lang FROM users WHERE user_id=%s", (uid,), fetch=True)
    if not user:
        db_query("INSERT INTO users (user_id) VALUES (%s)", (uid,))
        return get_user(uid)
    return user

# ================= BTC PRICE =================
btc_cache = {"price": None, "time": 0}
async def get_btc(symbol="BTC"):
    now = time.time()
    if btc_cache["price"] and now - btc_cache["time"] < 10: return btc_cache["price"]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={"X-CMC_PRO_API_KEY": CMC_KEY}, params={"symbol": symbol, "convert": "USDT"}) as r:
                data = await r.json()
                price = round(float(data["data"][symbol]["quote"]["USDT"]["price"]), 2)
                btc_cache["price"] = price
                btc_cache["time"] = now
                return price
    except: return 60000.0

# ================= TEXTS =================
STRINGS = {
    "en": {
        "choose_lang": "🌍 Choose language:", "welcome": "<b>👋 Welcome!</b>",
        "dashboard": "<b>💎 Dashboard</b>\n\n💰 Points: <code>{}</code>\n💵 USDT: <code>{:.2f}</code>\n📊 Trades: <code>{}</code>\n🏆 Wins: <code>{}</code>\n🔗 Wallet: <code>{}</code>",
        "trade": "🎲 Start Trade", "wallet": "💳 Set Wallet", "withdraw": "💸 Withdraw",
        "active_trade": "⚠️ Active trade!", "low_points": "❌ No points!",
        "monitor": "⏳ Monitoring...\nPrice: ${}\nTime: 60s", "win": "✅ WIN!\nPrice: ${}\n+250", "loss": "❌ LOSS\nPrice: ${}\n-100",
        "send_wallet": "📌 Send USDT TRC20:", "wallet_saved": "✅ Saved!", "invalid_wallet": "❌ Invalid",
        "withdraw_min": "⚠️ Min 10 USDT", "withdraw_no_wallet": "⚠️ Set wallet", "withdraw_sent": "✅ Sent", "lang_btn": "🌐 Language",
    },
    "ar": {
        "choose_lang": "🌍 اختر لغتك:", "welcome": "<b>👋 أهلاً بك!</b>",
        "dashboard": "<b>💎 لوحة التحكم</b>\n\n💰 النقاط: <code>{}</code>\n💵 دولار: <code>{:.2f}</code>\n📊 الصفقات: <code>{}</code>\n🏆 الفوز: <code>{}</code>\n🔗 المحفظة: <code>{}</code>",
        "trade": "🎲 بدء المراهنة", "wallet": "💳 تعيين المحفظة", "withdraw": "💸 سحب",
        "active_trade": "⚠️ لديك صفقة مفتوحة!", "low_points": "❌ نقاط غير كافية!",
        "monitor": "⏳ مراقبة...\nالسعر: ${}\nالمدة: 60ث", "win": "✅ ربح!\nالسعر: ${}\n+250", "loss": "❌ خسارة\nالسعر: ${}\n-100",
        "send_wallet": "📌 أرسل محفظة USDT TRC20:", "wallet_saved": "✅ تم الحفظ!", "invalid_wallet": "❌ خطأ",
        "withdraw_min": "⚠️ الحد الأدنى 10$", "withdraw_no_wallet": "⚠️ عين المحفظة", "withdraw_sent": "✅ تم الطلب", "lang_btn": "🌐 تغيير اللغة",
    }
}

# ================= MENU =================
def main_menu(user):
    # حل مشكلة الـ Unpack: نأخذ أول 7 قيم فقط ونضع قيم افتراضية إذا نقصت
    uid = user[0]
    points = user[1] if len(user) > 1 else 1000
    trades = user[2] if len(user) > 2 else 0
    wins = user[3] if len(user) > 3 else 0
    wallet = user[4] if len(user) > 4 else None
    active_trade = user[5] if len(user) > 5 else False
    lang = user[6] if len(user) > 6 else 'en'
    
    if lang not in STRINGS: lang = "en"
    txt = STRINGS[lang]
    usdt = points / POINTS_PER_USDT
    w_display = wallet if wallet else ("Not Set" if lang=="en" else "غير محدد")
    text = txt["dashboard"].format(points, usdt, trades, wins, w_display)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(txt["trade"], callback_data="trade")],
        [InlineKeyboardButton(txt["wallet"], callback_data="set_wallet"), InlineKeyboardButton(txt["withdraw"], callback_data="withdraw")],
        [InlineKeyboardButton(txt["lang_btn"], callback_data="change_lang")]
    ])
    return text, kb

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"), InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")]])
    await update.message.reply_text("🌍 Choose language / اختر اللغة:", reply_markup=kb)

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    
    if q.data.startswith("lang_"):
        l_code = q.data.split("_")[1]
        db_query("UPDATE users SET lang=%s WHERE user_id=%s", (l_code, uid))
        user = get_user(uid)
        text, kb = main_menu(user)
        await q.edit_message_text(STRINGS[l_code]["welcome"], parse_mode=ParseMode.HTML)
        await q.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    user = get_user(uid)
    lang = user[6] if len(user) > 6 and user[6] else "en"
    txt = STRINGS.get(lang, STRINGS["en"])

    if q.data == "trade":
        if len(user) > 5 and user[5]: # active_trade
            await q.message.reply_text(txt["active_trade"])
            return
        price = await get_btc()
        db_query("UPDATE users SET points=points-100, trades=trades+1, active_trade=TRUE WHERE user_id=%s", (uid,))
        await q.edit_message_text(txt["monitor"].format(price))
        context.job_queue.run_once(finish_trade, 60, data={"uid":uid,"start":price,"chat_id":q.message.chat_id,"msg_id":q.message.message_id})
    
    elif q.data == "set_wallet":
        context.user_data["await_wallet"] = True
        await q.message.reply_text(txt["send_wallet"])
    
    elif q.data == "change_lang":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"), InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")]])
        await q.edit_message_text(txt["choose_lang"], reply_markup=kb)

async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    end_p = await get_btc()
    win = end_p > job.data["start"]
    uid = job.data["uid"]
    if win: db_query("UPDATE users SET points=points+250, wins=wins+1 WHERE user_id=%s", (uid,))
    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s", (uid,))
    await context.bot.send_message(job.data["chat_id"], "✅ WIN!" if win else "❌ LOSS")
    user = get_user(uid)
    text, kb = main_menu(user)
    await context.bot.send_message(job.data["chat_id"], text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def handle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_wallet"):
        wallet = update.message.text.strip()
        db_query("UPDATE users SET wallet=%s WHERE user_id=%s", (wallet, update.effective_user.id))
        context.user_data["await_wallet"] = False
        await update.message.reply_text("✅ Saved!")

# ================= FASTAPI SETUP =================
ptb_app = Application.builder().token(TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet))

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(f"{RENDER_URL}/{TOKEN}")
    yield
    await ptb_app.stop()
    await ptb_app.shutdown()

api = FastAPI(lifespan=lifespan)
@api.post(f"/{TOKEN}")
async def web_h(request: Request):
    data = await request.json()
    await ptb_app.process_update(Update.de_json(data, ptb_app.bot))
    return "ok"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
