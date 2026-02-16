import os
import requests
import logging
import psycopg2 
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

# --- الإعدادات (استخدم متغيرات البيئة في Render لضمان الأمان) ---
TOKEN = os.environ.get('BOT_TOKEN', "7793678424:AAH7mXshTdQ4RjynCh-VyzGZAzWtDSSkiFM")
DATABASE_URL = os.environ.get('DATABASE_URL', "postgresql://neondb_owner:npg_txJFdgkvBH35@ep-icy-forest-aia1n447-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require")
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', "https://wcema-bot-6hga.onrender.com") 
PORT = int(os.environ.get('PORT', 5000))
ADMIN_ID = 6172153716 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- إدارة قاعدة البيانات ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id BIGINT PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 1000, wallet TEXT DEFAULT 'Not Set')''')
    conn.commit()
    c.close()
    conn.close()

def get_user(user_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, username, balance, wallet FROM users WHERE id=%s", (user_id,))
        user = c.fetchone()
        c.close()
        conn.close()
        return user
    except: return None

def save_user(user_id, username, balance, wallet):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO users (id, username, balance, wallet) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET username=%s, wallet=%s", (user_id, username, balance, wallet, username, wallet))
    conn.commit()
    c.close()
    conn.close()

def update_balance(user_id, amount):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, user_id))
    conn.commit()
    c.close()
    conn.close()

# --- جلب السعر اللحظي من Binance ---
def get_crypto_price(symbol):
    try:
        sym = symbol.strip().upper() + "USDT"
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
        response = requests.get(url, timeout=5)
        return float(response.json()['price'])
    except: return None

# --- معالجة الرهان مع تحديث "لايف" ومنطق التعادل ---
async def process_bet(context, user_id, message_id, symbol, entry_price, direction):
    seconds = 30
    while seconds > 0:
        await asyncio.sleep(5) # تحديث كل 5 ثوانٍ
        seconds -= 5
        current_p = get_crypto_price(symbol)
        if current_p:
            diff = current_p - entry_price
            trend = "🟢 Profit" if (direction == "up" and diff > 0) or (direction == "down" and diff < 0) else "🔴 Loss"
            if diff == 0: trend = "🟡 Neutral"
            
            live_msg = (f"🚀 <b>Trade Live: {symbol}</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"📉 Entry: <code>${entry_price:.4f}</code>\n"
                        f"📊 Live: <code>${current_p:.4f}</code>\n"
                        f"⏳ Time: {seconds}s\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"Status: <b>{trend}</b>")
            try:
                await context.bot.edit_message_text(live_msg, chat_id=user_id, message_id=message_id, parse_mode='HTML')
            except: pass

    # النتيجة النهائية
    exit_price = get_crypto_price(symbol)
    if exit_price:
        if exit_price == entry_price: # منطق التعادل
            status = "🟡 DRAW! Price Unchanged"
            amount = 0
        else:
            win = (direction == "up" and exit_price > entry_price) or (direction == "down" and exit_price < entry_price)
            amount = 200 if win else -200
            update_balance(user_id, amount)
            status = "🟢 WINNER! +200 Pts" if win else "🔴 LOSS! -200 Pts"

        final_msg = (f"🏆 <b>{symbol} Final Result</b>\n"
                     f"━━━━━━━━━━━━━━\n"
                     f"📉 Entry: <code>${entry_price:.4f}</code>\n"
                     f"📈 Exit: <code>${exit_price:.4f}</code>\n"
                     f"━━━━━━━━━━━━━━\n"
                     f"<b>{status}</b>")
        await context.bot.send_message(user_id, final_msg, parse_mode='HTML')
    else:
        await context.bot.send_message(user_id, "⚠️ Network Error. Points returned.")

# --- الأوامر والرسائل ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"Pilot_{user_id}"
    if not get_user(user_id):
        save_user(user_id, username, 1000, "Not Set")
    
    keyboard = [['🎮 Bet Now'], ['💼 Wallet', '👤 Account'], ['🏧 Withdraw', '📢 Earn Points']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(f"🌕 <b>Welcome to Binance Moonbix!</b>\n\nPredict market moves and win! 🚀", reply_markup=reply_markup, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user: return

    if text == '👤 Account':
        await update.message.reply_text(f"🚀 <b>Pilot: @{user[1]}</b>\n💰 Balance: <b>{user[2]:,} Pts</b>\n🏦 Wallet: <code>{user[3]}</code>", parse_mode='HTML')
    elif text == '🎮 Bet Now':
        if user[2] < 200:
            await update.message.reply_text("❌ Insufficient Balance (Min 200 Pts).")
            return
        coins = ['BTC', 'ETH', 'BNB', 'SOL', 'TON', 'DOGE']
        keyboard = [[InlineKeyboardButton(f"🪙 {c}", callback_data=f"bet_{c}")] for c in coins]
        await update.message.reply_text("✨ <b>Choose Asset:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    elif text == '💼 Wallet':
        await update.message.reply_text("🔗 Send your <b>TRC20</b> address:", parse_mode='HTML')
        context.user_data['waiting_for_wallet'] = True
    elif context.user_data.get('waiting_for_wallet'):
        save_user(user_id, user[1], user[2], text)
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text("✅ Wallet Connected!")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    if query.data.startswith("bet_"):
        symbol = query.data.split("_")[1]
        price = get_crypto_price(symbol)
        if not price: return
        context.user_data.update({'coin': symbol, 'price': price})
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"🪙 <b>{symbol} Market</b>\nPrice: <code>${price:.4f}</code>\n\nPredict 30s move:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    elif query.data.startswith("dir_"):
        direction = query.data.split("_")[1]
        msg = await query.edit_message_text(f"🚀 <b>Trade Executed!</b>\nWaiting... ⏳", parse_mode='HTML')
        asyncio.create_task(process_bet(context, user_id, msg.message_id, context.user_data['coin'], context.user_data['price'], direction))

if __name__ == '__main__':
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL}/{TOKEN}")
