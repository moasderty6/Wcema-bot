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

# ================= TEXTS (MULTILINGUAL) =================
STRINGS = {
    "en": {
        "welcome": "<b>👋 Welcome to TradeBot!</b>\nChoose your direction and earn points based on BTC price.",
        "dashboard": "<b>💎 Dashboard</b>\n\n💰 Points: <code>{}</code>\n💵 USDT: <code>{:.2f}</code>\n📊 Trades: <code>{}</code>\n🏆 Wins: <code>{}</code>\n🔗 Wallet: <code>{}</code>",
        "btn_up": "🚀 Bullish (Up)",
        "btn_down": "📉 Bearish (Down)",
        "btn_wallet": "💳 Set Wallet",
        "btn_withdraw": "💸 Withdraw",
        "set_wallet_msg": "📌 Please send your <b>USDT TRC20</b> wallet address:",
        "wallet_saved": "✅ Wallet saved successfully!",
        "invalid_wallet": "❌ Invalid TRC20 address. Please try again.",
        "active_trade_err": "⚠️ You already have an active trade!",
        "low_points": "❌ Not enough points (Min 100).",
        "monitoring": "⏳ <b>Trade Active...</b>\n\nEntry Price: <code>${}</code>\nDuration: 60s",
        "win": "✅ <b>PROFIT!</b>\nBTC Price: <code>${}</code>\nYou earned 250 points!",
        "loss": "❌ <b>LOSS</b>\nBTC Price: <code>${}</code>\nBetter luck next time!",
        "withdraw_min": "⚠️ Minimum withdrawal is 10 USDT.",
        "withdraw_no_wallet": "⚠️ Please set your wallet first.",
        "withdraw_sent": "✅ Withdrawal request sent to admin.",
        "choose_lang": "🌍 Please choose your language / اختر اللغة:"
    },
    "ar": {
        "welcome": "<b>👋 أهلاً بك في بوت التداول!</b>\nتوقع اتجاه السعر واربح نقاطاً بناءً على سعر BTC.",
        "dashboard": "<b>💎 لوحة التحكم</b>\n\n💰 النقاط: <code>{}</code>\n💵 دولار: <code>{:.2f}</code>\n📊 الصفقات: <code>{}</code>\n🏆 الانتصارات: <code>{}</code>\n🔗 المحفظة: <code>{}</code>",
        "btn_up": "🚀 صعود",
        "btn_down": "📉 هبوط",
        "btn_wallet": "💳 تعيين المحفظة",
        "btn_withdraw": "💸 سحب الأرباح",
        "set_wallet_msg": "📌 من فضلك أرسل عنوان محفظتك <b>USDT TRC20</b>:",
        "wallet_saved": "✅ تم حفظ المحفظة بنجاح!",
        "invalid_wallet": "❌ عنوان TRC20 غير صحيح. حاول مرة أخرى.",
        "active_trade_err": "⚠️ لديك صفقة مفتوحة بالفعل!",
        "low_points": "❌ لا تملك نقاطاً كافية (الأدنى 100).",
        "monitoring": "⏳ <b>جارٍ المراقبة...</b>\n\nسعر الدخول: <code>${}</code>\nالمدة: 60 ثانية",
        "win": "✅ <b>ربح!</b>\nسعر الإغلاق: <code>${}</code>\nلقد ربحت 250 نقطة!",
        "loss": "❌ <b>خسارة</b>\nسعر الإغلاق: <code>${}</code>\nحظاً أوفق في المرة القادمة!",
        "withdraw_min": "⚠️ الحد الأدنى للسحب هو 10 دولار.",
        "withdraw_no_wallet": "⚠️ يرجى تعيين المحفظة أولاً.",
        "withdraw_sent": "✅ تم إرسال طلب السحب للإدارة.",
        "choose_lang": "🌍 اختر اللغة المفضل لديك:"
    }
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
    # ... بقية الجداول كما هي ...

def get_user(uid):
    user = db_query("SELECT * FROM users WHERE user_id=%s", (uid,), fetch=True)
    if not user:
        db_query("INSERT INTO users (user_id) VALUES (%s)", (uid,))
        return get_user(uid)
    return user

# ================= UTILS =================
async def get_btc():
    # كود الـ API الخاص بك كما هو (يفضل إضافة try/except قوية)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={"X-CMC_PRO_API_KEY": CMC_KEY},
                params={"symbol": "BTC", "convert": "USDT"},
            ) as r:
                data = await r.json()
                return round(float(data["data"]["BTC"]["quote"]["USDT"]["price"]), 2)
    except: return 60000.0 # سعر افتراضي في حال الخطأ

def main_menu(user):
    uid, points, trades, wins, wallet, active, lang = user
    txt = STRINGS[lang]
    usdt = points / POINTS_PER_USDT
    
    display_wallet = wallet if wallet else ("Not Set" if lang == 'en' else "غير محدد")
    text = txt["dashboard"].format(points, usdt, trades, wins, display_wallet)

    keyboard = [
        [InlineKeyboardButton(txt["btn_up"], callback_data="t_up"),
         InlineKeyboardButton(txt["btn_down"], callback_data="t_down")],
        [InlineKeyboardButton(txt["btn_wallet"], callback_data="set_wallet")],
        [InlineKeyboardButton(txt["btn_withdraw"], callback_data="withdraw")],
        [InlineKeyboardButton("🌐 Change Language / تغيير اللغة", callback_data="lang_select")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    kb = [[InlineKeyboardButton("🇺🇸 English", callback_data="setlang_en"),
           InlineKeyboardButton("🇸🇦 العربية", callback_data="setlang_ar")]]
    await update.message.reply_text(STRINGS["en"]["choose_lang"], reply_markup=InlineKeyboardMarkup(kb))

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    user = get_user(uid)
    lang = user[6]
    txt = STRINGS[lang]
    
    if q.data.startswith("setlang_"):
        new_lang = q.data.split("_")[1]
        db_query("UPDATE users SET lang=%s WHERE user_id=%s", (new_lang, uid))
        user = get_user(uid)
        text, kb = main_menu(user)
        await q.edit_message_text(STRINGS[new_lang]["welcome"], reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    if q.data == "lang_select":
        kb = [[InlineKeyboardButton("🇺🇸 English", callback_data="setlang_en"),
               InlineKeyboardButton("🇸🇦 العربية", callback_data="setlang_ar")]]
        await q.edit_message_text(txt["choose_lang"], reply_markup=InlineKeyboardMarkup(kb))
        return

    # Trade logic
    if q.data.startswith("t_"):
        if user[5]: # active_trade
            await q.answer(txt["active_trade_err"], show_alert=True)
            return
        if user[1] < 100:
            await q.answer(txt["low_points"], show_alert=True)
            return

        price = await get_btc()
        db_query("UPDATE users SET points=points-100, trades=trades+1, active_trade=TRUE WHERE user_id=%s", (uid,))
        await q.edit_message_text(txt["monitoring"].format(price), parse_mode=ParseMode.HTML)
        
        context.job_queue.run_once(finish_trade, 60, data={
            "uid": uid, "start": price, "direction": "up" if q.data == "t_up" else "down", "msg_id": q.message.message_id
        })

    # (أكمل بقية الحالات بنفس الطريقة باستخدام txt["key"])
    # ...

async def finish_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    user = get_user(data["uid"])
    lang = user[6]
    txt = STRINGS[lang]
    
    end_price = await get_btc()
    win = (data["direction"] == "up" and end_price > data["start"]) or \
          (data["direction"] == "down" and end_price < data["start"])

    if win:
        db_query("UPDATE users SET points=points+250, wins=wins+1 WHERE user_id=%s", (data["uid"],))
    
    db_query("UPDATE users SET active_trade=FALSE WHERE user_id=%s", (data["uid"],))
    
    final_text = txt["win"].format(end_price) if win else txt["loss"].format(end_price)
    await context.bot.edit_message_text(chat_id=data["uid"], message_id=data["msg_id"], text=final_text, parse_mode=ParseMode.HTML)
    
    await asyncio.sleep(3)
    user = get_user(data["uid"])
    text, kb = main_menu(user)
    await context.bot.send_message(chat_id=data["uid"], text=text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ================= WEBHOOK & INIT =================
# بقية الأكواد الخاصة بـ Flask و ApplicationBuilder تبقى كما هي مع التأكد من تسجيل الـ JobQueue
