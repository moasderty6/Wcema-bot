import os
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- الإعدادات ---
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = Flask(__name__)

# إنشاء التطبيق
application = Application.builder().token(TOKEN).build()

REPLY_TEXT = (
    "Please use this Digital Currency Analysis Bot @AiCryptoGPTbot "
    "to be able to play and earn cryptocurrencies! 🚀"
)

def get_keyboard():
    keyboard = [[InlineKeyboardButton("Go to Bot Now 🔗", url="https://t.me/AiCryptoGPTbot")]]
    return InlineKeyboardMarkup(keyboard)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(REPLY_TEXT, reply_markup=get_keyboard())

# دالة إعداد البوت (Handlers)
async def setup_handlers():
    if not application._initialized:
        await application.initialize()
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_handler))

@app.route("/", methods=["GET"])
def index():
    return "Bot is online!", 200

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    # التأكد من أن المعالجات مفعّلة
    await setup_handlers()
    
    # استلام التحديث
    update = Update.de_json(request.get_json(force=True), application.bot)
    
    # معالجة التحديث
    await application.process_update(update)
    return "ok", 200

# هذه الدالة تقوم بتفعيل الويب هوك عند تشغيل الملف مباشرة
def set_webhook_sync():
    url = f"{WEBHOOK_URL}/{TOKEN}"
    # نستخدم requests بشكل خارجي وسريع لإخبار تليجرام بالرابط الجديد
    import requests
    requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}")

if __name__ == "__main__":
    # تفعيل الويب هوك قبل تشغيل Flask
    set_webhook_sync()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
