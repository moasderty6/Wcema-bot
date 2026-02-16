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

# --- الإعدادات (تأكدي من إضافتها في Render Environment) ---
TOKEN = os.environ.get('BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL') 
PORT = int(os.environ.get('PORT', 5000))
DATABASE_URL = os.environ.get('DATABASE_URL')
ADMIN_ID = 6172153716 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- إدارة قاعدة بيانات PostgreSQL ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id BIGINT PRIMARY KEY, 
                      username TEXT, 
                      balance INTEGER DEFAULT 1000, 
                      wallet TEXT DEFAULT 'Not Set')''')
        conn.commit()
        c.close()
        conn.close()
        logging.info("Database initialized successfully.")
    except Exception as e:
        logging.error(f"Database Init Error: {e}")

def get_user(user_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, username, balance, wallet FROM users WHERE id=%s", (user_id,))
        user = c.fetchone()
        c.close()
        conn.close()
        return user
    except:
        return None

def save_user(user_id, username, balance, wallet):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (id, username, balance, wallet) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT (id) DO UPDATE SET username=%s, wallet=%s
    """, (user_id, username, balance, wallet, username, wallet))
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

# --- جلب السعر من بايننس مع معالجة الأخطاء ---
def get_crypto_price(symbol):
    try:
        # بعض العملات قد تختلف تسميتها، لذا نضمن الصيغة الصحيحة
        s = symbol.strip().upper()
        if s == "TON": s = "TON" # بايننس أضافت TON مؤخراً
        
        ticker = f"{s}USDT"
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={ticker}"
        
        response = requests.get(url, timeout=8)
        data = response.json()
        
        if 'price' in data:
            return float(data['price'])
        else:
            logging.error(f"Binance API returned: {data}")
            return None
    except Exception as e:
        logging.error(f"Fetch Price Error: {e}")
        return None

# --- معالجة الرهان (30 ثانية) ---
async def process_bet(context, user_id, symbol, entry_price, direction):
    await asyncio.sleep(30)
    exit_price = get_crypto_price(symbol)
    
    if exit_price is not None:
        if exit_price == entry_price:
            status = "🟡 DRAW! Price unchanged."
            msg = (f"🏆 <b>{symbol} Trade Result</b>\n"
                   f"━━━━━━━━━━━━━━\n"
                   f"📉 Entry: <code>${entry_price:.4f}</code>\n"
                   f"📈 Exit: <code>${exit_price:.4f}</code>\n"
                   f"━━━━━━━━━━━━━━\n"
                   f"<b>{status}</b>\nPoints returned!")
        else:
            win = (direction == "up" and exit_price > entry_price) or (direction == "down" and exit_price < entry_price)
            amount = 200 if win else -200 
            update_balance(user_id, amount)
            
            status = "🟢 WINNER! +200 Pts" if win else "🔴 LOSS! -200 Pts"
            msg = (f"🏆 <b>{symbol} Trade Result</b>\n"
                   f"━━━━━━━━━━━━━━\n"
                   f"📉 Entry: <code>${entry_price:.4f}</code>\n"
                   f"📈 Exit: <code>${exit_price:.4f}</code>\n"
                   f"━━━━━━━━━━━━━━\n"
                   f"<b>{status}</b>")
        
        await context.bot.send_message(user_id, msg, parse_mode='HTML')
    else:
        # في حال فشل جلب سعر الخروج، لا نخصم نقاط
        await context.bot.send_message(user_id, "⚠️ Network error at exit. Your points are safe.")

# --- الأوامر الأساسية ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"Pilot_{user_id}"
    
    user = get_user(user_id)
    if not user:
        if context.args:
            try:
                ref_id = int(context.args[0])
                if get_user(ref_id):
                    update_balance(ref_id, 200)
                    await context.bot.send_message(ref_id, "🚀 <b>New Pilot Joined!</b> You earned 200 Pts.", parse_mode='HTML')
            except: pass
        save_user(user_id, username, 1000, "Not Set")

    keyboard = [['🎮 Bet Now'], ['💼 Wallet', '👤 Account'], ['🏧 Withdraw', '📢 Earn Points']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"🌕 <b>Welcome to Binance Moonbix!</b>\n\nExplore the galaxy of crypto and earn points by predicting the market moves. 🚀",
        reply_markup=reply_markup, parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user: return

    if text == '👤 Account':
        msg = (f"🚀 <b>Moonbix Pilot: @{user[1]}</b>\n"
               f"━━━━━━━━━━━━━━\n"
               f"🆔 ID: <code>{user[0]}</code>\n"
               f"💰 Balance: <b>{user[2]:,} Pts</b>\n"
               f"💵 Value: <b>${user[2]/1000:.2f} USDT</b>\n"
               f"🏦 Wallet(TRC20): <code>{user[3]}</code>")
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == '🎮 Bet Now':
        if user[2] < 200:
            bot_info = await context.bot.get_me()
            share_link = f"https://t.me/{bot_info.username}?start={user_id}"
            await update.message.reply_text(f"❌ <b>Insufficient Balance!</b>\n\nInvite friends:\n{share_link}", parse_mode='HTML')
            return
        coins = ['BTC', 'ETH', 'BNB', 'SOL', 'TON', 'XRP', 'ADA', 'DOGE']
        keyboard = [[InlineKeyboardButton(f"🪙 {c}", callback_data=f"bet_{c}")] for c in coins]
        await update.message.reply_text("✨ <b>Choose your Asset:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif text == '💼 Wallet':
        await update.message.reply_text("🔗 <b>Wallet Setup</b>\nPlease send your <b>TRC20</b> address:", parse_mode='HTML')
        context.user_data['waiting_for_wallet'] = True

    elif text == '🏧 Withdraw':
        if user[2] < 10000:
            await update.message.reply_text(f"⚠️ <b>Access Denied!</b>\nMin: 10,000 Pts.\nYou: {user[2]:,} Pts.", parse_mode='HTML')
        elif user[3] == "Not Set":
            await update.message.reply_text("❌ <b>Wallet Missing!</b>", parse_mode='HTML')
        else:
            await update.message.reply_text(f"✅ <b>Ready!</b>\nEnter amount to withdraw:", parse_mode='HTML')
            context.user_data['waiting_for_withdraw_amount'] = True

    elif text == '📢 Earn Points':
        bot_info = await context.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start={user_id}"
        await update.message.reply_text(f"🎁 <b>Invite Link:</b>\n{share_link}", parse_mode='HTML')

    elif context.user_data.get('waiting_for_wallet'):
        save_user(user_id, user[1], user[2], text)
        context.user_data['waiting_for_wallet'] = False
        await update.message.reply_text("✅ <b>Wallet Connected!</b>", parse_mode='HTML')

    elif context.user_data.get('waiting_for_withdraw_amount'):
        try:
            amount = int(text)
            if amount < 10000 or amount > user[2]:
                await update.message.reply_text("❌ <b>Invalid Amount!</b>")
            else:
                update_balance(user_id, -amount)
                context.user_data['waiting_for_withdraw_amount'] = False
                await update.message.reply_text(f"🎊 <b>Request Sent!</b>", parse_mode='HTML')
                await context.bot.send_message(ADMIN_ID, f"🔔 <b>WITHDRAW</b>\nUser: @{user[1]}\nAmount: {amount}\nWallet: {user[3]}", parse_mode='HTML')
        except:
            await update.message.reply_text("❌ Enter numbers only.")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    await query.answer()
    
    if query.data.startswith("bet_"):
        symbol = query.data.split("_")[1]
        price = get_crypto_price(symbol)
        if price is None:
            await query.edit_message_text("❌ Binance API Busy. Try again in a moment.")
            return
        context.user_data.update({'coin': symbol, 'price': price})
        keyboard = [[InlineKeyboardButton("📈 UP", callback_data="dir_up"), InlineKeyboardButton("📉 DOWN", callback_data="dir_down")]]
        await query.edit_message_text(f"🪙 <b>{symbol}</b>: <code>${price:.4f}</code>\nPredict 30s move:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    elif query.data.startswith("dir_"):
        direction = query.data.split("_")[1]
        await query.edit_message_text(f"🚀 <b>Trade Live!</b>\n30s remaining... ⏳", parse_mode='HTML')
        asyncio.create_task(process_bet(context, user_id, context.user_data['coin'], context.user_data['price'], direction))

if __name__ == '__main__':
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(bet_callback))
    
    # التشغيل النهائي
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL}/{TOKEN}")
