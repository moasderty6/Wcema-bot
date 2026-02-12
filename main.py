import os
import asyncio
import requests
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

app = Flask(__name__)
users_db = {}

# صور تجميلية (يمكنك استبدال الروابط بصور خاصة بك)
IMG_WELCOME = "https://images.unsplash.com/photo-1621417646633-2fbf0627bb08?q=80&w=1000&auto=format&fit=crop"
IMG_TRADING = "https://cdn.pixabay.com/photo/2021/11/05/17/04/crypto-currency-6771741_1280.jpg"

STRINGS = {
    "ar": {
        "welcome": "<b>🌟 أهلاً بك في عالم Moonbix الاحترافي!</b>\n\n🎯 <b>رصيدك:</b> <code>{points}</code> نقطة\n📈 <b>نسبة الفوز:</b> <code>{win_rate}%</code>\n\n<i>تحدَّ السوق الآن وتوقع حركة BTC القادمة!</i>",
        "trade_up": "🚀 صعود (Long)", "trade_down": "📉 هبوط (Short)", "balance_btn": "💳 المحفظة", "lang_btn": "🇺🇸 English",
        "insufficient": "❌ <b>عذراً!</b> نقاطك غير كافية (تحتاج 100 نقطة على الأقل).",
        "recording": "<b>⌛️ تم دخول الصفقة بنجاح!</b>\n\n🔹 <b>الاتجاه:</b> {choice}\n🔹 <b>سعر الدخول:</b> <code>${price}</code>\n\n<i>جاري مراقبة الشارت لمدة 60 ثانية...</i>",
        "win": "<b>✅ صفقة ناجحة! (+150 نقطة)</b>\n\n💰 <b>السعر النهائي:</b> <code>${price}</code>\n🎊 لقد كنت محقاً، استمر في هذا الأداء!",
        "loss": "<b>❌ صفقة خاسرة! (-100 نقطة)</b>\n\n🔻 <b>السعر النهائي:</b> <code>${price}</code>\n💪 لا بأس، السوق يتقلب.. حاول مجدداً!",
        "up": "صعود 🟢", "down": "هبوط 🔴"
    },
    "en": {
        "welcome": "<b>🌟 Welcome to Moonbix Pro Universe!</b>\n\n🎯 <b>Balance:</b> <code>{points}</code> PTS\n📈 <b>Win Rate:</b> <code>{win_rate}%</code>\n\n<i>Challenge the market and predict BTC movement!</i>",
        "trade_up": "🚀 Long (Up)", "trade_down": "📉 Short (Down)", "balance_btn": "💳 Wallet", "lang_btn": "🇸🇦 العربية",
        "insufficient": "❌ <b>Oops!</b> You need at least 100 points.",
        "recording": "<b>⌛️ Trade Executed Successfully!</b>\n\n🔹 <b>Direction:</b> {choice}\n🔹 <b>Entry Price:</b> <code>${price}</code>\n\n<i>Monitoring the chart for 60 seconds...</i>",
        "win": "<b>✅ Successful Trade! (+150 PTS)</b>\n\n💰 <b>Final Price:</b> <code>${price}</code>\n🎊 Your prediction was spot on!",
        "loss": "<b>❌ Trade Failed! (-100 PTS)</b>\n\n🔻 <b>Final Price:</b> <code>${price}</code>\n💪 Market is volatile.. try again!",
        "up": "UP 🟢", "down": "DOWN 🔴"
    }
}

ptb_app = Application.builder().token(TOKEN).build()

def get_btc_price():
    try:
        res = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT").json()
        return float(res['result']['list'][0]['lastPrice'])
    except: return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_db: 
        users_db[user_id] = {"points": 1000, "lang": None, "wins": 0, "total": 0}
    
    if users_db[user_id]["lang"] is None:
        keyboard = [[InlineKeyboardButton("العربية 🇸🇦", callback_data='set_lang_ar')],
                    [InlineKeyboardButton("English 🇺🇸", callback_data='set_lang_en')]]
        await update.message.reply_photo(photo=IMG_WELCOME, caption="<b>Choose your Language / اختر لغتك</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else: 
        await show_main_menu(update, user_id)

async def show_main_menu(update_or_query, user_id):
    lang = users_db[user_id]["lang"]
    points = users_db[user_id]["points"]
    total = users_db[user_id]["total"]
    win_rate = round((users_db[user_id]["wins"] / total * 100), 1) if total > 0 else 0
    
    text = STRINGS[lang]["welcome"].format(points=points, win_rate=win_rate)
    keyboard = [[InlineKeyboardButton(STRINGS[lang]["trade_up"], callback_data='trade_up'),
                 InlineKeyboardButton(STRINGS[lang]["trade_down"], callback_data='trade_down')],
                [InlineKeyboardButton(STRINGS[lang]["balance_btn"], callback_data='balance')],
                [InlineKeyboardButton(STRINGS[lang]["lang_btn"], callback_data='change_lang')]]
    
    markup = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, Update): 
        await update_or_query.message.reply_photo(photo=IMG_WELCOME, caption=text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else: 
        await update_or_query.edit_message_media(media=InputMediaPhoto(media=IMG_WELCOME, caption=text, parse_mode=ParseMode.HTML), reply_markup=markup)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); user_id = query.from_user.id; data = query.data
    
    if data.startswith("set_lang_"):
        users_db[user_id]["lang"] = data.split("_")[2]
        await show_main_menu(query, user_id); return
    
    if data == "change_lang":
        users_db[user_id]["lang"] = "en" if users_db[user_id]["lang"] == "ar" else "ar"
        await show_main_menu(query, user_id); return
    
    lang = users_db[user_id].get("lang", "en")
    
    if data.startswith("trade_"):
        choice = data.split("_")[1]
        if users_db[user_id]['points'] < 100:
            await query.edit_message_caption(caption=STRINGS[lang]["insufficient"], parse_mode=ParseMode.HTML); return
        
        price_start = get_btc_price()
        users_db[user_id]['points'] -= 100
        users_db[user_id]['total'] += 1
        choice_text = STRINGS[lang]["up"] if choice == "up" else STRINGS[lang]["down"]
        
        await query.edit_message_media(media=InputMediaPhoto(media=IMG_TRADING, caption=STRINGS[lang]["recording"].format(choice=choice_text, price=f"{price_start:,}"), parse_mode=ParseMode.HTML))
        
        await asyncio.sleep(60)
        
        price_end = get_btc_price()
        win = (choice == "up" and price_end > price_start) or (choice == "down" and price_end < price_start)
        
        if win:
            users_db[user_id]['points'] += 250
            users_db[user_id]['wins'] += 1
            result = STRINGS[lang]["win"].format(price=f"{price_end:,}")
        else:
            result = STRINGS[lang]["loss"].format(price=f"{price_end:,}")
        
        await query.edit_message_caption(caption=f"{result}\n\n💰 <b>Balance:</b> {users_db[user_id]['points']}", parse_mode=ParseMode.HTML)
        await asyncio.sleep(5); await show_main_menu(query, user_id)

pt_app = ptb_app # Alias

@app.post(f"/{TOKEN}")
async def respond():
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    await ptb_app.process_update(update)
    return "ok"

@app.route('/')
def health(): return "<b>Server Online</b>", 200

async def init_bot():
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{TOKEN}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_bot())
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
