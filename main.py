import os
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

# ================= CONFIG =================
API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # https://your-app.onrender.com
PORT = int(os.getenv("PORT") or 10000)

WEBHOOK_PATH = f"/bot/{API_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

CHANNEL_USERNAME = "p2p_LRN"

logging.basicConfig(level=logging.INFO)

# ================= BOT =================
bot = Bot(API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

user_state = {}

# ================= UI =================
def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🇦🇪 عربي", callback_data="ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data="en")]
    ])

def type_kb(lang):
    t = {"ar": ["🎬 فيلم", "📺 مسلسل"], "en": ["🎬 Movie", "📺 Series"]}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t[lang][0], callback_data="movie"),
         InlineKeyboardButton(t[lang][1], callback_data="series")]
    ])

# ================= HELPERS =================
async def is_subscribed(uid):
    try:
        m = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", uid)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

# ================= HANDLERS =================
@dp.message(F.command == "start")
async def start(m: types.Message):
    user_state[m.from_user.id] = {}
    await m.answer("اختر اللغة / Choose language", reply_markup=lang_kb())

@dp.callback_query()
async def cb(q: types.CallbackQuery):
    uid = q.from_user.id
    user_state.setdefault(uid, {})
    data = q.data

    if data in ("ar", "en"):
        user_state[uid]["lang"] = data
        await q.message.edit_text("فيلم أم مسلسل؟" if data=="ar" else "Movie or Series?",
                                  reply_markup=type_kb(data))

    elif data in ("movie", "series"):
        if not await is_subscribed(uid):
            await q.message.answer("❗ اشترك بالقناة أولاً")
            return
        user_state[uid]["type"] = data
        await q.message.answer("📌 اكتب الاسم")

@dp.message(F.text)
async def text(m: types.Message):
    uid = m.from_user.id
    if uid not in user_state:
        await m.answer("/start")
        return

    st = user_state[uid]

    if "title" not in st:
        st["title"] = m.text
        if st["type"] == "series":
            await m.answer("📌 رقم الحلقة")
        else:
            await m.answer(f"🎬 {st['title']}\nhttps://example.com/watch")
            user_state.pop(uid)
    else:
        await m.answer(f"📺 {st['title']} - Ep {m.text}\nhttps://example.com/watch")
        user_state.pop(uid)

# ================= WEB SERVER =================
async def healthcheck(request):
    return web.Response(text="OK")  # Render يحتاج هذا

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("Webhook set")

async def on_shutdown(app):
    await bot.delete_webhook()

async def main():
    app = web.Application()

    # Route عشان Render (GET /)
    app.router.add_get("/", healthcheck)

    # Telegram Webhook (POST)
    SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logging.info("🚀 Webhook bot running")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())