import os
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("API_TOKEN")  # أضفه في متغيرات Render
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

headers = {"User-Agent": "Mozilla/5.0"}

# ========= الموقع 1: Wecima =========
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

# ========= الموقع 2: EgyBest =========
def search_egybest(movie_name):
    url = f"https://egybest.ltd/search/?q={movie_name.replace(' ', '+')}"
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("a.movie a")
    if not link: return None

    page = requests.get(link["href"], headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")
    iframe = soup.find("iframe")
    if iframe: return iframe.get("src")
    return None

# ========= الموقع 3: Cima4u =========
def search_cima4u(movie_name):
    url = f"https://my.cima4u.ws/search/{movie_name.replace(' ', '%20')}"
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("h3.title a")
    if not link: return None

    page = requests.get(link["href"], headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")
    iframe = soup.find("iframe")
    if iframe: return iframe.get("src")
    return None

# ========= دمج البحث في كل المواقع =========
def find_movie_link(title):
    for site in [search_wecima, search_egybest, search_cima4u]:
        try:
            link = site(title)
            if link:
                return link
        except Exception as e:
            print(f"Error in {site.__name__}: {e}")
    return None

# ========= المعالجة على تيليغرام =========
@dp.message_handler()
async def handle(message: types.Message):
    title = message.text.strip()
    await message.reply("🔍 جاري البحث عن الفيلم في عدة مواقع...")

    try:
        video_url = find_movie_link(title)
        if not video_url:
            return await message.reply("❌ لم أجد رابط للمشاهدة.")

        # إذا كان رابط مباشر للفيديو mp4 نحاول تحميله
        if video_url.endswith(".mp4"):
            video_data = requests.get(video_url, stream=True)
            filename = "video.mp4"
            with open(filename, "wb") as f:
                for chunk in video_data.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            with open(filename, "rb") as video:
                await bot.send_video(message.chat.id, video, caption=f"🎬 {title}")
            os.remove(filename)
        else:
            await message.reply(f"🎬 {title}\n🔗 رابط المشاهدة:\n{video_url}")

    except Exception as e:
        await message.reply("❌ حدث خطأ أثناء البحث أو التنزيل.")
        print("ERROR:", e)

# ========= تشغيل البوت =========
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
