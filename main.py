import os
import asyncio
import requests
import time
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# تحميل متغيرات البيئة
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# تخزين بيانات المستخدمين (في الذاكرة - يفضل SQL في المستقبل)
users_db = {}

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
        users_db[user_id] = {"points": 1000, "last_claim": 0}
    
    keyboard = [
        [InlineKeyboardButton("📈 صعود (60ث)", callback_query_data='trade_up')],
        [InlineKeyboardButton("📉 هبوط (60ث)", callback_query_data='trade_down')],
        [InlineKeyboardButton("💰 رصيدي", callback_query_data='balance')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"مرحباً بك في محاكي Moonbix! 🚀\n\n"
        f"رصيدك الحالي: {users_db[user_id]['points']} نقطة.\n"
        "توقع اتجاه BTC خلال الـ 60 ثانية القادمة واربح!",
        reply_markup=reply_markup
    )

async def handle_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    choice = "up" if query.data == "trade_up" else "down"
    
    if users_db[user_id]['points'] < 100:
        await query.edit_message_text("عذراً، رصيدك أقل من 100 نقطة!")
        return

    price_start = get_btc_price()
    users_db[user_id]['points'] -= 100 # خصم مبلغ الرهان
    
    status_msg = "✅ تم تسجيل توقعك: " + ("صعود 📈" if choice == "up" else "هبوط 📉")
    status_msg += f"\nسعر الدخول: ${price_start:,}"
    
    await query.edit_message_text(f"{status_msg}\n⏳ جاري مراقبة السوق (60 ثانية)...")
    
    await asyncio.sleep(60) # الانتظار دقيقة
    
    price_end = get_btc_price()
    win = False
    if choice == "up" and price_end > price_start: win = True
    elif choice == "down" and price_end < price_start: win = True
    
    if win:
        users_db[user_id]['points'] += 250 # استرداد الـ 100 + ربح 150
        result_text = f"🎉 مبروك! ربحت التحدي.\nالسعر النهائي: ${price_end:,}\nرصيدك: {users_db[user_id]['points']}"
    else:
        result_text = f"❌ للأسف، خسرت التحدي.\nالسعر النهائي: ${price_end:,}\nرصيدك: {users_db[user_id]['points']}"
        
    await query.edit_message_text(result_text)

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    points = users_db.get(user_id, {}).get("points", 0)
    await query.answer(f"رصيدك الحالي: {points} نقطة", show_alert=True)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_trade, pattern='^trade_'))
    app.add_handler(CallbackQueryHandler(show_balance, pattern='^balance$'))
    app.run_polling()

if __name__ == "__main__":
    main()
