import os
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- STRINGS ---
STRINGS = {
    "en": {
        "welcome": "<b>👋 Welcome to TradeBot!</b>\nChoose an option:",
        "dashboard": "<b>💎 Dashboard</b>\n\n💰 Points: <code>{}</code>\n📊 Trades: <code>{}</code>\n🏆 Wins: <code>{}</code>\n🔗 Wallet: <code>{}</code>",
        "trade_btn": "🎲 Start Trade",
        "wallet_btn": "💳 Set Wallet",
        "lang_btn": "🌐 Language",
        "set_wallet_msg": "📌 Please send your USDT TRC20 address:",
        "wallet_saved": "✅ Wallet Saved!",
    },
    "ar": {
        "welcome": "<b>👋 أهلاً بك في بوت التداول!</b>\nاختر من القائمة:",
        "dashboard": "<b>💎 لوحة التحكم</b>\n\n💰 النقاط: <code>{}</code>\n📊 الصفقات: <code>{}</code>\n🏆 الفوز: <code>{}</code>\n🔗 المحفظة: <code>{}</code>",
        "trade_btn": "🎲 بدء التداول",
        "wallet_btn": "💳 تعيين المحفظة",
        "lang_btn": "🌐 تغيير اللغة",
        "set_wallet_msg": "📌 من فضلك أرسل عنوان محفظة USDT TRC20 الخاص بك:",
        "wallet_saved": "✅ تم حفظ المحفظة بنجاح!",
    }
}

# --- DATABASE ---
class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        # تفعيل SSL ضروري لمنصات مثل Render
        self.pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    points INT DEFAULT 1000,
                    trades INT DEFAULT 0,
                    wins INT DEFAULT 0,
                    wallet TEXT,
                    lang TEXT DEFAULT 'en'
                )
            """)

    async def get_user(self, user_id):
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                await conn.execute("INSERT INTO users (user_id) VALUES ($1)", user_id)
                return await self.get_user(user_id)
            return user

    async def update_user(self, user_id, column, value):
        async with self.pool.acquire() as conn:
            await conn.execute(f"UPDATE users SET {column} = $1 WHERE user_id = $2", value, user_id)

db = Database()

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
    await message.answer(STRINGS[lang]["welcome"], reply_markup=get_main_kb(user), parse_mode="HTML")

@dp.callback_query(F.data == "show_langs")
async def show_langs(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🇺🇸 English", callback_data="set_lang_en"))
    builder.add(InlineKeyboardButton(text="🇸🇦 العربية", callback_data="set_lang_ar"))
    await callback.message.edit_text("Choose Language / اختر اللغة:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_lang(callback: types.CallbackQuery):
    new_lang = callback.data.split("_")[2]
    await db.update_user(callback.from_user.id, "lang", new_lang)
    user = await db.get_user(callback.from_user.id)
    await callback.message.edit_text(STRINGS[new_lang]["welcome"], reply_markup=get_main_kb(user), parse_mode="HTML")

@dp.callback_query(F.data == "set_wallet")
async def set_wallet_prompt(callback: types.CallbackQuery, state: any):
    user = await db.get_user(callback.from_user.id)
    lang = user['lang']
    await callback.message.answer(STRINGS[lang]["set_wallet_msg"])
    # ملاحظة: في aiogram 3 نستخدم FSM لمحفظة المستخدم، هنا سنبسطها باستقبال أي رسالة نصية تالية

@dp.message()
async def global_message_handler(message: types.Message):
    # إذا كانت الرسالة تبدو كعنوان محفظة (تبدأ بـ T وطولها > 30)
    if message.text.startswith("T") and len(message.text) > 30:
        await db.update_user(message.from_user.id, "wallet", message.text)
        user = await db.get_user(message.from_user.id)
        lang = user['lang']
        await message.reply(STRINGS[lang]["wallet_saved"])
        await message.answer(STRINGS[lang]["welcome"], reply_markup=get_main_kb(user), parse_mode="HTML")

async def main():
    await db.connect()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
