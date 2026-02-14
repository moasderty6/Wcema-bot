import os
import requests
import logging
import psycopg2 # استخدام PostgreSQL بدلاً من SQLite
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
DATABASE_URL = "postgresql://neondb_owner:npg_txJFdgkvBH35@ep-icy-forest-aia1n447-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- إدارة قاعدة البيانات PostgreSQL ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id BIGINT PRIMARY KEY, username TEXT, balance INTEGER, wallet TEXT)''')
    # إضافة رصيد تجريبي للمستخدم المحدد
    c.execute("INSERT INTO users (id, username, balance, wallet) VALUES (565965404, 'Tester', 100000, 'Not Set') ON CONFLICT (id) DO UPDATE SET balance = 100000")
    conn.commit()
    c.close()
    conn.close()

def get_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, username, balance, wallet FROM users WHERE id=%s", (user_id,))
    user = c.fetchone()
    c.close()
    conn.close()
    return user

def save_user(user_id, username, balance, wallet):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO users (id, username, balance, wallet) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET username=%s, wallet=%s", 
              (user_id, username, balance, wallet, username, wallet))
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
        amount = 500 if win else -500
        update_balance(user_id, amount)
        status = "🟢 WINNER! +500 Pts" if win else "🔴 LOSS! -500 Pts"
        msg = (f"🏆 <b>{symbol} Trade Result</b>\n"
               f"━━━━━━━━━━━━━━\n"
               f"📉 Entry: <code>${entry_price:.4f}</code>\n"
               f"📈 Exit: <code>${exit_price:.4f}</code>\n"
               f"━━━━━━━━━━━━━━\n"
               f"<b>{status}</b>")
        await context.bot.send_message(user_id, msg, parse_mode='HTML')
    else:
        await context.bot.send_message(user_id, "⚠️ Market connection lost. Points safe.")

# --- المعالجات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Space_Traveler"
    
    if not get_user(user_id):
        if context.args:
            try:
                ref_id = int(context.args[0])
                if get_user(ref_id):
                    update_balance(ref_id, 200)
                    await context.bot.send_message(ref_id, "🚀 <b>New Pilot!</b> You earned 200 Pts.", parse_mode='HTML')
            except: pass
        save_user(user_id, username, 1000, "Not Set")

    keyboard = [['🎮 Bet Now'], ['💼 Wallet', '👤 Account'], ['🏧 Withdraw', '📢 Earn Points']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(f"🌕 <b>Bybit Moonbix Bot</b>\n\nTrade & Earn in the galaxy! 🚀", reply_markup=reply_markup, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user: return

    if text == '👤 Account':
        # عرض اليوزر نيم فوق الـ ID كما طلبت
        msg = (f"🚀 <b>Moonbix Pilot: @{user[1]}</b>\n"
               f"━━━━━━━━━━━━━━\n"
               f"🆔 ID: <code>{user[0]}</code>\n"
               f"💰 Balance: <b>{user[2]:,} Pts</b>\n"
               f"💵 Value: <b>${user[2]/1000:.2f} USDT</b>\n"
               f"🏦 Wallet: <code>{user[3]}</code>")
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == '🎮 Bet Now':
        coins = ['BTC', 'ETH', 'BNB', 'SOL', 'TON', 'XRP', 'DOT', 'DOGE', 'AVAX', 'ADA']
        keyboard = [[InlineKeyboardButton(f"🪙 {c}", callback_data=f"bet_{c}")] for c in coins]
        await update.message.reply_text("✨ <b>Choose Asset:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif text == '💼 Wallet':
        await update.message.reply_text("🔗 <b>Wallet Setup</b>\nSend your TRC20 address:", parse_mode='HTML')
        context.user_data['waiting_for_wallet'] = True

    elif text == '🏧 Withdraw':
        if user[2] < 10000:
            await update.message.reply_text(f"⚠️ <b>Low Fuel!</b> Min: 10,000 Pts.\nBalance: {user[2]:,} Pts.", parse_mode='HTML')
        elif user[3] == "Not Set":
            await update.message.reply_text("❌ Set your wallet first!", parse_mode='HTML')
        else:
            await update.message.reply_text(f"✅ Balance: {user[2]:,} Pts.\nEnter amount to withdraw:", parse_mode='HTML')
            context.user_data['waiting_for_withdraw_amount'] = True

    elif text == '📢 Earn Points':
        bot = await context.bot.get_me()
        share_link = f"https://t.me/{bot.username}?start={user_id}"
        msg = f"🎁 <b>Moonbix Referral</b>\n\nEarn <b>200 Pts</b> per invite!\n\n🔗 {share_link}"
        await update.message.reply_text(msg, parse_mode='HTML', disable_web_page_preview=True)

    elif context.user_data.get('waiting_for_wallet'):
        save_user(user_id, user[1], user[2], text)
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text("✅ <b>Wallet Connected!</b>", parse_mode='HTML')

    elif context.user_data.get('waiting_for_withdraw_amount'):
        try:
            amt = int(text)
            if amt < 10000 or amt > user[2]:
                await update.message.reply_text("❌ <b>Invalid amount or insufficient balance!</b>")
            else:
                update_balance(user_id, -amt)
                context.user_data['waiting_for_withdraw_amount'] = False
                await update.message.reply_text("🎊 <b>Request Sent!</b> Review in 24h.", parse_mode='HTML')
                admin_msg = f"🔔 <b>NEW WITHDRAW</b>\nUser: @{user[1]}\nID: {user[0]}\nAmt: {amt:,} Pts\nWallet: {user[3]}"
                await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode='HTML')
        except:
            await update.message.reply_text("❌ Numbers only.")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("bet_"):
        symbol = query.data.split("_")[1]
        price = get_crypto_price(symbol)
        if not price: return
        context.user_data.update({'coin': symbol, 'price': price})
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"🪙 <b>{symbol} Market</b>\nPrice: <code>${price:.4f}</code>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    elif query.data.startswith("dir_"):
        direction = "UP" if query.data.split("_")[1] == "up" else "DOWN"
        await query.edit_message_text(f"🚀 <b>Trade Executed!</b> ({direction})\nWait 30s... ⏳", parse_mode='HTML')
        asyncio.create_task(process_bet(context, query.from_user.id, context.user_data['coin'], context.user_data['price'], query.data.split("_")[1]))

if __name__ == '__main__':
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL}/{TOKEN}")
