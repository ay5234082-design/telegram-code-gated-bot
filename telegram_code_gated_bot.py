import os import asyncio from aiogram import Bot, Dispatcher from aiogram.types import Message from aiogram.filters import CommandStart from aiohttp import web

BOT_TOKEN = os.getenv("7559492905:AAFEtoyWTIB0l83RFw2fZOhp3bU9geVTTpA") OWNER_ID = int(os.getenv("5045767844", "0")) FORCE_JOIN_CHANNEL = os.getenv("@newupji")

bot = Bot(token=BOT_TOKEN) dp = Dispatcher()

--- Dummy Web Server for Render ---

async def handle(request): return web.Response(text="Bot is running!")

async def start_webserver(): app = web.Application() app.router.add_get("/", handle) runner = web.AppRunner(app) await runner.setup() site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080))) await site.start()

--- Bot Handlers ---

@dp.message(CommandStart()) async def start_cmd(message: Message): await message.answer("Hello! Bot is running successfully on Render Free Plan 🚀")

--- Main ---

async def main(): # Start dummy web server for Render asyncio.create_task(start_webserver()) # Start Telegram bot polling await dp.start_polling(bot)

if name == "main": asyncio.run(main())

