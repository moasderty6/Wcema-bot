import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
PORT = int(os.getenv("PORT") or 10000)

WEBHOOK_PATH = "/telegram"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

bot = Bot(API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("✅ WORKING")

async def root(request):
    return web.Response(text="OK")

async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

async def main():
    app = web.Application()
    app.router.add_get("/", root)
    SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
    app.on_startup.append(on_startup)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    await asyncio.Event().wait()

asyncio.run(main())