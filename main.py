import os
import logging
import asyncio
from groq import AsyncGroq
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from urllib.parse import urlparse

# ========= الإعدادات =========
API_TOKEN = os.getenv("API_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CHANNEL_USERNAME = "p2p_LRN"

# الرابط الكامل من إعدادات ريندر (مثال: https://app.onrender.com/telegram)
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

# استخراج المسار تلقائياً (سيكون غالباً /telegram)
WEBHOOK_PATH = urlparse(WEBHOOK_URL).path if WEBHOOK_URL else "/telegram"

# إعداد Groq بشكل غير متزامن
client = AsyncGroq(api_key=GROQ_API_KEY)

# إعداد البوت
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)
user_state = {}

# ========= النصوص ولوحة المفاتيح =========
TXT = {
    "choose_lang": {"ar": "اختر اللغة:", "en": "Choose language:"},
    "choose_type": {"ar": "فيلم أم مسلسل؟", "en": "Movie or Series?"},
    "enter_title": {"ar": "📌 اكتب اسم العمل بدقة:", "en": "📌 Send the exact title:"},
    "enter_episode": {"ar": "📌 رقم الحلقة:", "en": "📌 Episode number:"},
    "searching": {"ar": "🔍 جاري معالجة الاسم والبحث...", "en": "🔍 Processing and searching..."},
    "not_sub": {"ar": "❗ يجب عليك الاشتراك في القناة لاستخدام البوت:\n@p2p_LRN", 
                "en": "❗ You must subscribe to the channel first:\n@p2p_LRN"},
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

# ========= الوظائف المساعدة =========
async def is_subscribed(user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def ai_fix_title(title: str) -> str:
    """تصحيح اسم الفيلم باستخدام ذكاء Groq الاصطناعي"""
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a movie database assistant. Return ONLY the official title of the movie or series provided, with its release year if possible. No chat, no intro."},
                {"role": "user", "content": title}
            ],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return title

def generate_link(name: str) -> str:
    """توليد رابط تجريبي"""
    clean_name = name.replace(" ", "_").replace(":", "")
    return f"https://example.com/watch/{clean_name}"

# ========= المعالجات (Handlers) =========
@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    user_state[msg.from_user.id] = {}
    await msg.answer(TXT["choose_lang"]["en"], reply_markup=lang_kb())

@dp.callback_query()
async def callback_handler(q: types.CallbackQuery):
    uid = q.from_user.id
    data = q.data
    user_state.setdefault(uid, {})

    if data.startswith("lang_"):
        lang = "ar" if "ar" in data else "en"
        user_state[uid]["lang"] = lang
        await q.message.edit_text(TXT["choose_type"][lang], reply_markup=type_kb(lang))

    elif data in ("movie", "series"):
        # فحص الاشتراك قبل المتابعة
        if not await is_subscribed(uid):
            lang = user_state[uid].get("lang", "en")
            await q.answer(TXT["not_sub"][lang], show_alert=True)
            return
        
        user_state[uid]["type"] = data
        lang = user_state[uid].get("lang", "en")
        await q.message.answer(TXT["enter_title"][lang])

@dp.message()
async def handle_text(msg: types.Message):
    uid = msg.from_user.id
    if uid not in user_state or "lang" not in user_state[uid]:
        return

    state = user_state[uid]
    lang = state.get("lang", "en")

    if "type" not in state:
        await msg.answer(TXT["choose_type"][lang], reply_markup=type_kb(lang))
        return

    if "title" not in state:
        # المستخدم أرسل الاسم
        await msg.answer(TXT["searching"][lang])
        fixed_title = await ai_fix_title(msg.text)
        state["title"] = fixed_title
        
        if state["type"] == "series":
            await msg.answer(TXT["enter_episode"][lang])
        else:
            link = generate_link(fixed_title)
            await msg.answer(f"🎬 <b>{fixed_title}</b>\n\n🔗 {link}")
            user_state.pop(uid, None)
    else:
        # المستخدم أرسل رقم الحلقة
        episode = msg.text
        full_name = f"{state['title']} Episode {episode}"
        await msg.answer(TXT["searching"][lang])
        link = generate_link(full_name)
        await msg.answer(f"📺 <b>{state['title']}</b>\n📌 Episode: {episode}\n\n🔗 {link}")
        user_state.pop(uid, None)

# ========= إعداد السيرفر والـ Webhook =========
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logging.info(f"Webhook set to: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    await client.close() # إغلاق اتصال Groq

def main():
    app = web.Application()
    # رابط فحص الحالة (Health Check)
    app.router.add_get("/", lambda r: web.Response(text="Bot is Active and Running!"))
    
    # ربط تليجرام بالمسار المستخرج
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
