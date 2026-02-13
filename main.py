import os
import json
import random
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

TOKEN = os.getenv("BOT_TOKEN")
CMC_API_KEY = os.getenv("CMC_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = Flask(__name__)
users = {}

COINS = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "DOGE", "DOT", "TRX", "MATIC"
]

# -------- USER INIT --------
def get_user(user):
    if user.id not in users:
        users[user.id] = {
            "username": user.username,
            "balance": 1000,
            "wallet": None,
            "invites": 0,
        }
    return users[user.id]

# -------- PRICE FROM CMC --------
def get_price(symbol):
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
    params = {"symbol": symbol}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    return data["data"][symbol]["quote"]["USD"]["price"]

# -------- MAIN MENU --------
def main_menu():
    keyboard = [
        [InlineKeyboardButton("👤 Account", callback_data="account")],
        [InlineKeyboardButton("📈 Bet", callback_data="bet")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🎁 Earn Points", callback_data="earn")],
    ]
    return InlineKeyboardMarkup(keyboard)

# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user)
    await update.message.reply_text(
        "Welcome to Crypto Betting Bot 🚀",
        reply_markup=main_menu()
    )

# -------- BUTTON HANDLER --------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user)

    if query.data == "account":
        text = f"""
👤 Username: @{user['username']}
🆔 ID: {query.from_user.id}
💰 Balance: {user['balance']} Points
💵 Value: {user['balance']/1000} USDT
🏦 Wallet: {user['wallet']}
"""
        await query.edit_message_text(text, reply_markup=main_menu())

    elif query.data == "bet":
        keyboard = [
            [InlineKeyboardButton(c, callback_data=f"coin_{c}")]
            for c in COINS
        ]
        await query.edit_message_text(
            "Choose a coin:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("coin_"):
        coin = query.data.split("_")[1]
        context.user_data["coin"] = coin
        price = get_price(coin)
        context.user_data["start_price"] = price

        keyboard = [
            [
                InlineKeyboardButton("📈 UP", callback_data="up"),
                InlineKeyboardButton("📉 DOWN", callback_data="down"),
            ]
        ]

        await query.edit_message_text(
            f"{coin} Price: {price}\nChoose direction:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data in ["up", "down"]:
        direction = query.data
        coin = context.user_data["coin"]
        start_price = context.user_data["start_price"]

        await query.edit_message_text("⏳ Waiting 60 seconds...")

        await asyncio.sleep(60)

        end_price = get_price(coin)
        win = (
            (direction == "up" and end_price > start_price) or
            (direction == "down" and end_price < start_price)
        )

        if win:
            user["balance"] += 100
            result = "🎉 You WON +100 Points!"
        else:
            user["balance"] -= 100
            result = "❌ You LOST -100 Points!"

        await query.message.reply_text(
            f"{coin} Start: {start_price}\n"
            f"{coin} End: {end_price}\n\n"
            f"{result}",
            reply_markup=main_menu()
        )

    elif query.data == "withdraw":
        if user["balance"] >= 10000:
            user["balance"] -= 10000
            await query.edit_message_text(
                "✅ Withdraw request submitted (10 USDT)",
                reply_markup=main_menu()
            )
        else:
            await query.edit_message_text(
                "❌ You need 10000 points (10 USDT)",
                reply_markup=main_menu()
            )

    elif query.data == "earn":
        invite_link = f"https://t.me/{context.bot.username}?start={query.from_user.id}"
        await query.edit_message_text(
            f"Share this link:\n{invite_link}\n\n"
            "You earn 100 points per user.",
            reply_markup=main_menu()
        )

# -------- WEBHOOK ROUTE --------
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return "ok"

# -------- RUN --------
if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))

    application.bot.set_webhook(f"{WEBHOOK_URL}/{TOKEN}")
    app.run(host="0.0.0.0", port=10000)