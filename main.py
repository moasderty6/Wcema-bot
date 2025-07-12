import os
import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # https://your-app-name.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
CHANNEL_USERNAME = "p2p_LRN"
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

headers = {"User-Agent": "Mozilla/5.0"}

async def is_user_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

def search_wecima(movie_name):
    try:
        url = f"https://wecima.show/?s={movie_name.replace(' ', '+')}"
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.select_one("h2.entry-title a")
        if not link:
            return None
        page = requests.get(link["href"], headers=headers, timeout=10)
        soup = BeautifulSoup(page.text, "html.parser")
        iframe = soup.find("iframe")
        if iframe:
            return iframe.get("src")
        return None
    except Exception as e:
        print("Scraping Error:", e)
        return None

@dp.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    movie_name = message.text.strip()

    # تحقق من الاشتراك
    if not await is_user_subscribed(user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك أولاً في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")]
        ])
        await message.answer("❗ يجب الاشتراك في القناة أولاً لتحميل الفيلم.", reply_markup=kb)
        return

    await message.answer("🔍 جارٍ البحث عن الفيلم...")

    video_url = await asyncio.to_thread(search_wecima, movie_name)

    if not video_url:
        await message.answer("❌ لم أجد رابط للمشاهدة.")
    else:
        await message.answer(f"🎬 <b>{movie_name}</b>\n🔗 <code>{video_url}</code>")

# Webhook startup
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook set to: {WEBHOOK_URL}")

# Webhook shutdown
async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    print("❌ Webhook removed")

# تشغيل التطبيق
async def main():
    app = web.Application()
    app["bot"] = bot

    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    app.on_shutdown.append(lambda _: on_shutdown(bot))

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("🚀 Bot is running...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    import requests
    asyncio.run(main())
