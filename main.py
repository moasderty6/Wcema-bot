import os
import asyncio
import requests
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

app = Flask(__name__)
users_db = {}

# نصوص منسقة بشكل احترافي
STRINGS = {
    "ar": {
        "welcome": "<b>🌟 مرحباً بك في Moonbix Pro</b>\n\n🎯 <b>رصيدك:</b> <code>{points}</code> نقطة\n📊 <b>الصفقات:</b> <code>{total}</code>\n\n<i>توقع حركة BTC خلال 60 ثانية:</i>",
        "trade_up": "🚀 صعود", "trade_down": "📉 هبوط", "balance_btn": "💰 الرصيد", "lang_btn": "🇺🇸 English",
        "recording": "<b>⌛️ جاري المراقبة...</b>\n\n🔹 <b>اتجاهك:</b> {choice}\n🔹 <b>سعر الدخول:</b> <code>${price}</code>",
        "win": "<b>✅ صفقة ناجحة! (+150)</b>\n💰 السعر: <code>${price}</code>",
        "loss": "<b>❌ صفقة خاسرة! (-100)</b>\n🔻 السعر: <code>${price}</code>",
        "up": "صعود 🟢", "down": "هبوط 🔴"
    },
    "en": {
        "welcome": "<b>🌟 Welcome to Moonbix Pro</b>\n\n🎯 <b>Balance:</b> <code>{points}</code> PTS\n📊 <b>Trades:</b> <code>{total}</code>\n\n<i>Predict BTC in 60s:</i>",
        "trade_up": "🚀 Long", "trade_down": "📉 Short", "balance_btn": "💰 Balance", "lang_btn": "🇸🇦 العربية",
        "recording": "<b>⌛️ Monitoring...</b>\n\n🔹 <b>Direction:</b> {choice}\n🔹 <b>Entry:</b> <code>${price}</code>",
        "win": "<b>✅ Success! (+150)</b>\n💰 Price: <code>${price}</code>",
        "loss": "<b>❌ Failed! (-100)</b>\n🔻 Price: <code>${price}</code>",
        "up": "UP 🟢", "down": "DOWN 🔴"
    }
}

ptb_app = Application.builder().token(TOKEN).build()

def get_btc_price():
    try:
        res = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT", timeout=5).json()
        return float(res['result']['list'][0]['lastPrice'])
    except: return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_db:
        users_db[user_id] = {"points": 1000, "lang": None, "total": 0}
    
    if users_db[user_id]["lang"] is None:
        keyboard = [[InlineKeyboardButton("العربية 🇸🇦", callback_data='set_lang_ar')],
                    [InlineKeyboardButton("English 🇺🇸", callback_data='set_lang_en')]]
        await update.message.reply_text("<b>Choose Language / اختر اللغة</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await show_main_menu(update, user_id)

async def show_main_menu(update_or_query, user_id):
    lang = users_db[user_id]["lang"]
    text = STRINGS[lang]["welcome"].format(points=users_db[user_id]["points"], total=users_db[user_id]["total"])
    keyboard = [[InlineKeyboardButton(STRINGS[lang]["trade_up"], callback_data='trade_up'),
                 InlineKeyboardButton(STRINGS[lang]["trade_down"], callback_data='trade_down')],
                [InlineKeyboardButton(STRINGS[lang]["balance_btn"], callback_data='balance')],
                [InlineKeyboardButton(STRINGS[lang]["lang_btn"], callback_data='change_lang')]]
    
    markup = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await update_or_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); user_id = query.from_user.id; data = query.data
    
    if data.startswith("set_lang_"):
        users_db[user_id]["lang"] = data.split("_")[2]
        await show_main_menu(query, user_id); return
    
    if data == "change_lang":
        users_db[user_id]["lang"] = "en" if users_db[user_id]["lang"] == "ar" else "ar"
        await show_main_menu(query, user_id); return

    lang = users_db[user_id].get("lang", "ar")

    if data.startswith("trade_"):
        choice = data.split("_")[1]
        price_start = get_btc_price()
        if not price_start:
            await query.edit_message_text("Error fetching price!"); return

        users_db[user_id]['points'] -= 100
        users_db[user_id]['total'] += 1
        choice_text = STRINGS[lang]["up"] if choice == "up" else STRINGS[lang]["down"]
        
        await query.edit_message_text(STRINGS[lang]["recording"].format(choice=choice_text, price=f"{price_start:,}"), parse_mode=ParseMode.HTML)
        
        await asyncio.sleep(60) # دقيقة انتظار
        
        price_end = get_btc_price()
        win = (choice == "up" and price_end > price_start) or (choice == "down" and price_end < price_start)
        users_db[user_id]['points'] += 250 if win else 0
        
        result_text = STRINGS[lang]["win" if win else "loss"].format(price=f"{price_end:,}")
        await query.edit_message_text(f"{result_text}\n\n🎯 رصيدك: {users_db[user_id]['points']}", parse_mode=ParseMode.HTML)
        await asyncio.sleep(4)
        await show_main_menu(query, user_id)

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_callbacks))

@app.post(f"/{TOKEN}")
async def respond():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    await ptb_app.process_update(update)
    return "ok"

@app.route('/')
def health(): return "Ready", 200

async def init_bot():
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{TOKEN}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_bot())
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
