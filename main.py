import os
import asyncio
import requests
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
# استخدام رابط الـ Pooler من Neon لأداء أسرع
DB_URI = "postgresql://neondb_owner:npg_txJFdgkvBH35@ep-icy-forest-aia1n447-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"
CMC_KEY = "fbfc6aef-dab9-4644-8207-046b3cdf69a3"

app = Flask(__name__)

# إنشاء مجمع اتصالات (مفتوح دائماً للسرعة)
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DB_URI)
except Exception as e:
    print(f"DB Pool Error: {e}")

def run_query(query, params=(), fetch=False):
    conn = db_pool.getconn()
    conn.autocommit = True # للحفظ الفوري للبيانات
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch: return cur.fetchone()
    finally:
        db_pool.putconn(conn)

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, points INT DEFAULT 1000, 
        lang TEXT, trades INT DEFAULT 0, wins INT DEFAULT 0)''')

def get_user_data(uid):
    user = run_query("SELECT * FROM users WHERE user_id = %s", (uid,), fetch=True)
    if not user:
        run_query("INSERT INTO users (user_id) VALUES (%s)", (uid,))
        return {"user_id": uid, "points": 1000, "lang": None, "trades": 0, "wins": 0}
    return {"user_id": user[0], "points": user[1], "lang": user[2], "trades": user[3], "wins": user[4]}

# نصوص منسقة
STRINGS = {
    "ar": {
        "menu": "<b>💎 لوحة التحكم | Moonbix</b>\n\n💰 الرصيد: <code>{p}</code>\n📊 الصفقات: <code>{t}</code>\n🏆 الفوز: <code>{w}</code>",
        "up": "🚀 صعود", "down": "📉 هبوط", "bal": "💰 الرصيد", "lng": "🇺🇸 English",
        "wait": "<b>⌛️ جاري المراقبة...</b>\n💰 السعر الحالي: <code>${pr}</code>",
        "win": "<b>✅ فوز! (+150)</b>\nالسعر: <code>${pr}</code>",
        "loss": "<b>❌ خسارة! (-100)</b>\nالسعر: <code>${pr}</code>"
    },
    "en": {
        "menu": "<b>💎 Dashboard | Moonbix</b>\n\n💰 Balance: <code>{p}</code>\n📊 Trades: <code>{t}</code>\n🏆 Wins: <code>{w}</code>",
        "up": "🚀 Up", "down": "📉 Down", "bal": "💰 Balance", "lng": "🇸🇦 العربية",
        "wait": "<b>⌛️ Monitoring...</b>\n💰 Current: <code>${pr}</code>",
        "win": "<b>✅ Win! (+150)</b>\nPrice: <code>${pr}</code>",
        "loss": "<b>❌ Loss! (-100)</b>\nPrice: <code>${pr}</code>"
    }
}

ptb_app = Application.builder().token(TOKEN).build()

def get_btc():
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        r = requests.get(url, headers={'X-CMC_PRO_API_KEY': CMC_KEY}, params={'symbol': 'BTC', 'convert': 'USDT'}, timeout=5).json()
        return round(float(r['data']['BTC']['quote']['USDT']['price']), 2)
    except: return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user_data(uid)
    if not user['lang']:
        kb = [[InlineKeyboardButton("العربية 🇸🇦", callback_data='lang_ar')], [InlineKeyboardButton("English 🇺🇸", callback_data='lang_en')]]
        await update.message.reply_text("<b>Choose Language</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else: await show_menu(update, uid)

async def show_menu(upd, uid):
    user = get_user_data(uid)
    l = user['lang'] or "en"
    txt = STRINGS[l]["menu"].format(p=user['points'], t=user['trades'], w=user['wins'])
    kb = [[InlineKeyboardButton(STRINGS[l]["up"], callback_data='t_up'), InlineKeyboardButton(STRINGS[l]["down"], callback_data='t_down')],
          [InlineKeyboardButton(STRINGS[l]["bal"], callback_data='b'), InlineKeyboardButton(STRINGS[l]["lng"], callback_data='c_l')]]
    if isinstance(upd, Update): await upd.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else: await upd.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer() # استجابة فورية للزر لمنع التعليق
    uid = query.from_user.id
    user = get_user_data(uid)
    data = query.data

    if data.startswith("lang_"):
        run_query("UPDATE users SET lang = %s WHERE user_id = %s", (data.split("_")[1], uid))
        await show_menu(query, uid); return
    
    if data == "c_l":
        run_query("UPDATE users SET lang = %s WHERE user_id = %s", ("en" if user['lang'] == "ar" else "ar", uid))
        await show_menu(query, uid); return

    l = user['lang'] or "en"
    if data.startswith("t_"):
        if user['points'] < 100: await query.message.reply_text("❌ No Points!"); return
        
        pr_start = get_btc()
        run_query("UPDATE users SET points = points - 100, trades = trades + 1 WHERE user_id = %s", (uid,))
        await query.edit_message_text(STRINGS[l]["wait"].format(pr=f"{pr_start:,}"), parse_mode=ParseMode.HTML)
        
        await asyncio.sleep(15) # تقليل الوقت للتجربة السريعة (يمكنك اعادتها لـ 60)
        
        pr_end = get_btc()
        is_win = (data == "t_up" and pr_end > pr_start) or (data == "t_down" and pr_end < pr_start)
        if is_win: run_query("UPDATE users SET points = points + 250, wins = wins + 1 WHERE user_id = %s", (uid,))
        
        res = STRINGS[l]["win" if is_win else "loss"].format(pr=f"{pr_end:,}")
        await query.edit_message_text(res, parse_mode=ParseMode.HTML)
        await asyncio.sleep(3); await show_menu(query, uid)
    
    elif data == "b": await query.answer(f"Balance: {user['points']}", show_alert=True)

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))

@app.post(f"/{TOKEN}")
async def respond():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    # تشغيل المعالجة في الخلفية لضمان سرعة رد الويب هوك
    asyncio.create_task(ptb_app.process_update(update))
    return "ok", 200

async def init():
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init())
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
