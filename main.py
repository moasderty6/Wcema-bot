import os
import asyncio
import requests
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- إعداد سيرفر وهمي لإرضاء Render ---
server = Flask(__name__)

@server.route('/')
def health_check():
    return "Bot is Alive!", 200

def run_flask():
    # Render يرسل المنفذ عبر متغير البيئة PORT
    port = int(os.environ.get("PORT", 10000))
    server.run(host='0.0.0.0', port=port)

# --- إعدادات البوت والبيانات ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# قاعدة بيانات مؤقتة (تضيع عند إعادة التشغيل)
users_db = {}

STRINGS = {
    "ar": {
        "welcome": "مرحباً بك في محاكي Moonbix! 🚀\nرصيدك: {points} نقطة.\nتوقع اتجاه BTC خلال 60 ثانية:",
        "trade_up": "📈 صعود",
        "trade_down": "📉 هبوط",
        "balance_btn": "💰 رصيدي",
        "lang_btn": "🌐 Change Language",
        "insufficient": "عذراً، رصيدك أقل من 100 نقطة!",
        "recording": "✅ تم تسجيل توقعك: {choice}\nسعر الدخول: ${price}\n⏳ جاري المراقبة (60 ثانية)...",
        "win": "🎉 مبروك! ربحت التحدي.\nالسعر النهائي: ${price}\nرصيدك الجديد: {points}",
        "loss": "❌ للأسف، خسرت التحدي.\nالسعر النهائي: ${price}\nرصيدك الحالي: {points}",
        "up": "صعود",
        "down": "هبوط"
    },
    "en": {
        "welcome": "Welcome to Moonbix Simulator! 🚀\nBalance: {points} points.\nPredict BTC direction in 60s:",
        "trade_up": "📈 UP",
        "trade_down": "📉 DOWN",
        "balance_btn": "💰 Balance",
        "lang_btn": "🌐 تغيير اللغة",
        "insufficient": "Sorry, you need at least 100 points!",
        "recording": "✅ Trade recorded: {choice}\nEntry Price: ${price}\n⏳ Monitoring (60s)...",
        "win": "🎉 Congrats! You won.\nFinal Price: ${price}\nNew Balance: {points}",
        "loss": "❌ Hard luck, you lost.\nFinal Price: ${price}\nBalance: {points}",
        "up": "UP",
        "down": "DOWN"
    }
}

def get_btc_price():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT"
        res = requests.get(url).json()
        return float(res['result']['list'][0]['lastPrice'])
    except:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_db:
        users_db[user_id] = {"points": 1000, "lang": None}
    
    if users_db[user_id]["lang"] is None:
        keyboard = [
            [InlineKeyboardButton("العربية 🇸🇦", callback_query_data='set_lang_ar')],
            [InlineKeyboardButton("English 🇺🇸", callback_query_data='set_lang_en')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose Language / اختر اللغة:", reply_markup=reply_markup)
    else:
        await show_main_menu(update, user_id)

async def show_main_menu(update_or_query, user_id):
    lang = users_db[user_id]["lang"]
    points = users_db[user_id]["points"]
    text = STRINGS[lang]["welcome"].format(points=points)
    
    keyboard = [
        [InlineKeyboardButton(STRINGS[lang]["trade_up"], callback_query_data='trade_up')],
        [InlineKeyboardButton(STRINGS[lang]["trade_down"], callback_query_data='trade_down')],
        [InlineKeyboardButton(STRINGS[lang]["balance_btn"], callback_query_data='balance')],
        [InlineKeyboardButton(STRINGS[lang]["lang_btn"], callback_query_data='change_lang')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update_or_query.edit_message_text(text, reply_markup=reply_markup)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("set_lang_"):
        users_db[user_id]["lang"] = data.split("_")[2]
        await show_main_menu(query, user_id)
        return

    if data == "change_lang":
        users_db[user_id]["lang"] = "en" if users_db[user_id]["lang"] == "ar" else "ar"
        await show_main_menu(query, user_id)
        return

    lang = users_db[user_id]["lang"]

    if data.startswith("trade_"):
        choice = data.split("_")[1]
        if users_db[user_id]['points'] < 100:
            await query.edit_message_text(STRINGS[lang]["insufficient"])
            return

        price_start = get_btc_price()
        if not price_start:
            await query.edit_message_text("Error fetching price. Try again.")
            return

        users_db[user_id]['points'] -= 100
        choice_text = STRINGS[lang]["up"] if choice == "up" else STRINGS[lang]["down"]
        
        await query.edit_message_text(STRINGS[lang]["recording"].format(choice=choice_text, price=f"{price_start:,}"))
        
        await asyncio.sleep(60) # انتظر دقيقة
        
        price_end = get_btc_price()
        win = (choice == "up" and price_end > price_start) or (choice == "down" and price_end < price_start)
        
        if win:
            users_db[user_id]['points'] += 250
            result = STRINGS[lang]["win"].format(price=f"{price_end:,}", points=users_db[user_id]['points'])
        else:
            result = STRINGS[lang]["loss"].format(price=f"{price_end:,}", points=users_db[user_id]['points'])
            
        await query.edit_message_text(result)
        await asyncio.sleep(3)
        await show_main_menu(query, user_id)

    elif data == "balance":
        msg = "رصيدك: " if lang == "ar" else "Balance: "
        await query.answer(f"{msg}{users_db[user_id]['points']}", show_alert=True)

def main():
    # 1. تشغيل سيرفر الويب في الخلفية
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. تشغيل البوت
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    
    print("Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
