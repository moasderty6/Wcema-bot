import os
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("API_TOKEN")
REQUIRED_CHANNEL = "@p2p_LRN"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

headers = {"User-Agent": "Mozilla/5.0"}

def search_wecima(movie_name):
    query = movie_name.replace(" ", "+")
    url = f"https://wecima.show/?s={query}"
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("h2.entry-title a")
    if not link:
        return None

    page = requests.get(link["href"], headers=headers)
    soup = BeautifulSoup(page.text, "html.parser")
    iframe = soup.find("iframe")
    return iframe["src"] if iframe else None

def find_movie_link(title):
    try:
        return search_wecima(title)
    except Exception as e:
        print("Error during scraping:", e)
        return None

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.is_chat_member() or member.status in ["member", "administrator", "creator"]
    except:
        return False

@dp.message_handler()
async def handle(message: types.Message):
    user_id = message.from_user.id
    if not await check_subscription(user_id):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"))
        await message.reply("🔒 يجب عليك الاشتراك في القناة أولاً!", reply_markup=keyboard)
        return

    title = message.text.strip()
    await message.reply("🔍 جاري البحث عن الفيلم...")

    try:
        video_url = find_movie_link(title)
        if not video_url:
            await message.reply("❌ لم أجد رابط للمشاهدة.")
        else:
            await message.reply(f"🎬 {title}\n🔗 رابط المشاهدة:\n{video_url}")
    except Exception as e:
        print("ERROR:", e)
        await message.reply("❌ حدث خطأ أثناء المعالجة.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
