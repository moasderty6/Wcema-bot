import os
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.exceptions import ChatMemberInvalid

API_TOKEN = os.getenv("API_TOKEN")  # ضع توكن بوتك في متغيرات البيئة
CHANNEL_USERNAME = "@p2p_LRN"       # قناة الاشتراك الإلزامي

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

headers = {"User-Agent": "Mozilla/5.0"}

# دوال البحث في المواقع (wecima, egybest, cima4u)
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

def find_movie_link(title):
    for site in [search_wecima, search_egybest, search_cima4u]:
        try:
            link = site(title)
            if link:
                return link
        except Exception as e:
            print(f"Error in {site.__name__}: {e}")
    return None

# تحقق من الاشتراك في القناة
async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except ChatMemberInvalid:
        return False
    except Exception as e:
        print(f"Subscription check error: {e}")
        return False

@dp.message_handler()
async def handle(message: types.Message):
    user_id = message.from_user.id

    # تحقق الاشتراك بالقناة
    subscribed = await check_subscription(user_id)
    if not subscribed:
        await message.reply(f"❌ يجب عليك الاشتراك في القناة {CHANNEL_USERNAME} أولاً لمتابعة التحميل.")
        return

    title = message.text.strip()
    await message.reply("🔍 جاري البحث عن الفيلم في عدة مواقع...")

    try:
        video_url = find_movie_link(title)
        if not video_url:
            await message.reply("❌ لم أجد رابط للمشاهدة.")
            return

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

# إعدادات الـ webhook
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # مثال: https://your-app-name.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    print("Webhook set.")

async def on_shutdown(dp):
    await bot.delete_webhook()
    print("Webhook deleted.")

if __name__ == "__main__":
    import asyncio
    from aiogram import executor

    PORT = int(os.getenv("PORT", 8080))

    executor.start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=PORT,
    )
