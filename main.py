import os
import requests
import logging
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # مثال: https://your-app-name.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_PORT = int(os.getenv("PORT", default=8080))
WEBAPP_HOST = "0.0.0.0"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

def find_video_url(movie_title):
    slug = movie_title.replace(" ", "-")
    search_url = f"https://wecima.org/?s={slug}"
    r = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("h2.entry-title a")
    if not link:
        return None
    page = requests.get(link["href"], headers={"User-Agent": "Mozilla/5.0"})
    sp = BeautifulSoup(page.text, "html.parser")
    video_tag = sp.find("iframe") or sp.find("video")
    if not video_tag:
        return None
    return video_tag.get("src") or video_tag.get("data-src")

@dp.message_handler()
async def handle(message: types.Message):
    title = message.text.strip()
    await message.reply("🔍 أبحث في وي سيما...")
    try:
        video_url = find_video_url(title)
        if not video_url:
            return await message.reply("❌ لم أجد رابط مشاهدة مباشر.")
        await message.reply(f"🎬 {title}\n🔗 الرابط:\n{video_url}")
    except Exception as e:
        await message.reply("❌ حدث خطأ أثناء المعالجة.")
        print("ERROR:", e)

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
