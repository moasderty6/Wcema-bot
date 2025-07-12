import os
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiohttp import web
import asyncio

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get("PORT", 8080))
CHANNEL_USERNAME = "p2p_LRN"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

headers = {"User-Agent": "Mozilla/5.0"}

# التحقق من الاشتراك
async def is_user_subscribed(user_id):
    try:
        member = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# البحث عن الفيديو
def search_wecima(movie_name):
    url = f"https://wecima.show/?s={movie_name.replace(' ', '+')}"
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("h2.entry-title a")
    if not link: return None
    page = requests.get(link["href"], headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")
    iframe = soup.find("iframe")
    if iframe: return iframe.get("src")
    return None

def find_movie_link(title):
    try:
        return search_wecima(title)
    except Exception as e:
        print(f"Search error: {e}")
        return None

# رسالة المستخدم
@dp.message_handler()
async def handle(message: types.Message):
    user_id = message.from_user.id
    title = message.text.strip()

    if not await is_user_subscribed(user_id):
        join_button = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("اشترك في القناة 📢", url=f"https://t.me/{CHANNEL_USERNAME}")
        )
        await message.reply("❗ يجب عليك الاشتراك في القناة أولاً لتحميل الفيلم.", reply_markup=join_button)
        return

    await message.reply("🔍 جاري البحث عن الفيلم...")

    try:
        video_url = find_movie_link(title)
        if not video_url:
            return await message.reply("❌ لم أجد رابط للمشاهدة.")

        await message.reply(f"🎬 {title}\n🔗 رابط المشاهدة:\n{video_url}")
    except Exception as e:
        await message.reply("❌ حدث خطأ أثناء المعالجة.")
        print("ERROR:", e)

# Webhook route
async def webhook_handler(request):
    try:
        data = await request.json()
        update = Update.to_object(data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Failed to handle update: {e}")
    return web.Response()

# Webhook startup
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to {WEBHOOK_URL}")

# Webhook shutdown
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()

# Main app
async def main():
    await on_startup()
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"Running on {WEBHOOK_URL}")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
