import logging
import os
import asyncio
import time
import aiohttp
from aiohttp import web
import asyncpg
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters, PreCheckoutQueryHandler
)

# --- Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6172153716"))
CMC_KEY = os.environ.get("CMC_KEY") # اختياري لجلب السعر من CoinMarketCap

# --- Constants ---
TRADE_DURATION = 60  # مدة الصفقة بالثواني
MIN_BET = 50        # أقل مبلغ للرهان بالنجوم
WIN_MULTIPLIER = 1.8 # العائد (180%)

# --- Global DB Pool ---
DB_POOL = None

# --- States ---
ADD_STARS_STATE, SET_WALLET_STATE, TRADING_AMOUNT_STATE = range(3)

# --- Database functions ---
async def init_db():
    async with DB_POOL.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance BIGINT DEFAULT 100, -- رصيد تجريبي بسيط عند البدء
                ton_wallet TEXT,
                total_deposits BIGINT DEFAULT 0,
                total_trades INT DEFAULT 0,
                total_wins INT DEFAULT 0
            )
        """)

async def get_user_data(user_id: int) -> dict:
    async with DB_POOL.acquire() as conn:
        data = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not data:
            await conn.execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            data = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    return dict(data)

async def update_user_data(user_id: int, **kwargs):
    set_clauses = [f"{key} = ${i+2}" for i, key in enumerate(kwargs.keys())]
    query = f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = $1"
    async with DB_POOL.acquire() as conn:
        await conn.execute(query, user_id, *kwargs.values())

# --- Price Fetcher ---
async def get_btc_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT") as resp:
                data = await resp.json()
                return float(data['price'])
    except:
        return 65000.0 # سعر افتراضي في حال فشل الاتصال

# --- Keyboards ---
def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📈 Trade (Up/Down)"), KeyboardButton("🌟 Add Funds")],
        [KeyboardButton("👤 Profile"), KeyboardButton("🏧 Withdraw")],
        [KeyboardButton("💼 Wallet")]
    ], resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await get_user_data(user_id)
    await update.message.reply_text(
        "Welcome to BTC Predictor! 🚀\nTrade Bitcoin price movements and win Stars.", 
        reply_markup=main_menu_keyboard()
    )

async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_info = await get_user_data(update.effective_user.id)
    text = (
        f"👤 Account Profile:\n"
        f"- ID: {user_info['user_id']}\n"
        f"- Balance: {user_info['balance']} ⭐\n"
        f"- Total Trades: {user_info['total_trades']}\n"
        f"- Total Wins: {user_info['total_wins']}\n"
        f"- Wallet: {user_info['ton_wallet'] or 'Not Set'}"
    )
    await update.message.reply_text(text)

# --- Trading Logic ---
async def trade_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Enter the amount of Stars to trade (Min: {MIN_BET}):",
        reply_markup=cancel_keyboard()
    )
    return TRADING_AMOUNT_STATE

async def get_trade_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await start(update, context)
        return ConversationHandler.END
    
    try:
        amount = int(update.message.text)
        user_info = await get_user_data(update.effective_user.id)
        
        if amount < MIN_BET:
            await update.message.reply_text(f"Min trade is {MIN_BET} Stars.")
            return TRADING_AMOUNT_STATE
        if amount > user_info['balance']:
            await update.message.reply_text("Insufficient balance!")
            return TRADING_AMOUNT_STATE
            
        context.user_data["trade_amount"] = amount
        keyboard = [
            [InlineKeyboardButton("📈 UP", callback_data="trade_up"),
             InlineKeyboardButton("📉 DOWN", callback_data="trade_down")]
        ]
        await update.message.reply_text(
            f"Predict BTC movement for the next {TRADE_DURATION}s:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("Please enter a valid number.")
        return TRADING_AMOUNT_STATE

async def process_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    direction = "up" if query.data == "trade_up" else "down"
    amount = context.user_data.get("trade_amount")
    
    user_info = await get_user_data(user_id)
    if amount > user_info['balance']:
        await query.edit_message_text("Error: Insufficient balance.")
        return

    # خصم المبلغ وبدء الصفقة
    entry_price = await get_btc_price()
    await update_user_data(user_id, balance=user_info['balance'] - amount, total_trades=user_info['total_trades'] + 1)
    
    await query.edit_message_text(
        f"⏳ Trade Active!\n"
        f"Amount: {amount} ⭐\n"
        f"Direction: {direction.upper()}\n"
        f"Entry Price: ${entry_price:,.2f}\n"
        f"Result in {TRADE_DURATION} seconds..."
    )
    
    # انتظار انتهاء المدة
    await asyncio.sleep(TRADE_DURATION)
    
    exit_price = await get_btc_price()
    win = False
    if direction == "up" and exit_price > entry_price: win = True
    elif direction == "down" and exit_price < entry_price: win = True
    
    user_info = await get_user_data(user_id) # تحديث البيانات بعد الخصم
    if win:
        prize = int(amount * WIN_MULTIPLIER)
        await update_user_data(user_id, balance=user_info['balance'] + prize, total_wins=user_info['total_wins'] + 1)
        result_text = f"✅ WIN!\nPrice went from ${entry_price:,.2f} to ${exit_price:,.2f}.\nYou won {prize} Stars!"
    else:
        result_text = f"❌ LOSS\nPrice went from ${entry_price:,.2f} to ${exit_price:,.2f}.\nYou lost {amount} Stars."
    
    await context.bot.send_message(chat_id=user_id, text=result_text, reply_markup=main_menu_keyboard())

# --- Wallet & Withdraw --- (نفس منطق كودك الأصلي)
async def wallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send your TON wallet address:", reply_markup=cancel_keyboard())
    return SET_WALLET_STATE

async def set_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await start(update, context)
    await update_user_data(update.effective_user.id, ton_wallet=update.message.text)
    await update.message.reply_text("✅ Wallet updated!", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# --- Stars Deposit --- (Telegram Stars)
async def add_fund_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter Stars to add (min 100):", reply_markup=cancel_keyboard())
    return ADD_STARS_STATE

async def get_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await start(update, context)
    try:
        amt = int(update.message.text)
        await context.bot.send_invoice(
            update.effective_chat.id, "Buy Stars", f"Add {amt} Stars", "payload", "", "XTR", [LabeledPrice("Stars", amt)]
        )
    except: pass
    return ADD_STARS_STATE

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def success_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt = update.message.successful_payment.total_amount
    u = await get_user_data(update.effective_user.id)
    await update_user_data(u['user_id'], balance=u['balance'] + amt, total_deposits=u['total_deposits'] + amt)
    await update.message.reply_text(f"✅ Added {amt} Stars!", reply_markup=main_menu_keyboard())

# --- Main App ---
async def main():
    global DB_POOL
    DB_POOL = await asyncpg.create_pool(DATABASE_URL)
    await init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversations
    trade_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📈 Trade"), trade_start)],
        states={TRADING_AMOUNT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_trade_amount)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel"), start)]
    )
    
    deposit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🌟 Add Funds"), add_fund_start)],
        states={ADD_STARS_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_deposit_amount)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel"), start)]
    )

    wallet_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💼 Wallet"), wallet_start)],
        states={SET_WALLET_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_wallet)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancel"), start)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^👤 Profile"), profile_handler))
    application.add_handler(trade_conv)
    application.add_handler(deposit_conv)
    application.add_handler(wallet_conv)
    application.add_handler(CallbackQueryHandler(process_trade, pattern="^trade_"))
    application.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success_payment))

    # Webhook Setup
    PORT = int(os.environ.get("PORT", 8080))
    URL = os.environ.get("RENDER_EXTERNAL_URL")
    
    await application.initialize()
    if URL: await application.bot.set_webhook(url=f"{URL}/{BOT_TOKEN}")

    async def telegram_webhook(request):
        data = await request.json()
        await application.process_update(Update.de_json(data, application.bot))
        return web.Response(text="OK")

    webapp = web.Application()
    webapp.router.add_post(f"/{BOT_TOKEN}", telegram_webhook)
    webapp.router.add_get("/", lambda r: web.Response(text="Bot is running!"))
    
    runner = web.AppRunner(webapp)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=PORT).start()
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
