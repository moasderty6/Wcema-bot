import os
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiohttp import web
import asyncio

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # مثال: https://your-app-name.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get("PORT", 8080))
CHANNEL_USERNAME = "p2p_LRN"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

headers = {"User-Agent": "Mozilla/5.0"}

# التحقق من الاشتراك في القناة
async def is_user_subscribed(user_id):
    try:
        member = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

# مواقع البحث
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

def find_movie_link(title):
    for site in [search_wecima, search_egybest, search_cima4u]:
        try:
            link = site(title)
            if link:
                return link
        except Exception as e:
            print(f"Error in {site.__name__}: {e}")
    return None

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
        await message.reply("❌ حدث خطأ أثناء المعالجة.")
        print("ERROR:", e)

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")

async def on_shutdown(dp):
    await bot.delete_webhook()
    await bot.session.close()  # <-- إغلاق جلسة aiohttp لتجنب الخطأ

if __name__ == "__main__":
    os.makedirs("downloads", exist_ok=True)
    async def main():
        await on_startup(dp)
        app = web.Application()
        app.router.add_post(WEBHOOK_PATH, dp)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        print(f"Running on {WEBHOOK_URL}")
        while True:
            await asyncio.sleep(3600)

    asyncio.run(main())
