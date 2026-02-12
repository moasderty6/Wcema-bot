import os
import asyncio
import logging
import httpx
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CMC_KEY = os.getenv("CMC_KEY") # اختياري لجلب السعر
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- STRINGS ---
STRINGS = {
    "en": {
        "welcome": "<b>👋 Welcome to TradeBot!</b>",
        "dashboard": "<b>💎 Dashboard</b>\n\n💰 Points: <code>{}</code>\n📊 Trades: <code>{}</code>\n🏆 Wins: <code>{}</code>\n🔗 Wallet: <code>{}</code>",
        "trade_btn": "🎲 Start Trade",
        "wallet_btn": "💳 Set Wallet",
        "lang_btn": "🌐 Language",
        "set_wallet_msg": "📌 Send your USDT TRC20 address:",
        "wallet_saved": "✅ Wallet Saved!",
        "trade_start": "⏳ Trade started at ${}\nWaiting 60s...",
        "win": "✅ WIN! Price: ${}\n+250 Points",
        "loss": "❌ LOSS! Price: ${}\n-100 Points"
    },
    "ar": {
        "welcome": "<b>👋 أهلاً بك في بوت التداول!</b>",
        "dashboard": "<b>💎 لوحة التحكم</b>\n\n💰 النقاط: <code>{}</code>\n📊 الصفقات: <code>{}</code>\n🏆 الفوز: <code>{}</code>\n🔗 المحفظة: <code>{}</code>",
        "trade_btn": "🎲 بدء التداول",
        "wallet_btn": "💳 تعيين المحفظة",
        "lang_btn": "🌐 تغيير اللغة",
        "set_wallet_msg": "📌 أرسل عنوان محفظة USDT TRC20:",
        "wallet_saved": "✅ تم الحفظ بنجاح!",
        "trade_start": "⏳ بدأت الصفقة بسعر ${}\nانتظر 60 ثانية...",
        "win": "✅ ربح! السعر: ${}\n+250 نقطة",
        "loss": "❌ خسارة! السعر: ${}\n-100 نقطة"
    }
}

# --- DATABASE ---
class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    points INT DEFAULT 1000,
                    trades INT DEFAULT 0,
                    wins INT DEFAULT 0,
                    wallet TEXT,
                    lang TEXT DEFAULT 'en',
                    is_trading BOOLEAN DEFAULT FALSE
                )
            """)

    async def get_user(self, user_id):
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                await conn.execute("INSERT INTO users (user_id) VALUES ($1)", user_id)
                return await self.get_user(user_id)
            return user

    async def update_user(self, user_id, **kwargs):
        columns = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys())])
        values = list(kwargs.values())
        async with self.pool.acquire() as conn:
            await conn.execute(f"UPDATE users SET {columns} WHERE user_id = $1", user_id, *values)

db = Database()

# --- UTILS ---
async def get_btc_price():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
            return float(r.json()['price'])
    except: return 60000.0

# --- KEYBOARDS ---
def get_main_kb(user):
    lang = user['lang'] or 'en'
    txt = STRINGS[lang]
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=txt["trade_btn"], callback_data="trade"))
    builder.row(
        InlineKeyboardButton(text=txt["wallet_btn"], callback_data="set_wallet"),
        InlineKeyboardButton(text=txt["lang_btn"], callback_data="show_langs")
    )
    return builder.as_markup()

# --- HANDLERS ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = await db.get_user(message.from_user.id)
    lang = user['lang']
    txt = STRINGS[lang]
    usdt = user['points'] / 1000
    dashboard = txt["dashboard"].format(user['points'], user['trades'], user['wins'], user['wallet'] or "---")
    await message.answer(f"{txt['welcome']}\n\n{dashboard}", reply_markup=get_main_kb(user), parse_mode="HTML")

@dp.callback_query(F.data == "show_langs")
async def show_langs(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🇺🇸 English", callback_data="set_lang_en"))
    builder.add(InlineKeyboardButton(text="🇸🇦 العربية", callback_data="set_lang_ar"))
    await callback.message.edit_text("Choose Language / اختر اللغة:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_lang(callback: types.CallbackQuery):
    new_lang = callback.data.split("_")[2]
    await db.update_user(callback.from_user.id, lang=new_lang)
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text(STRINGS[new_lang]["welcome"], reply_markup=get_main_kb(user), parse_mode="HTML")

@dp.callback_query(F.data == "trade")
async def start_trade(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    lang = user['lang']
    if user['is_trading']: return await callback.answer("❌ Trade in progress")
    if user['points'] < 100: return await callback.answer("❌ Need 100 points")

    entry_price = await get_btc_price()
    await db.update_user(callback.from_user.id, is_trading=True, points=user['points']-100, trades=user['trades']+1)
    
    msg = await callback.message.answer(STRINGS[lang]["trade_start"].format(entry_price))
    await asyncio.sleep(60)
    
    exit_price = await get_btc_price()
    win = exit_price > entry_price
    new_points = 250 if win else 0
    
    await db.update_user(callback.from_user.id, is_trading=False, points=(await db.get_user(user['user_id']))['points'] + new_points, wins=user['wins'] + (1 if win else 0))
    
    result_txt = STRINGS[lang]["win" if win else "loss"].format(exit_price)
    await msg.reply(result_txt)
    user = await db.get_user(callback.from_user.id)
    await msg.answer(STRINGS[lang]["welcome"], reply_markup=get_main_kb(user), parse_mode="HTML")

@dp.message()
async def handle_text(message: types.Message):
    if message.text.startswith("T") and len(message.text) > 30:
        await db.update_user(message.from_user.id, wallet=message.text)
        user = await db.get_user(message.from_user.id)
        await message.reply(STRINGS[user['lang']]["wallet_saved"])

async def main():
    await db.connect()
    # الحذف التلقائي للـ Webhook لحل مشكلة التعارض
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Webhook deleted. Starting Polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
