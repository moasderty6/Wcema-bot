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
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DB MANAGEMENT ---
def init_db():
    conn = sqlite3.connect("data.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, 
            username TEXT,
            points INT DEFAULT 1000, 
            wallet TEXT
        )
    """)
    conn.commit()
    conn.close()

def sync_user(uid, username):
    conn = sqlite3.connect("data.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (id, username) VALUES (?, ?)", (uid, username))
        conn.commit()
        return sync_user(uid, username)
    conn.close()
    return user

# --- PRICE UTILS ---
async def get_btc_price():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
            return float(r.json()['price'])
    except Exception as e:
        logger.error(f"Price error: {e}")
        return 0.0

# --- BOT SETUP ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📈 High", callback_data="trade_up"), 
                InlineKeyboardButton(text="📉 Low", callback_data="trade_down"))
    builder.row(InlineKeyboardButton(text="💳 Set Wallet", callback_data="set_wallet"))
    builder.row(InlineKeyboardButton(text="💸 Withdraw", callback_data="withdraw"))
    builder.row(InlineKeyboardButton(text="🔄 Refresh Dashboard", callback_data="refresh"))
    return builder.as_markup()

async def send_dashboard(message_or_call, user_id, username):
    user = sync_user(user_id, username)
    points = user[2]
    usdt = points / 1000
    wallet = user[3] if user[3] else "Not Set"
    
    text = (
        f"<b>💎 USER DASHBOARD</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {username}\n"
        f"💰 <b>Points:</b> <code>{points}</code>\n"
        f"💵 <b>Balance:</b> <code>{usdt:.2f} USDT</code>\n"
        f"🔗 <b>TRC20:</b> <code>{wallet}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎮 <b>Predict BTC price in 60s:</b>"
    )
    
    if isinstance(message_or_call, types.Message):
        await message_or_call.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    else:
        try:
            await message_or_call.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
        except:
            pass

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await send_dashboard(message, message.from_user.id, message.from_user.full_name)

@dp.callback_query(F.data == "refresh")
async def refresh_cb(call: types.CallbackQuery):
    await send_dashboard(call, call.from_user.id, call.from_user.full_name)
    await call.answer()

@dp.callback_query(F.data.startswith("trade_"))
async def trade_handler(call: types.CallbackQuery):
    user = sync_user(call.from_user.id, call.from_user.full_name)
    if user[2] < 100:
        return await call.answer("❌ Need at least 100 points!", show_alert=True)
    
    prediction = call.data.split("_")[1] # up or down
    entry_price = await get_btc_price()
    
    if entry_price == 0:
        return await call.answer("❌ Price API Error, try later")

    # خصم النقاط فوراً
    conn = sqlite3.connect("data.db")
    conn.execute("UPDATE users SET points = points - 100 WHERE id = ?", (user[0],))
    conn.commit()

    await call.message.edit_text(
        f"✅ <b>Trade Active!</b>\n"
        f"Type: {'🚀 High' if prediction == 'up' else '🔻 Low'}\n"
        f"Entry: ${entry_price}\n"
        f"⏳ Waiting 60 seconds...",
        parse_mode="HTML"
    )
    
    await asyncio.sleep(60)
    
    exit_price = await get_btc_price()
    win = False
    if prediction == "up" and exit_price > entry_price: win = True
    elif prediction == "down" and exit_price < entry_price: win = True
    
    reward = 200 if win else 0 # يرجع الـ 100 وفوقها 100 ربح
    if win:
        conn.execute("UPDATE users SET points = points + ? WHERE id = ?", (reward, user[0]))
        conn.commit()
    
    result_text = "🎉 <b>YOU WIN!</b>" if win else "💀 <b>YOU LOST!</b>"
    await call.message.answer(
        f"{result_text}\n"
        f"━━━━━━━━━━━━━━\n"
        f"Entry: ${entry_price}\n"
        f"Exit: ${exit_price}\n"
        f"Change: {exit_price - entry_price:.2f}$",
        parse_mode="HTML"
    )
    await send_dashboard(call, call.from_user.id, call.from_user.full_name)

@dp.callback_query(F.data == "set_wallet")
async def set_wallet_call(call: types.CallbackQuery):
    await call.message.answer("📩 Please send your <b>USDT TRC20</b> address:", parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "withdraw")
async def withdraw_call(call: types.CallbackQuery):
    user = sync_user(call.from_user.id, call.from_user.full_name)
    if user[2] < 10000:
        await call.answer("❌ Minimum withdrawal is 10,000 points (10 USDT)", show_alert=True)
    elif not user[3]:
        await call.answer("❌ Set your wallet address first!", show_alert=True)
    else:
        # هنا يمكنك إضافة كود لإرسال طلب السحب للآدمن
        await call.message.answer(f"✅ Withdrawal request for {user[2]/1000:.2f} USDT sent to admin!")
    await call.answer()

@dp.message()
async def text_handler(message: types.Message):
    # تحقق بسيط إذا كان النص هو عنوان محفظة
    if len(message.text) > 30 and message.text.startswith("T"):
        conn = sqlite3.connect("data.db")
        conn.execute("UPDATE users SET wallet = ? WHERE id = ?", (message.text, message.from_user.id))
        conn.commit()
        await message.reply("✅ TRC20 Wallet Address Saved!")
        await send_dashboard(message, message.from_user.id, message.from_user.full_name)

# --- FASTAPI SERVER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(url=WEBHOOK_URL)
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
    return {"status": "Bot is active"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
