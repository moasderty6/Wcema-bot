import os
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_polling
from aiohttp import web

API_TOKEN = os.getenv("API_TOKEN")  # ضعه في متغيرات ريندر
REQUIRED_CHANNEL = "@p2p_LRN"       # قناتك الإلزامية للاشتراك

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

headers = {"User-Agent": "Mozilla/5.0"}

# البحث في المواقع الثلاثة
def search_wecima(movie_name):
    try:
        url = f"https://wecima.show/?s={movie_name.replace(' ', '+')}"
        soup = BeautifulSoup(requests.get(url, headers=headers).text, "html.parser")
        link = soup.select_one("h2.entry-title a")
        if not link:
            return None
        page = requests.get(link["href"], headers=headers).text
        iframe = BeautifulSoup(page, "html.parser").find("iframe")
        return iframe.get("src") if iframe else None
    except:
        return None

def search_cima4u(movie_name):
    try:
        url = f"https://my.cima4u.ws/search/{movie_name.replace(' ', '%20')}"
        soup = BeautifulSoup(requests.get(url, headers=headers).text, "html.parser")
        link = soup.select_one("h3.title a")
        if not link:
            return None
        page = requests.get(link["href"], headers=headers).text
        iframe = BeautifulSoup(page, "html.parser").find("iframe")
        return iframe.get("src") if iframe else None
    except:
        return None

def search_egybest(movie_name):
    try:
        url = f"https://egybest.ltd/search/?q={movie_name.replace(' ', '+')}"
        soup = BeautifulSoup(requests.get(url, headers=headers).text, "html.parser")
        link = soup.select_one("a.movie a")
        if not link:
            return None
        page = requests.get(link["href"], headers=headers).text
        iframe = BeautifulSoup(page, "html.parser").find("iframe")
        return iframe.get("src") if iframe else None
    except:
        return None

# يجمع بين كل المواقع
def find_movie_link(title):
    for func in [search_wecima, search_cima4u, search_egybest]:
        link = func(title)
        if link:
            return link
    return None

# تحقق من الاشتراك في القناة
async def is_user_subscribed(user_id):
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'creator', 'administrator']
    except:
        return False

# رسالة الاشتراك
def get_subscription_keyboard():
    buttons = [
        [types.InlineKeyboardButton("🔔 اشترك الآن", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

# المعالجة
@dp.message_handler()
async def handle_message(message: types.Message):
    if not await is_user_subscribed(message.from_user.id):
        await message.reply("🚫 يجب الاشتراك في القناة أولاً لتحميل الفيلم:", reply_markup=get_subscription_keyboard())
        return

    title = message.text.strip()
    await message.reply("🔍 جاري البحث عن الفيلم...")

    try:
        video_url = find_movie_link(title)
        if not video_url:
            return await message.reply("❌ لم أجد رابط للمشاهدة.")

        if video_url.endswith(".mp4"):
            r = requests.get(video_url, stream=True)
            filename = "movie.mp4"
            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            with open(filename, "rb") as video:
                await bot.send_video(message.chat.id, video, caption=f"🎬 {title}")
            os.remove(filename)
        else:
            await message.reply(f"🎬 {title}\n🔗 رابط المشاهدة:\n{video_url}")

    except Exception as e:
        await message.reply("❌ حدث خطأ أثناء المعالجة.")
        print(f"Error: {e}")

# aiohttp web server لتشغيل البورت على Render
async def handle_webhook(request):
    return web.Response(text="✅ Bot is running")

def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_webhook)
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

# تشغيل البوت مع البورت
if __name__ == "__main__":
    import threading
    threading.Thread(target=start_web_server).start()
    start_polling(dp, skip_updates=True)
