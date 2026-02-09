import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import openai

# --- إعدادات ---
API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # مثال: https://your-service.onrender.com
WEBHOOK_PATH = f"/bot/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
CHANNEL_USERNAME = "p2p_LRN"
PORT = int(os.getenv("PORT", 8080))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ===== قاعدة بيانات مؤقتة لحالة المستخدم =====
user_state = {}

# ===== رسائل حسب اللغة =====
messages = {
    "choose_lang": {"ar": "اختر اللغة / Choose Language:", "en": "Choose your language / اختر اللغة:"},
    "choose_type": {"ar": "هل تريد بحث عن فيلم أم مسلسل؟", "en": "Do you want a Movie or Series?"},
    "enter_title": {"ar": "📌 أرسل اسم الفيلم أو المسلسل:", "en": "📌 Send the Movie or Series title:"},
    "enter_episode": {"ar": "📌 أرسل رقم الحلقة:", "en": "📌 Send the episode number:"},
    "not_subscribed": {"ar": "❗ يجب الاشتراك في القناة أولاً:", "en": "❗ You must subscribe to the channel first:"},
    "searching": {"ar": "🔍 جاري البحث...", "en": "🔍 Searching..."},
    "not_found": {"ar": "❌ لم أتمكن من العثور على رابط للفيلم/الحلقة.", "en": "❌ Could not find a link for the movie/episode."}
}

# ===== Inline Keyboard =====
def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🇦🇪 عربي", callback_data="lang_ar"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
    ])

def type_keyboard(lang):
    text = {"ar": ["فيلم", "مسلسل"], "en": ["Movie", "Series"]}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text[lang][0], callback_data="type_movie"),
         InlineKeyboardButton(text[lang][1], callback_data="type_series")]
    ])

# ===== Helpers =====
async def is_user_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

async def get_ai_correct_title(title: str, content_type: str) -> str:
    """Use OpenAI API to correct/normalize the movie/series title"""
    try:
        prompt = f"Find the correct name for this {content_type}: '{title}' and return just the title."
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=prompt,
            max_tokens=30
        )
        corrected = response.choices[0].text.strip()
        if corrected:
            return corrected
        return title
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return title  # fallback

async def search_links(title: str, content_type: str) -> str | None:
    """Mock function: replace with real scraping/API"""
    return f"https://example.com/watch/{title.replace(' ', '_')}"

# ===== Handlers =====
@dp.message(F.command == "start")
async def start(message: types.Message):
    user_id = message.from_user.id
    user_state[user_id] = {}
    await message.answer(messages["choose_lang"]["en"], reply_markup=lang_keyboard())

@dp.callback_query(F.data)
async def callback_handler(query: types.CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if user_id not in user_state:
        user_state[user_id] = {}

    if data.startswith("lang_"):
        lang = "ar" if data=="lang_ar" else "en"
        user_state[user_id]["lang"] = lang
        await query.message.edit_text(messages["choose_type"][lang], reply_markup=type_keyboard(lang))

    elif data.startswith("type_"):
        content_type = "movie" if data=="type_movie" else "series"
        user_state[user_id]["type"] = content_type
        lang = user_state[user_id]["lang"]

        if not await is_user_subscribed(user_id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{CHANNEL_USERNAME}")]
            ])
            await query.message.edit_text(messages["not_subscribed"][lang], reply_markup=kb)
            return

        await query.message.edit_text(messages["enter_title"][lang])

@dp.message(F.text)
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_state:
        await message.answer("❗ Please press /start first")
        return

    state = user_state[user_id]
    lang = state.get("lang", "en")

    if "title" not in state:
        # Movie or Series title
        state["title"] = message.text.strip()
        corrected_title = await get_ai_correct_title(state["title"], state["type"])
        state["title"] = corrected_title

        if state["type"] == "series":
            await message.answer(messages["enter_episode"][lang])
        else:
            await message.answer(messages["searching"][lang])
            link = await search_links(corrected_title, "movie")
            if link:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton("🎬 Watch", url=link)]
                ])
                await message.answer(f"🎬 <b>{corrected_title}</b>", reply_markup=kb)
            else:
                await message.answer(messages["not_found"][lang])
            user_state.pop(user_id)

    else:
        # Series episode
        if state["type"] == "series":
            state["episode"] = message.text.strip()
            await message.answer(messages["searching"][lang])
            link = await search_links(f"{state['title']}_E{state['episode']}", "series")
            if link:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton("🎬 Watch Episode", url=link)]
                ])
                await message.answer(f"🎬 <b>{state['title']} - Episode {state['episode']}</b>", reply_markup=kb)
            else:
                await message.answer(messages["not_found"][lang])
            user_state.pop(user_id)

# ===== Webhook Setup =====
async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to: {WEBHOOK_URL}")

async def on_shutdown(app: web.Application):
    logging.info("Shutting down...")

async def main():
    logging.basicConfig(level=logging.INFO)
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"🚀 Bot running on port {PORT}...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
