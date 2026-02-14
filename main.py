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
    # منح الرصيد التجريبي للمستخدم المطلوب
    c.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", (565965404, 'Tester', 100000, 'Not Set'))
    c.execute("UPDATE users SET balance = 100000 WHERE id = 565965404")
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
        amount = 500 if win else -500 # رفعنا قيمة الربح والخصارة للتشويق
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
        await context.bot.send_message(user_id, "⚠️ Network Error. Points returned.")

# --- المعالجات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Space_Traveler"
    
    if not get_user(user_id):
        if context.args:
            try:
                ref_id = int(context.args[0])
                if get_user(ref_id):
                    update_balance(ref_id, 200) # مكافأة أعلى للدعوة
                    await context.bot.send_message(ref_id, "🚀 <b>New Pilot Joined!</b> You earned 200 Pts.", parse_mode='HTML')
            except: pass
        save_user(user_id, username, 1000, "Not Set")

    keyboard = [
        ['🎮 Bet Now'],
        ['💼 Wallet', '👤 Account'],
        ['🏧 Withdraw', '📢 Earn Points']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"🌕 <b>Welcome to Bybit Moonbix!</b>\n\nExplore the galaxy of crypto and earn points by predicting the market moves. 🚀",
        reply_markup=reply_markup, parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user: return

    if text == '👤 Account':
        msg = (f"🚀 <b>Moonbix Pilot Profile</b>\n\n"
               f"🆔 ID: <code>{user[0]}</code>\n"
               f"💰 Balance: <b>{user[2]:,} Pts</b>\n"
               f"💵 Value: <b>${user[2]/1000:.2f} USDT</b>\n"
               f"🏦 Wallet: <code>{user[3]}</code>")
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == '🎮 Bet Now':
        # تم تبديل ماتيك بـ TON
        coins = ['BTC', 'ETH', 'BNB', 'SOL', 'TON', 'XRP', 'DOT', 'DOGE', 'AVAX', 'ADA']
        keyboard = [[InlineKeyboardButton(f"🪙 {c}", callback_data=f"bet_{c}")] for c in coins]
        await update.message.reply_text("✨ <b>Choose your Asset:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif text == '💼 Wallet':
        await update.message.reply_text("🔗 <b>Wallet Setup</b>\nPlease send your <b>TRC20</b> address to receive your rewards:", parse_mode='HTML')
        context.user_data['waiting_for_wallet'] = True

    elif text == '🏧 Withdraw':
        if user[2] < 10000:
            await update.message.reply_text(
                f"⚠️ <b>Access Denied!</b>\n\nMinimum fuel required for withdrawal is <b>10,000 Pts</b>.\n"
                f"Your current fuel: <b>{user[2]:,} Pts</b>.\n\nKeep trading to reach the moon! 🚀", 
                parse_mode='HTML'
            )
        elif user[3] == "Not Set":
            await update.message.reply_text("❌ <b>Wallet Missing!</b>\nPlease set your TRC20 address first using the 💼 Wallet button.", parse_mode='HTML')
        else:
            await update.message.reply_text(
                f"✅ <b>Ready for Takeoff!</b>\n\nAvailable: {user[2]:,} Pts\n"
                f"Please enter the amount you want to withdraw (Min 10,000):",
                parse_mode='HTML'
            )
            context.user_data['waiting_for_withdraw_amount'] = True

    elif text == '📢 Earn Points':
        bot_info = await context.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (f"🎁 <b>Moonbix Referral Program</b>\n\n"
               f"Invite friends and get <b>200 Points</b> instantly!\n\n"
               f"🔗 <b>Your Invite Link:</b>\n{share_link}")
        await update.message.reply_text(msg, parse_mode='HTML', disable_web_page_preview=True)

    elif context.user_data.get('waiting_for_wallet'):
        save_user(user_id, user[1], user[2], text)
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text("✅ <b>Wallet Connected!</b> Your future rewards will be sent to this address.", parse_mode='HTML')

    elif context.user_data.get('waiting_for_withdraw_amount'):
        try:
            amount = int(text)
            if amount < 10000:
                await update.message.reply_text("⚠️ <b>Invalid Amount!</b>\nMinimum withdrawal is 10,000 Pts. Please try again.")
            elif amount > user[2]:
                await update.message.reply_text(f"❌ <b>Insufficient Balance!</b>\nYou are trying to withdraw {amount:,} Pts, but you only have {user[2]:,} Pts.")
            else:
                update_balance(user_id, -amount)
                context.user_data['waiting_for_withdraw_amount'] = False
                await update.message.reply_text(f"🎊 <b>Withdrawal Request Sent!</b>\n\n{amount:,} Pts are now being processed. Our team will review it within 24 hours.", parse_mode='HTML')
                
                admin_msg = (f"🔔 <b>NEW WITHDRAWAL</b>\n\nPilot: @{user[1]}\nID: <code>{user[0]}</code>\nAmount: {amount:,} Pts\nWallet: <code>{user[3]}</code>")
                await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode='HTML')
        except:
            await update.message.reply_text("❌ <b>Error!</b> Please enter a numeric value only.")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("bet_"):
        symbol = query.data.split("_")[1]
        price = get_crypto_price(symbol)
        if not price:
            await query.edit_message_text("❌ Data error. Try another coin.")
            return
        context.user_data.update({'coin': symbol, 'price': price})
        keyboard = [[InlineKeyboardButton("📈 BULLISH (UP)", callback_data="dir_up"), 
                     InlineKeyboardButton("📉 BEARISH (DOWN)", callback_data="dir_down")]]
        await query.edit_message_text(f"🪙 <b>{symbol} Market</b>\nCurrent Price: <code>${price:.4f}</code>\n\nPredict the move in 30 seconds:", 
                                     reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    elif query.data.startswith("dir_"):
        direction = "UP" if query.data.split("_")[1] == "up" else "DOWN"
        symbol = context.user_data['coin']
        price = context.user_data['price']
        await query.edit_message_text(f"🚀 <b>Trade Executed!</b>\n\nPair: {symbol}/USDT\nPosition: {direction}\nWaiting for moon results... ⏳", parse_mode='HTML')
        asyncio.create_task(process_bet(context, query.from_user.id, symbol, price, query.data.split("_")[1]))

if __name__ == '__main__':
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL}/{TOKEN}")
