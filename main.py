import os
import asyncio
import requests
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# تحميل الإعدادات
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL") # رابط الخدمة من Render

# إعداد Flask
app = Flask(__name__)

# قاعدة بيانات مؤقتة
users_db = {}

STRINGS = {
    "ar": {
        "welcome": "مرحباً بك في محاكي Moonbix! 🚀\nرصيدك: {points} نقطة.\nتوقع اتجاه BTC خلال 60 ثانية:",
        "trade_up": "📈 صعود", "trade_down": "📉 هبوط", "balance_btn": "💰 رصيدي", "lang_btn": "🌐 Change Language",
        "insufficient": "عذراً، رصيدك أقل من 100 نقطة!",
        "recording": "✅ تم تسجيل توقعك: {choice}\nسعر الدخول: ${price}\n⏳ جاري المراقبة (60 ثانية)...",
        "win": "🎉 مبروك! ربحت التحدي.\nالسعر النهائي: ${price}\nرصيدك الجديد: {points}",
        "loss": "❌ للأسف، خسرت التحدي.\nالسعر النهائي: ${price}\nرصيدك الحالي: {points}",
        "up": "صعود", "down": "هبوط"
    },
    "en": {
        "welcome": "Welcome to Moonbix Simulator! 🚀\nBalance: {points} points.\nPredict BTC direction in 60s:",
        "trade_up": "📈 UP", "trade_down": "📉 DOWN", "balance_btn": "💰 Balance", "lang_btn": "🌐 تغيير اللغة",
        "insufficient": "Sorry, you need at least 100 points!",
        "recording": "✅ Trade recorded: {choice}\nEntry Price: ${price}\n⏳ Monitoring (60s)...",
        "win": "🎉 Congrats! You won.\nFinal Price: ${price}\nNew Balance: {points}",
        "loss": "❌ Hard luck, you lost.\nFinal Price: ${price}\nBalance: {points}",
        "up": "UP", "down": "DOWN"
    }
}

# إعداد تطبيق البوت
ptb_app = Application.builder().token(TOKEN).build()

# وظائف البوت (نفس الوظائف السابقة)
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
    if isinstance(update_or_query, Update): await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else: await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); user_id = query.from_user.id; data = query.data
    if data.startswith("set_lang_"):
        users_db[user_id]["lang"] = data.split("_")[2]; await show_main_menu(query, user_id); return
    if data == "change_lang":
        users_db[user_id]["lang"] = "en" if users_db[user_id]["lang"] == "ar" else "ar"
        await show_main_menu(query, user_id); return
    lang = users_db[user_id]["lang"]
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
        if win:
            users_db[user_id]['points'] += 250
            result = STRINGS[lang]["win"].format(price=f"{price_end:,}", points=users_db[user_id]['points'])
        else: result = STRINGS[lang]["loss"].format(price=f"{price_end:,}", points=users_db[user_id]['points'])
        await query.edit_message_text(result)
        await asyncio.sleep(3); await show_main_menu(query, user_id)
    elif data == "balance":
        msg = "رصيدك: " if lang == "ar" else "Balance: "
        await query.answer(f"{msg}{users_db[user_id]['points']}", show_alert=True)

# أضف المعالجات (Handlers)
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(handle_callbacks))

# --- مسارات Flask للـ Webhook ---
@app.route(f'/{TOKEN}', methods=['POST'])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), ptb_app.bot)
        await ptb_app.process_update(update)
        return "ok", 200

@app.route('/')
def index(): return "Webhook is active!", 200

async def setup_webhook():
    webhook_url = f"{RENDER_EXTERNAL_URL}/{TOKEN}"
    await ptb_app.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to: {webhook_url}")

if __name__ == "__main__":
    # تشغيل تهيئة الويب هوك ثم سيرفر Flask
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_webhook())
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
