import os
import logging
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.client.default import DefaultBotProperties # <--- تم استيراد هذا
from aiohttp import web

# --- الإعدادات الأساسية ---
API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = f"/bot/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
CHANNEL_USERNAME = "p2p_LRN"
PORT = int(os.getenv("PORT", 8080))

# --- إعداد البوت ---
# <--- تم تعديل هذا السطر ليوافق الإصدار الجديد
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- دوال مساعدة ---
async def is_user_subscribed(user_id: int) -> bool:
    """التحقق من اشتراك المستخدم في القناة"""
    try:
        member = await bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.error(f"Error checking subscription for {user_id}: {e}")
        return False

async def search_wecima_async(session: aiohttp.ClientSession, movie_name: str) -> str | None:
    """البحث عن رابط الفيلم باستخدام aiohttp"""
    search_url = f"https://wecima.show/search/{movie_name.replace(' ', '+')}/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

    try:
        # 1. البحث عن الفيلم
        async with session.get(search_url, headers=headers, timeout=15) as response:
            if response.status != 200:
                logging.error(f"Search failed with status: {response.status}")
                return None
            
            soup = BeautifulSoup(await response.text(), "html.parser")
            movie_link_tag = soup.select_one("div.Grid--WecimaPosts div.Thumb--Grid a")
            if not movie_link_tag or not movie_link_tag.has_attr('href'):
                logging.warning(f"No movie link found for '{movie_name}'")
                return None
            
            movie_page_url = movie_link_tag['href']

        # 2. الدخول لصفحة الفيلم وجلب رابط المشاهدة
        async with session.get(movie_page_url, headers=headers, timeout=15) as page_response:
            if page_response.status != 200:
                logging.error(f"Movie page failed with status: {page_response.status}")
                return None

            soup = BeautifulSoup(await page_response.text(), "html.parser")
            iframe = soup.find("iframe", {"name": "watch_iframe"})
            if iframe and iframe.has_attr('src'):
                return iframe['src']
            
            logging.warning(f"No iframe found on page: {movie_page_url}")
            return None

    except Exception as e:
        logging.error(f"Scraping Error for '{movie_name}': {e}")
        return None

# --- معالجات الرسائل ---
@dp.message(F.text)
async def handle_message(message: Message, session: aiohttp.ClientSession):
    user_id = message.from_user.id
    movie_name = message.text.strip()

    if not await is_user_subscribed(user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك أولاً في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")]
        ])
        await message.answer("❗ يجب الاشتراك في القناة أولاً للبحث عن الفيلم.", reply_markup=kb)
        return

    msg = await message.answer("🔍 جارٍ البحث عن فيلمك...")
    
    video_url = await search_wecima_async(session, movie_name)

    if video_url:
        await msg.edit_text(f"🎬 <b>{movie_name}</b>\n\n🔗 رابط المشاهدة المباشر:\n<code>{video_url}</code>")
    else:
        await msg.edit_text(f"❌ عذراً, لم أتمكن من العثور على رابط مشاهدة للفيلم: <b>{movie_name}</b>")

# --- إعداد وتشغيل Webhook ---
async def on_startup(bot: Bot, app: web.Application):
    await bot.set_webhook(WEBHOOK_URL, secret_token=API_TOKEN)
    logging.info(f"Webhook set to: {WEBHOOK_URL}")

async def main():
    logging.basicConfig(level=logging.INFO)

    dp["session"] = aiohttp.ClientSession()

    app = web.Application()
    app.on_startup.append(lambda a: on_startup(bot, a))

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"🚀 Bot is running on port {PORT}...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")

