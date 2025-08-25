import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.filters import Command
from aiohttp import web

# ====== CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))  # Owner user ID
BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", 0))  # Backup channel ID

# Safe AUTH_USER_IDS parsing
auth_user_ids_str = os.getenv("AUTH_USER_IDS", "")
if auth_user_ids_str.strip():
    AUTH_USER_IDS = list(map(int, auth_user_ids_str.split(",")))
else:
    AUTH_USER_IDS = []

# ====== INIT BOT ======
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ====== HANDLERS ======
@dp.message(Command("start"))
async def start_command(message: types.Message):
    if message.from_user.id in AUTH_USER_IDS or message.from_user.id == OWNER_ID:
        await message.reply("Welcome! You are authorized.")
    else:
        await message.reply("You are not authorized.")

# ====== VIDEO UPLOAD HANDLER ======
@dp.message(lambda m: m.video)
async def handle_video(message: types.Message):
    # Only owner or authorized users can upload
    if message.from_user.id not in AUTH_USER_IDS and message.from_user.id != OWNER_ID:
        await message.reply("You are not allowed to upload.")
        return

    video = message.video
    # Forward video to backup channel if configured
    if BACKUP_CHANNEL_ID:
        await bot.send_video(BACKUP_CHANNEL_ID, video.file_id, caption=f"Backup from {message.from_user.id}")

    # Auto-delete video after 15 minutes
    await asyncio.sleep(15*60)
    try:
        await message.delete()
    except:
        pass  # ignore if already deleted

# ====== WEB SERVER ======
async def handle(request):
    return web.Response(text="Bot is running ✅")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

# ====== MAIN ======
async def main():
    # Start webserver in background
    asyncio.create_task(start_webserver())
    # Start bot
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
