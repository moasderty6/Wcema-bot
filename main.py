import os
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from aiohttp import web

# إعداد المتغيرات البيئية من Render
API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # مثل: https://your-app-name.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get("PORT", 8080))

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

headers = {"User-Agent": "Mozilla/5.0"}
CHANNEL_USERNAME = "p2p_LRN"

# التحقق من الاشتراك في القناة
async def is_user_subscribed(user_id):
    try:
        member = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# البحث في Wecima
def search_wecima(movie_name):
    url = f"https://wecima.show/?s={movie_name.replace(' ', '+')}"
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("h2.entry-title a")
    if not link:
        return None
    page = requests.get(link["href"], headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")
    iframe = soup.find("iframe")
    if iframe:
        return iframe.get("src")
    return None

# البحث في Egybest
def search_egybest(movie_name):
    url = f"https://egybest.ltd/search/?q={movie_name.replace(' ', '+')}"
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("a.movie a")
    if not link:
        return None
    page = requests.get(link["href"], headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")
    iframe = soup.find("iframe")
    if iframe:
        return iframe.get("src")
    return None

# البحث في Cima4u
def search_cima4u(movie_name):
    url = f"https://my.cima4u.ws/search/{movie_name.replace(' ', '%20')}"
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("h3.title a")
    if not link:
        return None
    page = requests.get(link["href"], headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")
    iframe = soup.find("iframe")
    if iframe:
        return iframe.get("src")
    return None

# البحث في كل المواقع بالتسلسل
def find_movie_link(title):
    for site in [search_wecima, search_egybest, search_cima4u]:
        try:
            link = site(title)
            if link:
                return link
        except Exception as e:
            print(f"Error in {site.__name__}: {e}")
    return None

# المعالجة الرئيسية للرسائل
@dp.message_handler()
async def handle(message: types.Message):
    user_id = message.from_user.id
    title = message.text.strip()

    if not await is_user_subscribed(user_id):
        join_button = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")
        )
        await message.reply("❗ يجب عليك الاشتراك في القناة أولاً لتحميل الفيلم.", reply_markup=join_button)
        return

    await message.reply("🔍 جاري البحث عن الفيلم...")

    try:
        video_url = find_movie_link(title)
        if not video_url:
            return await message.reply("❌ لم أجد رابط للمشاهدة.")

        # إذا كان رابط مباشر لـ mp4 نحاول إرساله مباشرة
        if video_url.endswith(".mp4"):
            video_data = requests.get(video_url, stream=True)
            filename = "video.mp4"
            with open(filename, "wb") as f:
                for chunk in video_data.iter_content(chunk_size=1024 * 1024):
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

# بدء البوت
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

# الرد على الصفحة الرئيسية /
async def index(request):
    return web.Response(text="🚀 Movie Bot is Running!")

# إطلاق السيرفر
if __name__ == "__main__":
    os.makedirs("downloads", exist_ok=True)
    app = web.Application()
    app.router.add_get("/", index)

    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=PORT,
        web_app=app
    )
