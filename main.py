import os
import requests
import logging
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    CallbackQueryHandler
)

# --- الإعدادات (استبدلها بالقيم الحقيقية أو استخدم Environment Variables) ---
TOKEN = "YOUR_TELEGRAM_TOKEN"
CMC_API_KEY = "YOUR_CMC_API_KEY"
WEBHOOK_URL = "https://your-app-name.onrender.com/webhook" # رابط تطبيقك على ريندر
PORT = int(os.environ.get('PORT', 5000))

# إعداد Flask للويب هوك
server = Flask(__name__)

# قاعدة بيانات وهمية (استخدم DB حقيقية في المشروع الفعلي)
users_db = {}
CRYPTO_LIST = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'AVAX', 'MATIC']

def get_crypto_price(symbol):
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        parameters = {'symbol': symbol, 'convert': 'USD'}
        headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': CMC_API_KEY}
        response = requests.get(url, headers=headers).json()
        return response['data'][symbol]['quote']['USD']['price']
    except:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # نظام الإحالة (Referral System)
    is_new_user = user_id not in users_db
    if is_new_user:
        referrer_id = None
        if context.args:
            try:
                referrer_id = int(context.args[0])
                if referrer_id in users_db and referrer_id != user_id:
                    users_db[referrer_id]['balance'] += 100
                    await context.bot.send_message(referrer_id, "🎁 Someone joined using your link! +100 Points.")
            except ValueError:
                pass
        
        users_db[user_id] = {
            'username': update.effective_user.username or "User",
            'balance': 1000,
            'wallet': 'Not Set',
            'id': user_id
        }

    keyboard = [['🌟 Add Funds', '🏧 Withdraw'], ['👤 Account', '💼 Wallet'], ['🎮 Bet Now', '📢 Earn Points']]
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
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={user_id}"
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
        if not price:
            await query.edit_message_text("Error fetching price. Try again.")
            return
        
        context.user_data['bet_coin'] = symbol
        context.user_data['entry_price'] = price
        
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), 
                     InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"Target: {symbol}\nCurrent Price: ${price:.4f}\n\nPredict price after 60s:", 
                                     reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("dir_"):
        direction = query.data.split("_")[1]
        symbol = context.user_data['bet_coin']
        entry_price = context.user_data['entry_price']
        user_id = query.from_user.id

        await query.edit_message_text(f"⏳ Bet active: {symbol} going {direction.upper()}\nEntry: ${entry_price:.4f}\nResult in 60 seconds...")
        
        # استخدام JobQueue بدلاً من sleep لعدم تعطيل البوت
        context.job_queue.run_once(
            check_bet_result, 
            60, 
            data={'uid': user_id, 'symbol': symbol, 'entry': entry_price, 'dir': direction},
            chat_id=user_id
        )

async def check_bet_result(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    exit_price = get_crypto_price(data['symbol'])
    user = users_db.get(data['uid'])
    
    win = False
    if data['dir'] == "up" and exit_price > data['entry']: win = True
    if data['dir'] == "down" and exit_price < data['entry']: win = True

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

# --- Flask & Webhook Logic ---
@server.route('/webhook', methods=['POST'])
def webhook_handler():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put(update)
    return "OK"

@server.route('/')
def index():
    return "Bot is Running!"

if __name__ == '__main__':
    # بناء تطبيق التليجرام
    application = Application.builder().token(TOKEN).build()
    
    # إضافة الأوامر والمقابض
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))

    # تشغيل Flask على خادم Gunicorn (أو داخلياً للتجربة)
    # ملاحظة: ريندر يدير المنافذ تلقائياً عبر المتغير PORT
    import threading
    
    # لبدء البوت مع الويب هوك بشكل صحيح:
    # 1. نقوم بضبط الويب هوك مع تليجرام
    application.bot.set_webhook(url=WEBHOOK_URL)
    
    # 2. تشغيل Flask في Thread منفصل أو استخدامه كـ Entry point
    # لسهولة الرفع على Render، سنقوم بتشغيل البوت بـ Polling إذا كنت لا تريد تعقيد الويب هوك
    # أو استخدام الـ Webhook مع Flask كما يلي:
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path='webhook',
        webhook_url=WEBHOOK_URL
    )
