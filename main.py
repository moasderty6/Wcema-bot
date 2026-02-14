import os
import requests
import logging
import sqlite3
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

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT, balance INTEGER, wallet TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def save_user(user_id, username, balance, wallet):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?)", (user_id, username, balance, wallet))
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- جلب السعر ---
def get_crypto_price(symbol):
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        parameters = {'symbol': symbol.strip().upper(), 'convert': 'USD'}
        headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': CMC_API_KEY}
        response = requests.get(url, headers=headers, params=parameters, timeout=10)
        data = response.json()
        if response.status_code == 200:
            return data['data'][symbol.upper()]['quote']['USD']['price']
        return None
    except:
        return None

# --- المعالجات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    
    if not get_user(user_id):
        if context.args:
            try:
                ref_id = int(context.args[0])
                if get_user(ref_id) and ref_id != user_id:
                    update_balance(ref_id, 100)
                    await context.bot.send_message(ref_id, "🎁 Referral Bonus! +100 Points.")
            except: pass
        save_user(user_id, username, 1000, "Not Set")

    # تعديل ترتيب الأزرار ليكون Bet Now في الأعلى وكبير
    keyboard = [
        ['🎮 Bet Now'], 
        ['🏧 Withdraw', '📢 Earn Points'],
        ['👤 Account', '💼 Wallet']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Welcome to TG Stars Saving! 🚀", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data: return

    if text == '👤 Account':
        msg = (f"👤 *Account Info*\n\nID: `{user_data[0]}`\n"
               f"Balance: {user_data[2]} Pts (${user_data[2]/1000} USDT)\n"
               f"Wallet: `{user_data[3]}`")
        await update.message.reply_text(msg, parse_mode='Markdown')

    elif text == '🎮 Bet Now':
        coins = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'AVAX', 'MATIC']
        keyboard = [[InlineKeyboardButton(c, callback_data=f"bet_{c}")] for c in coins]
        await update.message.reply_text("Select a coin (60s):", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == '💼 Wallet':
        await update.message.reply_text("Send your TRC20 address:")
        context.user_data['waiting_for_wallet'] = True

    elif text == '📢 Earn Points':
        bot_info = await context.bot.get_me()
        await update.message.reply_text(f"Your link: https://t.me/{bot_info.username}?start={user_id}")

    elif context.user_data.get('waiting_for_wallet'):
        conn = sqlite3.connect('bot_data.db')
        conn.execute("UPDATE users SET wallet = ? WHERE id = ?", (text, user_id))
        conn.commit()
        conn.close()
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text("✅ Wallet Saved!")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("bet_"):
        symbol = query.data.split("_")[1]
        price = get_crypto_price(symbol)
        if price is None:
            await query.edit_message_text("❌ Price Error. Try again.")
            return
        
        context.user_data.update({'bet_coin': symbol, 'entry_price': price})
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), 
                     InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"{symbol}: ${price:.4f}\nPredict 60s direction:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("dir_"):
        direction = query.data.split("_")[1]
        symbol = context.user_data.get('bet_coin')
        entry_price = context.user_data.get('entry_price')
        user_id = query.from_user.id
        
        await query.edit_message_text(f"⏳ Bet on {symbol} {direction.upper()}...\nResult in 60s.")
        
        # التأكد من تمرير البيانات للـ Job بشكل صحيح
        context.job_queue.run_once(
            check_bet_result, 
            60, 
            data={'uid': user_id, 'symbol': symbol, 'entry': entry_price, 'dir': direction},
            chat_id=query.message.chat_id
        )

async def check_bet_result(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    exit_price = get_crypto_price(data['symbol'])
    
    if exit_price:
        win = False
        if data['dir'] == "up" and exit_price > data['entry']: win = True
        elif data['dir'] == "down" and exit_price < data['entry']: win = True
        
        amount = 100 if win else -100
        update_balance(data['uid'], amount)
        
        res = "🎉 WIN! +100 Points" if win else "❌ LOSS! -100 Points"
        final_msg = (f"📊 *{data['symbol']} Result:*\n\n"
                     f"Entry: ${data['entry']:.4f}\n"
                     f"Exit: ${exit_price:.4f}\n\n"
                     f"*{res}*")
        
        await context.bot.send_message(data['uid'], final_msg, parse_mode='Markdown')
    else:
        await context.bot.send_message(data['uid'], "⚠️ Error fetching final price. Balance not changed.")

if __name__ == '__main__':
    init_db()
    # بناء التطبيق مع تفعيل الـ JobQueue تلقائياً
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))

    # تشغيل الويب هوك
    application.run_webhook(
        listen="0.0.0.0", 
        port=PORT, 
        url_path=TOKEN, 
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )
