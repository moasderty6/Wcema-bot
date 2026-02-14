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
ADMIN_ID = 6172153716 

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

# --- معالجة الرهان (30 ثانية) ---
async def process_bet(context, user_id, symbol, entry_price, direction):
    await asyncio.sleep(30)
    exit_price = get_crypto_price(symbol)
    if exit_price:
        win = (direction == "up" and exit_price > entry_price) or (direction == "down" and exit_price < entry_price)
        amount = 100 if win else -100
        update_balance(user_id, amount)
        status = "🎉 WIN! +100 Points" if win else "❌ LOSS! -100 Points"
        msg = (f"📊 <b>{symbol} Result:</b>\n\n"
               f"Entry: ${entry_price:.4f}\n"
               f"Exit: ${exit_price:.4f}\n\n"
               f"<b>{status}</b>")
        await context.bot.send_message(user_id, msg, parse_mode='HTML')
    else:
        await context.bot.send_message(user_id, "⚠️ Error fetching result.")

# --- المعالجات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    
    if not get_user(user_id):
        if context.args:
            try:
                ref_id = int(context.args[0])
                if get_user(ref_id):
                    update_balance(ref_id, 100)
                    await context.bot.send_message(ref_id, "🎁 New user joined via your link! +100 Points.")
            except: pass
        save_user(user_id, username, 1000, "Not Set")

    keyboard = [
        ['🎮 Bet Now'],
        ['💼 Wallet', '👤 Account'],
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
        msg = (f"👤 <b>Account Info</b>\n\n"
               f"ID: <code>{user[0]}</code>\n"
               f"Balance: {user[2]} Pts (${user[2]/1000} USDT)\n"
               f"Wallet: <code>{user[3]}</code>")
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == '🎮 Bet Now':
        coins = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'AVAX', 'MATIC']
        keyboard = [[InlineKeyboardButton(c, callback_data=f"bet_{c}")] for c in coins]
        await update.message.reply_text("Select a coin:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == '💼 Wallet':
        await update.message.reply_text("Please send your TRC20 wallet address:")
        context.user_data['waiting_for_wallet'] = True

    elif text == '🏧 Withdraw':
        if user[2] < 10000:
            await update.message.reply_text(f"❌ Min withdrawal: 10,000 Pts.\nBalance: {user[2]} Pts.")
        elif user[3] == "Not Set":
            await update.message.reply_text("❌ Please set your wallet address via 💼 Wallet button.")
        else:
            await update.message.reply_text(f"✅ Your balance: {user[2]} Pts.\nEnter the amount to withdraw:")
            context.user_data['waiting_for_withdraw_amount'] = True

    elif text == '📢 Earn Points':
        bot_info = await context.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start={user_id}"
        # تم استخدام HTML لضمان عمل الرابط بشكل صحيح
        msg = (f"📢 <b>Referral Program</b>\n\n"
               f"Earn <b>100 Points</b> for every friend you invite!\n\n"
               f"Invite Link:\n{share_link}")
        await update.message.reply_text(msg, parse_mode='HTML', disable_web_page_preview=True)

    elif context.user_data.get('waiting_for_wallet'):
        conn = sqlite3.connect('bot_data.db')
        conn.execute("UPDATE users SET wallet = ? WHERE id = ?", (text, user_id))
        conn.commit()
        conn.close()
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text("✅ Wallet Saved!")

    elif context.user_data.get('waiting_for_withdraw_amount'):
        try:
            amount = int(text)
            if amount < 10000:
                await update.message.reply_text("❌ Min 10,000 Pts.")
            elif amount > user[2]:
                await update.message.reply_text("❌ Insufficient balance!")
            else:
                update_balance(user_id, -amount)
                context.user_data['waiting_for_withdraw_amount'] = False
                await update.message.reply_text(f"✅ Request for {amount} Pts sent to admin.")
                admin_msg = (f"🔔 <b>Withdrawal Request</b>\nUser: @{user[1]}\nID: <code>{user[0]}</code>\nAmount: {amount} Pts\nWallet: <code>{user[3]}</code>")
                await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode='HTML')
        except:
            await update.message.reply_text("❌ Enter numbers only.")

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
        await query.edit_message_text(f"{symbol}: ${price:.4f}\nPredict 30s direction:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith("dir_"):
        direction = query.data.split("_")[1]
        symbol = context.user_data['coin']
        price = context.user_data['price']
        await query.edit_message_text(f"⏳ Bet active: {symbol} {direction.upper()}\nWait 30s...")
        asyncio.create_task(process_bet(context, query.from_user.id, symbol, price, direction))

if __name__ == '__main__':
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL}/{TOKEN}")
