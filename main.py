import os
import logging
import asyncio
from groq import Groq
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

# ========= SETTINGS =========
API_TOKEN = os.getenv("API_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CHANNEL_USERNAME = "p2p_LRN"

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST") # مثال: https://your-app.onrender.com
WEBHOOK_PATH = "/telegram"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))

# إعداد Groq
client = Groq(api_key=GROQ_API_KEY)

# ===== Bot setup =====
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

user_state = {}

# ========= MESSAGES & KEYBOARDS (نفس منطقك السابق) =========
TXT = {
    "choose_lang": {"ar": "اختر اللغة:", "en": "Choose language:"},
    "choose_type": {"ar": "فيلم أم مسلسل؟", "en": "Movie or Series?"},
    "enter_title": {"ar": "📌 اكتب الاسم:", "en": "📌 Send title:"},
    "enter_episode": {"ar": "📌 رقم الحلقة:", "en": "📌 Episode number:"},
    "searching": {"ar": "🔍 جاري البحث...", "en": "🔍 Searching..."},
    "not_sub": {"ar": "❗ اشترك بالقناة أولاً \n @p2p_LRN", "en": "❗ Subscribe first \n @p2p_LRN"},
}

def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🇦🇪 عربي", callback_data="lang_ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
    ])

def type_kb(lang):
    t = {"ar": ["🎬 فيلم", "📺 مسلسل"], "en": ["🎬 Movie", "📺 Series"]}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t[lang][0], callback_data="movie"),
         InlineKeyboardButton(t[lang][1], callback_data="series")]
    ])

# ========= HELPERS =========
async def subscribed(user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def ai_fix(title: str) -> str:
    try:
        # استخدام Groq لتصحيح الاسم
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": f"Give me only the official movie or series name for: {title}. No explanation."}],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return title

def fake_link(name: str) -> str:
    return f"https://example.com/watch/{name.replace(' ', '_')}"

# ========= HANDLERS =========
@dp.message(CommandStart())
async def start(msg: types.Message):
    user_state[msg.from_user.id] = {}
    await msg.answer(TXT["choose_lang"]["en"], reply_markup=lang_kb())

@dp.callback_query()
async def cb(q: types.CallbackQuery):
    uid = q.from_user.id
    data = q.data
    user_state.setdefault(uid, {})

    if data.startswith("lang_"):
        lang = "ar" if "ar" in data else "en"
        user_state[uid]["lang"] = lang
        await q.message.edit_text(TXT["choose_type"][lang], reply_markup=type_kb(lang))

    elif data in ("movie", "series"):
        if not await subscribed(uid):
            lang = user_state[uid].get("lang", "en")
            await q.message.answer(TXT["not_sub"][lang])
            return
        user_state[uid]["type"] = data
        await q.message.answer(TXT["enter_title"][user_state[uid]["lang"]])

@dp.message()
async def text_handler(msg: types.Message):
    uid = msg.from_user.id
    if uid not in user_state or "lang" not in user_state[uid]:
        await msg.answer("Please start with /start")
        return

    st = user_state[uid]
    lang = st.get("lang", "en")

    if "type" not in st:
        await msg.answer(TXT["choose_type"][lang], reply_markup=type_kb(lang))
        return

    if "title" not in st:
        st["title"] = await ai_fix(msg.text)
        if st["type"] == "series":
            await msg.answer(TXT["enter_episode"][lang])
        else:
            await msg.answer(TXT["searching"][lang])
            link = fake_link(st["title"])
            await msg.answer(f"🎬 <b>{st['title']}</b>\n{link}")
            user_state.pop(uid, None)
    else:
        ep = msg.text
        await msg.answer(TXT["searching"][lang])
        link = fake_link(f"{st['title']}_E{ep}")
        await msg.answer(f"📺 <b>{st['title']} – Ep {ep}</b>\n{link}")
        user_state.pop(uid, None)

# ========= WEBHOOK SETUP =========
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

async def on_shutdown(app):
    await bot.delete_webhook()

def main():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running!"))
    
    # معالج الطلبات من تليجرام
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
