import os
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- الإعدادات ---
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = Flask(__name__)

# إنشاء التطبيق مرة واحدة فقط
application = Application.builder().token(TOKEN).build()

REPLY_TEXT = (
    "Please use this Digital Currency Analysis Bot @AiCryptoGPTbot "
    "to be able to play and earn cryptocurrencies! 🚀"
)

def get_keyboard():
    keyboard = [
        [InlineKeyboardButton("Go to Bot Now 🔗", url="https://t.me/AiCryptoGPTbot")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- الهاندلر ---
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            REPLY_TEXT,
            reply_markup=get_keyboard()
        )

# --- تهيئة البوت مرة واحدة فقط ---
async def init_telegram():
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_handler))
    
    await application.initialize()
    await application.start()

# --- Webhook Route ---
@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is online!", 200

# --- تعيين الويب هوك ---
def set_webhook():
    import requests
    url = f"{WEBHOOK_URL}/{TOKEN}"
    requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}")

# --- تشغيل السيرفر ---
if __name__ == "__main__":
    asyncio.run(init_telegram())   # 🔥 التهيئة مرة واحدة فقط
    set_webhook()                  # 🔥 تعيين الويب هوك
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)