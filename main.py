import os
import asyncio
import requests
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

app = Flask(__name__)
users_db = {}

# قاموس النصوص
STRINGS = {
    "ar": {
        "welcome": "مرحباً بك في محاكي Moonbix! 🚀\nرصيدك: {points} نقطة.",
        "trade_up": "📈 صعود", "trade_down": "📉 هبوط", "balance_btn": "💰 رصيدي", "lang_btn": "🌐 Change Language",
        "insufficient": "عذراً، رصيدك أقل من 100 نقطة!",
        "recording": "✅ تم تسجيل توقعك: {choice}\nسعر الدخول: ${price}\n⏳ جاري المراقبة (60 ثانية)...",
        "win": "🎉 مبروك! ربحت.\nالسعر النهائي: ${price}",
        "loss": "❌ خسرت.\nالسعر النهائي: ${price}",
        "up": "صعود", "down": "هبوط"
    },
    "en": {
        "welcome": "Welcome to Moonbix Simulator! 🚀\nBalance: {points} pts.",
        "trade_up": "📈 UP", "trade_down": "📉 DOWN", "balance_btn": "💰 Balance", "lang_btn": "🌐 تغيير اللغة",
        "insufficient": "Not enough points!",
        "recording": "✅ Trade set: {choice}\nEntry: ${price}\n⏳ Waiting 60s...",
        "win": "🎉 You Won!\nFinal Price: ${price}",
        "loss": "❌ You Lost.\nFinal Price: ${price}",
        "up": "UP", "down": "DOWN"
    }
}

# إعداد التطبيق
ptb_app = Application.builder().token(TOKEN).build()

def get_btc_price():
    try:
        res = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT").json()
        return float(res['result']['list'][0]['lastPrice'])
    except: return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_db: users_db[user_id] = {"points": 1000, "lang": None}
    if users_db[user_id]["lang"] is None:
        keyboard = [[InlineKeyboardButton("العربية 🇸🇦", callback_query_data='set_lang_ar')],
                    [InlineKeyboardButton("English 🇺🇸", callback_query_data='set_lang_en')]]
        await update.message.reply_text("Choose Language / اختر اللغة:", reply_markup=InlineKeyboardMarkup(keyboard))
    else: await show_main_menu(update, user_id)

async def show_main_menu(update_or_query, user_id):
    lang = users_db[user_id]["lang"]; points = users_db[user_id]["points"]
    text = STRINGS[lang]["welcome"].format(points=points)
    keyboard = [[InlineKeyboardButton(STRINGS[lang]["trade_up"], callback_query_data='trade_up')],
                [InlineKeyboardButton(STRINGS[lang]["trade_down"], callback_query_data='trade_down')],
                [InlineKeyboardButton(STRINGS[lang]["balance_btn"], callback_query_data='balance')],
                [InlineKeyboardButton(STRINGS[lang]["lang_btn"], callback_query_data='change_lang')]]
    markup = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, Update): await update_or_query.message.reply_text(text, reply_markup=markup)
    else: await update_or_query.edit_message_text(text, reply_markup=markup)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); user_id = query.from_user.id; data = query.data
    if data.startswith("set_lang_"):
        users_db[user_id]["lang"] = data.split("_")[2]; await show_main_menu(query, user_id); return
    if data == "change_lang":
        users_db[user_id]["lang"] = "en" if users_db[user_id]["lang"] == "ar" else "ar"
        await show_main_menu(query, user_id); return
    lang = users_db[user_id].get("lang", "en")
    if data.startswith("trade_"):
        choice = data.split("_")[1]
        if users_db[user_id]['points'] < 100:
            await query.edit_message_text(STRINGS[lang]["insufficient"]); return
        price_start = get_btc_price()
        users_db[user_id]['points'] -= 100
        choice_text = STRINGS[lang]["up"] if choice == "up" else STRINGS[lang]["down"]
        await query.edit_message_text(STRINGS[lang]["recording"].format(choice=choice_text, price=f"{price_start:,}"))
        await asyncio.sleep(60)
        price_end = get_btc_price()
        win = (choice == "up" and price_end > price_start) or (choice == "down" and price_end < price_start)
        users_db[user_id]['points'] += 250 if win else 0
        result = STRINGS[lang]["win" if win else "loss"].format(price=f"{price_end:,}")
        await query.edit_message_text(f"{result}\nPoints: {users_db[user_id]['points']}")
        await asyncio.sleep(3); await show_main_menu(query, user_id)
    elif data == "balance":
        await query.answer(f"Points: {users_db[user_id]['points']}", show_alert=True)

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_callbacks))

# --- الجزء الأهم لإصلاح الأخطاء ---
@app.post(f"/{TOKEN}")
async def respond():
    # تحويل الـ JSON القادم من تيليجرام إلى كائن Update
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    # معالجة التحديث
    await ptb_app.process_update(update)
    return "ok"

@app.route('/')
def health(): return "Bot is Online!", 200

async def init_bot():
    # هذه الخطوات هي التي تحل خطأ RuntimeError: This Application was not initialized
    await ptb_app.initialize()
    await ptb_app.start()
    webhook_url = f"{RENDER_EXTERNAL_URL}/{TOKEN}"
    await ptb_app.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to: {webhook_url}")

if __name__ == "__main__":
    # تشغيل التهيئة ثم Flask
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_bot())
    
    port = int(os.environ.get("PORT", 10000))
    # تثبيت Flask مع [async] مطلوب في requirements
    app.run(host='0.0.0.0', port=port)
