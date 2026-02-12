import os
import asyncio
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = "postgresql://neondb_owner:npg_txJFdgkvBH35@ep-icy-forest-aia1n447-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"
CMC_API_KEY = "fbfc6aef-dab9-4644-8207-046b3cdf69a3"

app = Flask(__name__)

# --- وظائف قاعدة البيانات ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            points INTEGER DEFAULT 1000,
            lang TEXT,
            total_trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

def get_user(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (user_id) VALUES (%s) RETURNING *", (user_id,))
        user = cur.fetchone()
        conn.commit()
    cur.close()
    conn.close()
    return user

def update_user(user_id, points=None, lang=None, win=False, trade=False):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    if lang:
        cur.execute("UPDATE users SET lang = %s WHERE user_id = %s", (lang, user_id))
    if points is not None:
        cur.execute("UPDATE users SET points = %s WHERE user_id = %s", (points, user_id))
    if trade:
        cur.execute("UPDATE users SET total_trades = total_trades + 1 WHERE user_id = %s", (user_id,))
    if win:
        cur.execute("UPDATE users SET wins = wins + 1 WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

# --- نصوص البوت ---
STRINGS = {
    "ar": {
        "welcome": "<b>🌟 Moonbix Pro | Neon DB</b>\n\n🎯 <b>رصيدك:</b> <code>{points}</code>\n📊 <b>الصفقات:</b> <code>{total}</code>\n🏆 <b>الفوز:</b> <code>{wins}</code>",
        "trade_up": "🚀 صعود", "trade_down": "📉 هبوط", "balance_btn": "💰 الرصيد", "lang_btn": "🇺🇸 English",
        "recording": "<b>⌛️ جاري المراقبة...</b>\n🔹 <b>السعر:</b> <code>${price}</code>",
        "win": "<b>✅ ربح! (+150)</b>\n💰 السعر: <code>${price}</code>",
        "loss": "<b>❌ خسارة! (-100)</b>\n🔻 السعر: <code>${price}</code>",
        "up": "صعود 🟢", "down": "هبوط 🔴"
    },
    "en": {
        "welcome": "<b>🌟 Moonbix Pro | Neon DB</b>\n\n🎯 <b>Balance:</b> <code>{points}</code>\n📊 <b>Trades:</b> <code>{total}</code>\n🏆 <b>Wins:</b> <code>{wins}</code>",
        "trade_up": "🚀 Long", "trade_down": "📉 Short", "balance_btn": "💰 Balance", "lang_btn": "🇸🇦 العربية",
        "recording": "<b>⌛️ Monitoring...</b>\n🔹 <b>Entry:</b> <code>${price}</code>",
        "win": "<b>✅ Win! (+150)</b>\n💰 Price: <code>${price}</code>",
        "loss": "<b>❌ Loss! (-100)</b>\n🔻 Price: <code>${price}</code>",
        "up": "UP 🟢", "down": "DOWN 🔴"
    }
}

# --- منطق السعر والبوت ---
ptb_app = Application.builder().token(TOKEN).build()

def get_btc_price():
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {'X-CMC_PRO_API_KEY': CMC_API_KEY}
        res = requests.get(url, headers=headers, params={'symbol': 'BTC', 'convert': 'USDT'}).json()
        return round(float(res['data']['BTC']['quote']['USDT']['price']), 2)
    except: return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user['lang']:
        kb = [[InlineKeyboardButton("العربية 🇸🇦", callback_data='set_lang_ar')],
              [InlineKeyboardButton("English 🇺🇸", callback_data='set_lang_en')]]
        await update.message.reply_text("<b>Choose Language</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else:
        await show_main_menu(update, user['user_id'])

async def show_main_menu(update_or_query, user_id):
    user = get_user(user_id)
    lang = user['lang'] or "en"
    text = STRINGS[lang]["welcome"].format(points=user['points'], total=user['total_trades'], wins=user['wins'])
    kb = [[InlineKeyboardButton(STRINGS[lang]["trade_up"], callback_data='trade_up'),
           InlineKeyboardButton(STRINGS[lang]["trade_down"], callback_data='trade_down')],
          [InlineKeyboardButton(STRINGS[lang]["balance_btn"], callback_data='balance')],
          [InlineKeyboardButton(STRINGS[lang]["lang_btn"], callback_data='change_lang')]]
    
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else:
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); user_id = query.from_user.id; data = query.data
    user = get_user(user_id)

    if data.startswith("set_lang_"):
        update_user(user_id, lang=data.split("_")[2])
        await show_main_menu(query, user_id); return
    
    if data == "change_lang":
        new_lang = "en" if user['lang'] == "ar" else "ar"
        update_user(user_id, lang=new_lang)
        await show_main_menu(query, user_id); return

    lang = user['lang'] or "en"

    if data.startswith("trade_"):
        if user['points'] < 100:
            await query.edit_message_text("❌ Not enough points!"); return
        
        price_start = get_btc_price()
        update_user(user_id, points=user['points']-100, trade=True)
        await query.edit_message_text(STRINGS[lang]["recording"].format(price=f"{price_start:,}"), parse_mode=ParseMode.HTML)
        
        await asyncio.sleep(60)
        
        price_end = get_btc_price()
        win = (data == "trade_up" and price_end > price_start) or (data == "trade_down" and price_end < price_start)
        
        new_balance = user['points'] - 100 + (250 if win else 0)
        update_user(user_id, points=new_balance, win=win)
        
        res_text = STRINGS[lang]["win" if win else "loss"].format(price=f"{price_end:,}")
        await query.edit_message_text(f"{res_text}\n\n🎯 Balance: {new_balance}", parse_mode=ParseMode.HTML)
        await asyncio.sleep(4); await show_main_menu(query, user_id)

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_callbacks))

@app.post(f"/{TOKEN}")
async def respond():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    await ptb_app.process_update(update)
    return "ok"

async def init_bot():
    init_db() # إنشاء الجدول في Neon
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{TOKEN}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_bot())
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
