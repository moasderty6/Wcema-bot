import os
import logging
import asyncio
import openai
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

# ========= SETTINGS =========
API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHANNEL_USERNAME = "p2p_LRN"

openai.api_key = OPENAI_API_KEY

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

# ========= USER STATE =========
user_state = {}

# ========= MESSAGES =========
TXT = {
    "choose_lang": {"ar": "اختر اللغة:", "en": "Choose language:"},
    "choose_type": {"ar": "فيلم أم مسلسل؟", "en": "Movie or Series?"},
    "enter_title": {"ar": "📌 اكتب الاسم:", "en": "📌 Send title:"},
    "enter_episode": {"ar": "📌 رقم الحلقة:", "en": "📌 Episode number:"},
    "searching": {"ar": "🔍 جاري البحث...", "en": "🔍 Searching..."},
    "not_sub": {"ar": "❗ اشترك بالقناة أولاً", "en": "❗ Subscribe first"},
}

# ========= KEYBOARDS =========
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
async def subscribed(user_id):
    try:
        m = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

async def ai_fix(title):
    try:
        res = openai.Completion.create(
            model="text-davinci-003",
            prompt=f"Correct movie or series title: {title}",
            max_tokens=20
        )
        return res.choices[0].text.strip() or title
    except:
        return title

def fake_link(name):
    return f"https://example.com/watch/{name.replace(' ', '_')}"

# ========= HANDLERS =========
@dp.message(F.command == "start")
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
            await q.message.answer(TXT["not_sub"]["en"])
            return
        user_state[uid]["type"] = data
        await q.message.answer(TXT["enter_title"][user_state[uid]["lang"]])

@dp.message(F.text)
async def text_handler(msg: types.Message):
    uid = msg.from_user.id
    if uid not in user_state:
        await msg.answer("اكتب /start")
        return

    st = user_state[uid]
    lang = st.get("lang", "en")

    if "title" not in st:
        st["title"] = await ai_fix(msg.text)

        if st["type"] == "series":
            await msg.answer(TXT["enter_episode"][lang])
        else:
            await msg.answer(TXT["searching"][lang])
            link = fake_link(st["title"])
            await msg.answer(f"🎬 <b>{st['title']}</b>\n{link}")
            user_state.pop(uid)

    else:
        ep = msg.text
        await msg.answer(TXT["searching"][lang])
        link = fake_link(f"{st['title']}_E{ep}")
        await msg.answer(f"📺 <b>{st['title']} – Ep {ep}</b>\n{link}")
        user_state.pop(uid)

# ========= RUN =========
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())