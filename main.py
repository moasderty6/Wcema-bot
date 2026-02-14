import os
import requests
import logging
import sqlite3
import asyncio
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

# --- مهمة معالجة الرهان الخلفية ---
async def process_bet(context, user_id, symbol, entry_price, direction):
    # الانتظار لمدة 60 ثانية في الخلفية
    await asyncio.sleep(60)
    
    exit_price = get_crypto_price(symbol)
    if exit_price:
        win = (direction == "up" and exit_price > entry_price) or (direction == "down" and exit_price < entry_price)
        amount = 100 if win else -100
        update_balance(user_id, amount)
        
        status = "🎉 WIN! +100 Points" if win else "❌ LOSS! -100 Points"
        msg = (f"📊 *{symbol} Result:*\n\n"
               f"Entry: ${entry_price:.4f}\n"
               f"Exit: ${exit_price:.4f}\n\n"
               f"*{status}*")
        await context.bot.send_message(user_id, msg, parse_mode='Markdown')
    else:
        await context.bot.send_message(user_id, "⚠️ Error fetching result. Balance protected.")

# --- المعالجات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_user(user_id):
        if context.args:
            try:
                ref_id = int(context.args[0])
                if get_user(ref_id):
                    update_balance(ref_id, 100)
                    await context.bot.send_message(ref_id, "🎁 Referral Bonus! +100 Points.")
            except: pass
        save_user(user_id, update.effective_user.username or "User", 1000, "Not Set")

    # تنسيق الأزرار المطلوب
    keyboard = [
        ['🎮 Bet Now'],
        ['💼 Wallet', '👤 Account'], # واليت يسار، اكاونت يمين
        ['🏧 Withdraw', '📢 Earn Points']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Welcome to TG Stars Saving! 🚀", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user: return

    if text == '👤 Account':
        msg = (f"👤 *Account Info*\n\nID: `{user[0]}`\n"
               f"Balance: {user[2]} Pts (${user[2]/1000} USDT)\n"
               f"Wallet: `{user[3]}`")
        await update.message.reply_text(msg, parse_mode='Markdown')

    elif text == '🎮 Bet Now':
        coins = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'AVAX', 'MATIC']
        keyboard = [[InlineKeyboardButton(c, callback_data=f"bet_{c}")] for c in coins]
        await update.message.reply_text("Select a coin:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == '💼 Wallet':
        await update.message.reply_text("Send your TRC20 address:")
        context.user_data['waiting_for_wallet'] = True

    elif text == '📢 Earn Points':
        bot = await context.bot.get_me()
        await update.message.reply_text(f"Your link: https://t.me/{bot.username}?start={user_id}")

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
        if not price:
            await query.edit_message_text("❌ Price Error.")
            return
        context.user_data.update({'coin': symbol, 'price': price})
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"{symbol}: ${price:.4f}\nPredict 60s direction:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("dir_"):
        direction = query.data.split("_")[1]
        symbol = context.user_data['coin']
        price = context.user_data['price']
        
        await query.edit_message_text(f"⏳ Bet active: {symbol} {direction.upper()}\nWait 60s...")
        
        # إنشاء مهمة خلفية لضمان عدم ضياع النتيجة
        asyncio.create_task(process_bet(context, query.from_user.id, symbol, price, direction))

if __name__ == '__main__':
    init_db()
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
