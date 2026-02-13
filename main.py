import os
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configurations ---
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Your Render URL without a trailing slash

app = Flask(__name__)

# Initialize Telegram Application
application = Application.builder().token(TOKEN).build()

# --- Response Text ---
REPLY_TEXT = (
    "Please use this Digital Currency Analysis Bot @AiCryptoGPTbot "
    "to be able to play and earn cryptocurrencies! 🚀"
)

def get_keyboard():
    keyboard = [[
        InlineKeyboardButton("Go to Bot Now 🔗", url="https://t.me/AiCryptoGPTbot")
    ]]
    return InlineKeyboardMarkup(keyboard)

# --- Bot Handlers ---
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responds to /start and all text messages."""
    await update.message.reply_text(REPLY_TEXT, reply_markup=get_keyboard())

# --- Flask & Webhook Routes ---
@app.route("/", methods=["GET"])
def index():
    return "Bot is active and running!", 200

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    # Process the update from Telegram
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok", 200

# --- Setup Function ---
async def setup():
    await application.initialize()
    # Set the webhook URL on Telegram's side
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    
    # Add handlers for /start and any text message
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_handler))

# Run the setup before starting Flask
loop = asyncio.get_event_loop()
loop.run_until_complete(setup())

if __name__ == "__main__":
    # Render assigns a port via the PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
