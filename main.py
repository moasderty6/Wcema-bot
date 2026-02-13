import os
import asyncio
import requests
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- الإعدادات ---
TOKEN = os.getenv("BOT_TOKEN")
CMC_API_KEY = os.getenv("CMC_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # مثال: https://your-app.onrender.com

app = Flask(__name__)

# إنشاء تطبيق التليجرام عالمياً
application = Application.builder().token(TOKEN).build()

users = {}
COINS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "DOT", "TRX", "MATIC"]

# --- الوظائف المساعدة ---
def get_user(user_obj):
    if user_obj.id not in users:
        users[user_obj.id] = {"username": user_obj.username or "User", "balance": 1000, "wallet": None}
    return users[user_obj.id]

def get_price(symbol):
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
        params = {"symbol": symbol}
        response = requests.get(url, headers=headers, params=params)
        return response.json()["data"][symbol]["quote"]["USD"]["price"]
    except: return 0

def main_menu():
    keyboard = [
        [InlineKeyboardButton("👤 Account", callback_data="account")],
        [InlineKeyboardButton("📈 Bet", callback_data="bet")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- معالجات البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user)
    await update.message.reply_text("Welcome to Crypto Betting Bot 🚀", reply_markup=main_menu())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user)

    if query.data == "account":
        text = f"💰 Balance: {user['balance']} Points\n💵 Value: {user['balance']/1000} USDT"
        await query.edit_message_text(text, reply_markup=main_menu())

    elif query.data == "bet":
        keyboard = [[InlineKeyboardButton(c, callback_data=f"coin_{c}")] for c in COINS]
        await query.edit_message_text("Choose a coin:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("coin_"):
        coin = query.data.split("_")[1]
        context.user_data["coin"] = coin
        price = get_price(coin)
        context.user_data["start_price"] = price
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="up"), InlineKeyboardButton("📉 DOWN", callback_data="down")]]
        await query.edit_message_text(f"{coin} Price: ${price:.2f}\nDirection?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data in ["up", "down"]:
        direction = query.data
        coin, start_price = context.user_data.get("coin"), context.user_data.get("start_price")
        await query.edit_message_text(f"⏳ Waiting 60s for {coin}...")
        
        await asyncio.sleep(60) # سيستمر العمل لأن Render يبقي الطلب مفتوحاً
        
        end_price = get_price(coin)
        win = (direction == "up" and end_price > start_price) or (direction == "down" and end_price < start_price)
        user["balance"] += 100 if win else -100
        await query.message.reply_text(f"Result: {'🎉 WON' if win else '❌ LOST'}\nEnd Price: ${end_price:.2f}", reply_markup=main_menu())

# --- إعداد Flask للـ Webhook ---
@app.route("/", methods=["GET"])
def index(): return "Bot is Alive!"

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook(request): # لاحظ استخدام async هنا
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        return "ok", 200

# --- تشغيل التطبيق بالطريقة الصحيحة لـ Render ---
async def setup_webhook():
    await application.initialize()
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))

# تشغيل الـ Setup عند بدء التشغيل
loop = asyncio.get_event_loop()
loop.run_until_complete(setup_webhook())

if __name__ == "__main__":
    # ريندر يستخدم بورت 10000 افتراضياً
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
