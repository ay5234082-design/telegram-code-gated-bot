import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiohttp import web

# -----------------------------
# Environment Variables
# -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
BACKUP_CHANNEL = int(os.getenv("BACKUP_CHANNEL", 0))
AUTH_USER_IDS = list(map(int, os.getenv("AUTH_USER_IDS", "").split(",")))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -----------------------------
# Video Upload Handler
# -----------------------------
@dp.message_handler(content_types=["video"])
async def handle_video(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ You are not authorized to upload videos.")
        return
    
    await message.reply("✅ Video received. Processing...")

    # Video temporarily save
    temp_path = f"temp_{message.video.file_name}"
    video_file = await message.video.download(destination=temp_path)

    # Send to backup channel
    await bot.send_video(BACKUP_CHANNEL, InputFile(video_file.name), caption="New video uploaded by owner.")

    # Send to all authorized users
    for user_id in AUTH_USER_IDS:
        try:
            await bot.send_video(user_id, InputFile(video_file.name), caption="Your generated video!")
        except Exception as e:
            print(f"Failed to send to {user_id}: {e}")

    # Wait 15 minutes then delete temporary video
    await asyncio.sleep(900)  # 15 minutes
    os.remove(video_file.name)
    await message.reply("🗑️ Temporary video deleted.")

# -----------------------------
# Dummy Webserver for Render
# -----------------------------
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

# -----------------------------
# Main Function
# -----------------------------
async def main():
    # Start webserver
    asyncio.create_task(start_webserver())
    # Start bot polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
