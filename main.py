import os, asyncio, requests, psycopg2
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
DB_URI = "postgresql://neondb_owner:npg_txJFdgkvBH35@ep-icy-forest-aia1n447-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"
CMC_KEY = "fbfc6aef-dab9-4644-8207-046b3cdf69a3"

app = Flask(__name__)

# --- وظائف قاعدة البيانات المستقرة ---
def db_query(query, params=(), fetch=False):
    conn = psycopg2.connect(DB_URI)
    conn.autocommit = True  # حفظ التغييرات فوراً
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if fetch: return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, points INT DEFAULT 1000, 
        lang TEXT, trades INT DEFAULT 0, wins INT DEFAULT 0)''')

def get_user(uid):
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,), fetch=True)
    if not user:
        db_query("INSERT INTO users (user_id) VALUES (%s)", (uid,))
        return (uid, 1000, None, 0, 0)
    return user

# --- النصوص ---
STRINGS = {
    "ar": {
        "menu": "<b>💎 لوحة التحكم</b>\n\n💰 الرصيد: <code>{p}</code>\n📊 الصفقات: <code>{t}</code>\n🏆 الفوز: <code>{w}</code>",
        "up": "🚀 صعود", "down": "📉 هبوط", "bal": "💰 الرصيد", "lng": "🇺🇸 English",
        "wait": "<b>⌛️ جاري المراقبة...</b>\n💰 السعر: <code>${pr}</code>",
        "win": "<b>✅ فوز! (+150)</b>\n💰 <code>${pr}</code>",
        "loss": "<b>❌ خسارة! (-100)</b>\n🔻 <code>${pr}</code>"
    },
    "en": {
        "menu": "<b>💎 Dashboard</b>\n\n💰 Balance: <code>{p}</code>\n📊 Trades: <code>{t}</code>\n🏆 Wins: <code>{w}</code>",
        "up": "🚀 Up", "down": "📉 Down", "bal": "💰 Balance", "lng": "🇸🇦 العربية",
        "wait": "<b>⌛️ Monitoring...</b>\n💰 Entry: <code>${pr}</code>",
        "win": "<b>✅ Win! (+150)</b>\n💰 <code>${pr}</code>",
        "loss": "<b>❌ Loss! (-100)</b>\n🔻 <code>${pr}</code>"
    }
}

def get_btc():
    try:
        r = requests.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest", 
                         headers={'X-CMC_PRO_API_KEY': CMC_KEY}, params={'symbol': 'BTC', 'convert': 'USDT'}).json()
        return round(float(r['data']['BTC']['quote']['USDT']['price']), 2)
    except: return None

async def start(update, context):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user[2]:
        kb = [[InlineKeyboardButton("العربية 🇸🇦", callback_data='l_ar')], [InlineKeyboardButton("English 🇺🇸", callback_data='l_en')]]
        await update.message.reply_text("<b>Choose Language</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else: await show_menu(update, uid)

async def show_menu(upd, uid):
    u = get_user(uid)
    l = u[2] or "en"
    txt = STRINGS[l]["menu"].format(p=u[1], t=u[3], w=u[4])
    kb = [[InlineKeyboardButton(STRINGS[l]["up"], callback_data='t_up'), InlineKeyboardButton(STRINGS[l]["down"], callback_data='t_down')],
          [InlineKeyboardButton(STRINGS[l]["bal"], callback_data='b'), InlineKeyboardButton(STRINGS[l]["lng"], callback_data='c_l')]]
    if isinstance(upd, Update): await upd.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else: await upd.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_cb(update, context):
    q = update.callback_query; await q.answer(); uid = q.from_user.id
    u = get_user(uid); data = q.data

    if data.startswith("l_"):
        db_query("UPDATE users SET lang = %s WHERE user_id = %s", (data.split("_")[1], uid))
        await show_menu(q, uid); return
    
    if data == "c_l":
        db_query("UPDATE users SET lang = %s WHERE user_id = %s", ("en" if u[2] == "ar" else "ar", uid))
        await show_menu(q, uid); return

    l = u[2] or "en"
    if data.startswith("t_"):
        if u[1] < 100: await q.message.reply_text("❌ No Points!"); return
        pr_start = get_btc()
        db_query("UPDATE users SET points = points - 100, trades = trades + 1 WHERE user_id = %s", (uid,))
        await q.edit_message_text(STRINGS[l]["wait"].format(pr=f"{pr_start:,}"), parse_mode=ParseMode.HTML)
        await asyncio.sleep(60)
        pr_end = get_btc()
        win = (data == "t_up" and pr_end > pr_start) or (data == "t_down" and pr_end < pr_start)
        if win: db_query("UPDATE users SET points = points + 250, wins = wins + 1 WHERE user_id = %s", (uid,))
        await q.edit_message_text(STRINGS[l]["win" if win else "loss"].format(pr=f"{pr_end:,}"), parse_mode=ParseMode.HTML)
        await asyncio.sleep(3); await show_menu(q, uid)

ptb_app = Application.builder().token(TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_cb))

@app.post(f"/{TOKEN}")
async def respond():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    await ptb_app.process_update(update)
    return "ok", 200

@app.route('/')
def h(): return "Bot Active", 200

async def init():
    init_db()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init())
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
