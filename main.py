
import os
import logging
import requests
import subprocess
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

def extract_video_link(movie_name):
    search_url = f"https://wecima.org/?s={movie_name.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    first_result = soup.select_one("h2.entry-title a")
    if not first_result:
        return None
    movie_page = requests.get(first_result["href"], headers=headers)
    soup = BeautifulSoup(movie_page.text, "html.parser")
    iframe = soup.find("iframe")
    return iframe["src"] if iframe else None

@dp.message_handler()
async def handle_movie(message: types.Message):
    movie = message.text.strip()
    await message.reply("🔍 جاري البحث عن الفيلم...")
    try:
        video_url = extract_video_link(movie)
        if not video_url:
            return await message.reply("❌ لم أجد رابط للمشاهدة.")

        await message.reply("⬇️ جاري التحميل من المصدر...")

        filename = "movie.mp4"
        subprocess.run(["yt-dlp", "-o", filename, video_url], check=True)

        if os.path.exists(filename):
            with open(filename, "rb") as vid:
                await bot.send_video(message.chat.id, vid, caption=f"🎬 {movie}")
            os.remove(filename)
        else:
            await message.reply("⚠️ لم أتمكن من تحميل الفيديو.")
    except Exception as e:
        await message.reply("❌ حدث خطأ أثناء المعالجة.")
        print("ERROR:", e)

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    executor.start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )
