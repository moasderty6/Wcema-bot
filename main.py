import os
import asyncio
import logging
import httpx
import sqlite3
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, Update
from fastapi import FastAPI, Request
import uvicorn

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") # Example: https://bot.onrender.com
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DB (SQLite for stability) ---
def init_db():
    conn = sqlite3.connect("data.db")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, points INT DEFAULT 1000, trades INT DEFAULT 0, wins INT DEFAULT 0, wallet TEXT)")
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect("data.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (id) VALUES (?)", (uid,))
        conn.commit()
        return get_user(uid)
    conn.close()
    return user

# --- BOT SETUP ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

def main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Start Trade", callback_data="trade"))
    builder.row(InlineKeyboardButton(text="💳 Set Wallet", callback_data="set_wallet"))
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = get_user(message.from_user.id)
    await message.answer(f"<b>TradeBot Active!</b>\nPoints: {user[1]}", reply_markup=main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "trade")
async def handle_trade(callback: types.CallbackQuery):
    await callback.answer("Trading...")
    await callback.message.answer("⏳ Trade result in 30s...")

@dp.message()
async def save_wallet(message: types.Message):
    if len(message.text) > 25:
        conn = sqlite3.connect("data.db")
        conn.execute("UPDATE users SET wallet = ? WHERE id = ?", (message.text, message.from_user.id))
        conn.commit()
        await message.reply("✅ Wallet updated!")

# --- FASTAPI LIFESPAN ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # أهم خطوة: تنظيف الويب هوك القديم وإعداد الجديد
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")
    yield
    await bot.delete_webhook()

app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"status": "ok"}

@app.get("/")
async def index():
    return {"status": "Bot is running"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
