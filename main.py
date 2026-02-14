import os
import time
import requests
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQuery_handler

# --- الإعدادات ---
TOKEN = "YOUR_TELEGRAM_TOKEN"
CMC_API_KEY = "YOUR_YOUR_CMC_API_KEY"
app = Flask(__name__)

# قاعدة بيانات مؤقتة (في الإنتاج استخدم SQLite أو MongoDB)
users_db = {}

# قائمة العملات المتاحة
CRYPTO_LIST = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'AVAX', 'MATIC']

def get_crypto_price(symbol):
    url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    parameters = {'symbol': symbol, 'convert': 'USD'}
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': CMC_API_KEY}
    response = requests.get(url, headers=headers).json()
    return response['data'][symbol]['quote']['USD']['price']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_db:
        users_db[user_id] = {
            'username': update.effective_user.username or "User",
            'balance': 1000,
            'wallet': 'Not Set',
            'id': user_id
        }
    
    keyboard = [['🌟 Add Funds', '🏧 Withdraw'], ['👤 Account', '💼 Wallet'], ['🎮 Bet Now', '📢 Earn Points']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Welcome to TG Stars Saving! Choose an option:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = users_db.get(user_id)

    if text == '👤 Account':
        msg = (f"👤 *Account Info*\n\n"
               f"ID: `{user['id']}`\n"
               f"Username: @{user['username']}\n"
               f"Balance: {user['balance']} Points (${user['balance']/1000} USDT)\n"
               f"Wallet: `{user['wallet']}`")
        await update.message.reply_text(msg, parse_mode='Markdown')

    elif text == '🎮 Bet Now':
        keyboard = [[InlineKeyboardButton(c, callback_data=f"bet_{c}")] for c in CRYPTO_LIST]
        await update.message.reply_text("Select a coin to bet on (60s):", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == '💼 Wallet':
        await update.message.reply_text("Please send your TRC20 wallet address:")
        context.user_data['waiting_for_wallet'] = True

    elif text == '🏧 Withdraw':
        if user['balance'] < 10000:
            await update.message.reply_text("❌ Minimum withdrawal is 10,000 Points (10 USDT).")
        elif user['wallet'] == 'Not Set':
            await update.message.reply_text("❌ Please set your wallet address first.")
        else:
            user['balance'] -= 10000
            await update.message.reply_text("✅ Withdrawal request of 10 USDT sent!")

    elif text == '📢 Earn Points':
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={user_id}"
        await update.message.reply_text(f"Share your link to earn 100 points per user:\n{link}")

    elif context.user_data.get('waiting_for_wallet'):
        user['wallet'] = text
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text(f"✅ Wallet updated to: {text}")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("bet_"):
        symbol = data.split("_")[1]
        price = get_crypto_price(symbol)
        context.user_data['bet_coin'] = symbol
        context.user_data['entry_price'] = price
        
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), 
                     InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"Current {symbol} Price: ${price:.4f}\nPredict direction for next 60s:", 
                                     reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("dir_"):
        direction = data.split("_")[1]
        symbol = context.user_data['bet_coin']
        entry_price = context.user_data['entry_price']
        user_id = query.from_user.id

        await query.edit_message_text(f"⏳ Bet placed on {symbol} going {direction.upper()}... Waiting 60s.")
        
        # في الحقيقة الويب هوك لا يتحمل النوم (sleep)، لكن للتبسيط هنا:
        time.sleep(60) 
        
        exit_price = get_crypto_price(symbol)
        win = False
        if direction == "up" and exit_price > entry_price: win = True
        if direction == "down" and exit_price < entry_price: win = True

        if win:
            users_db[user_id]['balance'] += 100:
            res = "🎉 YOU WON! +100 Points."
        else:
            users_db[user_id]['balance'] -= 100:
            res = "❌ YOU LOST! -100 Points."
            
        await context.bot.send_message(user_id, f"Entry: ${entry_price:.4f}\nExit: ${exit_price:.4f}\n\n{res}")

# --- Flask Webhook Setup ---
@app.route('/webhook', methods=['POST'])
def webhook():
    # هذا الجزء لاستلام التحديثات من تليجرام وتمريرها للبوت
    return "OK"

if __name__ == '__main__':
    # إعداد البوت (Logic)
    # ملاحظة: في Render يفضل استخدام polling للسهولة أو ضبط الـ Webhook بشكل كامل
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))
    
    application.run_polling() # Render يحتاج Polling إذا لم تكن ستدفع لـ Static IP
