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
logging.basicConfig(level=logging.INFO)

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# إضافة sslmode=require للرابط لضمان عدم انقطاع الاتصال
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TRADE_DURATION = 60 
WIN_MULTIPLIER = 1.8

# --- Global DB Pool ---
DB_POOL = None

# --- States ---
ADD_STARS_STATE, SET_WALLET_STATE, TRADING_AMOUNT_STATE = range(3)

# --- Database functions ---
async def init_db():
    async with DB_POOL.acquire() as conn:
        # قمت بتحديث الجدول ليتطابق مع الـ Unpacking (7 قيم)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance BIGINT DEFAULT 1000,
                trades_count INT DEFAULT 0,
                wins_count INT DEFAULT 0,
                ton_wallet TEXT,
                active_trade BOOLEAN DEFAULT FALSE,
                total_deposits BIGINT DEFAULT 0
            )
        """)

async def get_user_data(user_id: int):
    async with DB_POOL.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not row:
            await conn.execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return row

async def get_btc_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT") as resp:
                data = await resp.json()
                return float(data['price'])
    except:
        return 65000.0

# --- UI ---
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📈 ابدأ التداول"), KeyboardButton("🌟 شحن نجوم")],
        [KeyboardButton("👤 حسابي"), KeyboardButton("💼 المحفظة")]
    ], resize_keyboard=True)

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_data(update.effective_user.id)
    # حل مشكلة الـ Unpacking: استلام الصف كقاموس أو صف بدقة
    uid, balance, trades, wins, wallet, active, deposits = user
    
    await update.message.reply_text(
        f"مرحباً بك في بوت تداول البتكوين! 🚀\nرصيدك الحالي: {balance} نجمة",
        reply_markup=main_menu()
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_data(update.effective_user.id)
    text = (
        f"👤 تفاصيل حسابك:\n"
        f"💰 الرصيد: {user['balance']} نجمة\n"
        f"📊 عدد الصفقات: {user['trades_count']}\n"
        f"🏆 فوز: {user['wins_count']}\n"
        f"💳 المحفظة: {user['ton_wallet'] or 'غير مسجلة'}"
    )
    await update.message.reply_text(text)

async def trade_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أدخل عدد النجوم التي تريد المراهنة بها (أو اضغط إلغاء):", reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True))
    return TRADING_AMOUNT_STATE

async def trade_amount_rcv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ إلغاء":
        await start(update, context)
        return ConversationHandler.END
    
    try:
        amt = int(update.message.text)
        user = await get_user_data(update.effective_user.id)
        if amt > user['balance'] or amt < 50:
            await update.message.reply_text("عذراً، الرصيد غير كافٍ أو المبلغ أقل من 50.")
            return TRADING_AMOUNT_STATE
        
        context.user_data["t_amt"] = amt
        kb = [[InlineKeyboardButton("📈 صعود BTC", callback_data="up"), InlineKeyboardButton("📉 هبوط BTC", callback_data="down")]]
        await update.message.reply_text(f"اختر توقعك لسعر البتكوين بعد {TRADE_DURATION} ثانية:", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    except:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")

async def trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    direction = query.data
    amt = context.user_data.get("t_amt")
    
    entry_p = await get_btc_price()
    async with DB_POOL.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance - $1, trades_count = trades_count + 1 WHERE user_id = $2", amt, uid)
    
    await query.edit_message_text(f"✅ بدأت الصفقة!\nالسعر الحالي: ${entry_p:,.2f}\nالتوقع: {direction}\nانتظر {TRADE_DURATION} ثانية...")
    
    await asyncio.sleep(TRADE_DURATION)
    
    exit_p = await get_btc_price()
    win = (direction == "up" and exit_p > entry_p) or (direction == "down" and exit_p < entry_p)
    
    if win:
        prize = int(amt * WIN_MULTIPLIER)
        async with DB_POOL.acquire() as conn:
            await conn.execute("UPDATE users SET balance = balance + $1, wins_count = wins_count + 1 WHERE user_id = $2", prize, uid)
        res = f"🏆 فوز!\nالسعر ارتفع لـ ${exit_p:,.2f}\nربحت {prize} نجمة!"
    else:
        res = f"❌ خسارة!\nالسعر النهائي: ${exit_p:,.2f}\nخسرت {amt} نجمة."
        
    await context.bot.send_message(chat_id=uid, text=res, reply_markup=main_menu())

# --- Main App ---
async def main():
    global DB_POOL
    DB_POOL = await asyncpg.create_pool(DATABASE_URL)
    await init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^👤 حسابي"), profile))
    
    trade_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📈 ابدأ التداول"), trade_init)],
        states={TRADING_AMOUNT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, trade_amount_rcv)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ إلغاء"), start)]
    )
    app.add_handler(trade_conv)
    app.add_handler(CallbackQueryHandler(trade_callback))

    # Webhook
    PORT = int(os.environ.get("PORT", 8080))
    URL = os.environ.get("RENDER_EXTERNAL_URL")
    
    await app.initialize()
    if URL: await app.bot.set_webhook(url=f"{URL}/{BOT_TOKEN}")

    async def handle_webhook(request):
        data = await request.json()
        await app.process_update(Update.de_json(data, app.bot))
        return web.Response(text="OK")

    webapp = web.Application()
    webapp.router.add_post(f"/{BOT_TOKEN}", handle_webhook)
    webapp.router.add_get("/", lambda r: web.Response(text="Bot Running"))
    
    runner = web.AppRunner(webapp)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=PORT).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
