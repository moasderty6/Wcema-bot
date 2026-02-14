import os
import requests
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    CallbackQueryHandler
)

# --- الإعدادات ---
TOKEN = "7793678424:AAH7mXshTdQ4RjynCh-VyzGZAzWtDSSkiFM"
CMC_API_KEY = "fbfc6aef-dab9-4644-8207-046b3cdf69a3"
WEBHOOK_URL = "https://wcema-bot-6hga.onrender.com" 
PORT = int(os.environ.get('PORT', 5000))

# تفعيل تسجيل الأخطاء (Logs) لمراقبة الأداء في Render
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

users_db = {}
CRYPTO_LIST = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'AVAX', 'MATIC']

def get_crypto_price(symbol):
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        parameters = {'symbol': symbol, 'convert': 'USD'}
        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': CMC_API_KEY,
        }
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if response.status_code == 200:
            price = data['data'][symbol]['quote']['USD']['price']
            return price
        else:
            logging.error(f"CMC API Error: {data['status']['error_message']}")
            return None
    except Exception as e:
        logging.error(f"Fetch Price Exception: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # نظام الإحالة
    if user_id not in users_db:
        if context.args:
            try:
                referrer_id = int(context.args[0])
                if referrer_id in users_db and referrer_id != user_id:
                    users_db[referrer_id]['balance'] += 100
                    await context.bot.send_message(referrer_id, "🎁 Someone joined using your link! +100 Points.")
            except: pass
        
        users_db[user_id] = {
            'username': update.effective_user.username or "User",
            'balance': 1000,
            'wallet': 'Not Set',
            'id': user_id
        }

    # تم إزالة زر Add Funds
    keyboard = [['🏧 Withdraw'], ['👤 Account', '💼 Wallet'], ['🎮 Bet Now', '📢 Earn Points']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Welcome to TG Stars Saving! 🚀\nChoose an option from below:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = users_db.get(user_id)
    if not user: return

    if text == '👤 Account':
        msg = (f"👤 *Account Info*\n\n"
               f"ID: `{user['id']}`\n"
               f"Username: @{user['username']}\n"
               f"Balance: {user['balance']} Points\n"
               f"Value: ${user['balance']/1000} USDT\n"
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
            await update.message.reply_text("❌ Please set your wallet address first via 'Wallet' button.")
        else:
            user['balance'] -= 10000
            await update.message.reply_text("✅ Withdrawal request for 10 USDT has been submitted!")

    elif text == '📢 Earn Points':
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={user_id}"
        await update.message.reply_text(f"Share your link to earn 100 points per user:\n`{link}`", parse_mode='Markdown')

    elif context.user_data.get('waiting_for_wallet'):
        user['wallet'] = text
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text(f"✅ Wallet updated successfully!")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("bet_"):
        symbol = query.data.split("_")[1]
        price = get_crypto_price(symbol)
        if price is None:
            await query.edit_message_text(f"❌ Error fetching {symbol} price. Please try again later.")
            return
        
        context.user_data['bet_coin'] = symbol
        context.user_data['entry_price'] = price
        
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), 
                     InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"Target: {symbol}\nCurrent Price: ${price:.4f}\n\nPredict price after 60s:", 
                                     reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("dir_"):
        direction = query.data.split("_")[1]
        symbol = context.user_data.get('bet_coin')
        entry_price = context.user_data.get('entry_price')
        user_id = query.from_user.id

        await query.edit_message_text(f"⏳ Bet active: {symbol} going {direction.upper()}\nEntry: ${entry_price:.4f}\nResult in 60 seconds...")
        
        context.job_queue.run_once(
            check_bet_result, 
            60, 
            data={'uid': user_id, 'symbol': symbol, 'entry': entry_price, 'dir': direction},
            chat_id=user_id
        )

async def check_bet_result(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    exit_price = get_crypto_price(data['symbol'])
    user = users_db.get(data['uid'])
    
    if exit_price is None:
        await context.bot.send_message(data['uid'], "⚠️ Error getting final price. Bet cancelled, balance unchanged.")
        return

    win = False
    if data['dir'] == "up" and exit_price > data['entry']: win = True
    elif data['dir'] == "down" and exit_price < data['entry']: win = True

    if win:
        user['balance'] += 100
        status = "🎉 WIN! +100 Points."
    else:
        user['balance'] -= 100
        status = "❌ LOST! -100 Points."

    await context.bot.send_message(
        data['uid'], 
        f"📊 Bet Result ({data['symbol']}):\nEntry: ${data['entry']:.4f}\nExit: ${exit_price:.4f}\n\n{status}"
    )

if __name__ == '__main__':
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )
