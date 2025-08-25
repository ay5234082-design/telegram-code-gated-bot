""" Telegram Code‑Gated File Bot

Features

Force-join a backup channel before access

Code → file mapping (owner/allowed uploaders can save)

15‑minute auto‑delete of delivered messages

Owner controls: /grant, /revoke, /stats, /broadcast

Safe, cached file sending via file_id (no reupload)


Quick Setup

1. Python 3.10+


2. pip install aiogram==3.6.0


3. Set environment variables:

BOT_TOKEN          -> your bot token

OWNER_ID           -> your Telegram numeric user id (e.g., 123456789)

FORCE_JOIN_CHANNEL -> channel username (e.g., @my_backup) or numeric id (e.g., -1001234567890)



4. Run: python telegram_code_gated_bot.py



Notes & Limitations

Telegram allows deleting the message we sent after 15 minutes; if the user downloads/saves the file, you cannot revoke it from their device.

Forwards work: reply to any media (forwarded or original) with /save <CODE> to register it.

Alternative: send media with caption "code: <CODE>" as owner/allowed uploader.


"""

import asyncio import os import sqlite3 from contextlib import closing from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, F from aiogram.filters import Command, CommandObject from aiogram.types import ( Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ) from aiogram.utils.keyboard import InlineKeyboardBuilder from aiogram.enums.chat_member_status import ChatMemberStatus

-------------------- Config --------------------

BOT_TOKEN = os.getenv("7559492905:AAFEtoyWTIB0l83RFw2fZOhp3bU9geVTTpA") OWNER_ID = int(os.getenv("5045767844", "0")) FORCE_JOIN_CHANNEL = os.getenv("@newupji")  # e.g., "@my_backup" or -100123...

if not BOT_TOKEN or not OWNER_ID or not FORCE_JOIN_CHANNEL: raise SystemExit( "Please set BOT_TOKEN, OWNER_ID, FORCE_JOIN_CHANNEL environment variables before running." )

bot = Bot(BOT_TOKEN) dp = Dispatcher()

DB_PATH = os.getenv("DB_PATH", "/data/bot.db")
-------------------- Database --------------------

def init_db(): with closing(sqlite3.connect(DB_PATH)) as conn: c = conn.cursor() c.execute( """ CREATE TABLE IF NOT EXISTS users ( user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ) """ ) c.execute( """ CREATE TABLE IF NOT EXISTS codes ( code TEXT PRIMARY KEY, file_id TEXT NOT NULL, file_type TEXT NOT NULL CHECK(file_type IN ('video','document','audio','photo','animation','voice')), added_by INTEGER NOT NULL, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ) """ ) c.execute( """ CREATE TABLE IF NOT EXISTS allowed_uploaders ( user_id INTEGER PRIMARY KEY ) """ ) conn.commit()

def db_execute(query: str, params: Tuple = ()):  # write with closing(sqlite3.connect(DB_PATH)) as conn: c = conn.cursor() c.execute(query, params) conn.commit()

def db_fetchone(query: str, params: Tuple = ()) -> Optional[tuple]: with closing(sqlite3.connect(DB_PATH)) as conn: c = conn.cursor() c.execute(query, params) return c.fetchone()

def db_fetchall(query: str, params: Tuple = ()) -> list[tuple]: with closing(sqlite3.connect(DB_PATH)) as conn: c = conn.cursor() c.execute(query, params) return c.fetchall()

-------------------- Helpers --------------------

async def ensure_user_row(message: Message): try: db_execute( "INSERT OR IGNORE INTO users(user_id, first_name, username) VALUES(?,?,?)", (message.from_user.id, message.from_user.first_name, message.from_user.username), ) except Exception: pass

def is_owner(user_id: int) -> bool: return user_id == OWNER_ID

def is_allowed_uploader(user_id: int) -> bool: if is_owner(user_id): return True row = db_fetchone("SELECT 1 FROM allowed_uploaders WHERE user_id=?", (user_id,)) return row is not None

async def check_force_join(user_id: int) -> bool: try: member = await bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id) return member.status in { ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR, } except Exception: return False

def join_keyboard() -> InlineKeyboardMarkup: kb = InlineKeyboardBuilder() kb.row( InlineKeyboardButton(text="Join Channel", url=f"https://t.me/{str(FORCE_JOIN_CHANNEL).lstrip('@')}") ) kb.row( InlineKeyboardButton(text="I Joined ✅", callback_data="joined"), InlineKeyboardButton(text="Enter Code ⌨️", callback_data="enter_code"), ) return kb.as_markup()

async def prompt_code(chat_id: int): await bot.send_message( chat_id, "Write your access code to get your file.\nNote: The delivered message will auto‑delete after 15 minutes.", )

async def send_file_by_code(message: Message, code: str): row = db_fetchone("SELECT file_id, file_type FROM codes WHERE code=?", (code.strip(),)) if not row: await message.answer("❌ Invalid code. Please check and try again.") return file_id, file_type = row

warn = await message.answer(
    "⚠️ The file we send will be automatically deleted from this chat after 15 minutes. Save it if you need it."
)

sent: Optional[Message] = None
try:
    if file_type == "video":
        sent = await message.answer_video(video=file_id)
    elif file_type == "document":
        sent = await message.answer_document(document=file_id)
    elif file_type == "audio":
        sent = await message.answer_audio(audio=file_id)
    elif file_type == "photo":
        sent = await message.answer_photo(photo=file_id)
    elif file_type == "animation":
        sent = await message.answer_animation(animation=file_id)
    elif file_type == "voice":
        sent = await message.answer_voice(voice=file_id)
    else:
        await message.answer("Unsupported file type stored for this code.")
        return
except Exception as e:
    await message.answer(f"Failed to send the file: {e}")
    return

# Schedule auto delete after 15 minutes (900s)
async def auto_delete(msg_ids: list[int]):
    try:
        await asyncio.sleep(900)
        for mid in msg_ids:
            try:
                await bot.delete_message(message.chat.id, mid)
            except Exception:
                pass
    except Exception:
        pass

ids = [warn.message_id]
if sent:
    ids.append(sent.message_id)
asyncio.create_task(auto_delete(ids))

-------------------- Handlers --------------------

@dp.message(Command("start")) async def cmd_start(message: Message): await ensure_user_row(message) if await check_force_join(message.from_user.id): await message.answer( "Welcome! Write code and get your file.", reply_markup=join_keyboard(), ) else: await message.answer( "To use this bot, first join our backup channel.", reply_markup=join_keyboard(), )

@dp.callback_query(F.data == "joined") async def cb_joined(call: CallbackQuery): ok = await check_force_join(call.from_user.id) if ok: await call.message.edit_text( "✅ Membership verified. Now tap Enter Code or just type your code.", reply_markup=join_keyboard(), ) else: await call.answer("You have not joined yet!", show_alert=True)

@dp.callback_query(F.data == "enter_code") async def cb_enter_code(call: CallbackQuery): await call.message.answer("Please type your access code:") await call.answer()

@dp.message(F.text & ~F.via_bot) async def on_text(message: Message): # Treat any plain text as a potential code if user is joined if not await check_force_join(message.from_user.id): await message.answer( "You must join the backup channel first.", reply_markup=join_keyboard() ) return text = message.text.strip()

# Owner/admin commands may also be plain text; they are handled by command handlers below
# If plain text is not a command, try as code
if not text.startswith("/"):
    await send_file_by_code(message, text)

-------- Owner & Uploader Commands --------

@dp.message(Command("save")) async def cmd_save(message: Message, command: CommandObject): """ Usage: 1) Reply to a media message with: /save CODE 2) Or send media with caption starting with: code: CODE   (handled in media handlers below) """ if not is_allowed_uploader(message.from_user.id): await message.answer("Only the owner or allowed uploaders can save files.") return if not message.reply_to_message: await message.answer("Reply to a media message with /save <CODE>.") return code = (command.args or "").strip() if not code: await message.answer("Please provide a code. Example: /save 1234") return

media = message.reply_to_message

file_id, file_type = extract_media(media)
if not file_id:
    await message.answer("Replied message has no supported media.")
    return

try:
    db_execute(
        "INSERT OR REPLACE INTO codes(code, file_id, file_type, added_by) VALUES(?,?,?,?)",
        (code, file_id, file_type, message.from_user.id),
    )
    await message.answer(f"✅ Saved. Code \"{code}\" now maps to this {file_type}.")
except Exception as e:
    await message.answer(f"Error saving: {e}")

@dp.message(Command("grant")) async def cmd_grant(message: Message, command: CommandObject): if not is_owner(message.from_user.id): return try: uid = int((command.args or "").strip()) db_execute("INSERT OR IGNORE INTO allowed_uploaders(user_id) VALUES(?)", (uid,)) await message.answer(f"✅ Granted upload permission to {uid}.") except Exception as e: await message.answer(f"Failed: {e}")

@dp.message(Command("revoke")) async def cmd_revoke(message: Message, command: CommandObject): if not is_owner(message.from_user.id): return try: uid = int((command.args or "").strip()) db_execute("DELETE FROM allowed_uploaders WHERE user_id=?", (uid,)) await message.answer(f"✅ Revoked upload permission from {uid}.") except Exception as e: await message.answer(f"Failed: {e}")

@dp.message(Command("stats")) async def cmd_stats(message: Message): if not is_owner(message.from_user.id): return total_users = db_fetchone("SELECT COUNT() FROM users")[0] total_codes = db_fetchone("SELECT COUNT() FROM codes")[0] uploaders = db_fetchone("SELECT COUNT(*) FROM allowed_uploaders")[0] await message.answer( f"👥 Users: {total_users}\n🎫 Codes: {total_codes}\n🛠️ Allowed uploaders (excl. owner): {uploaders}" )

@dp.message(Command("broadcast")) async def cmd_broadcast(message: Message, command: CommandObject): if not is_owner(message.from_user.id): return text = (command.args or "").strip() if not text: await message.answer("Usage: /broadcast Your message to everyone") return users = db_fetchall("SELECT user_id FROM users") sent = 0 for (uid,) in users: try: await bot.send_message(uid, text) sent += 1 await asyncio.sleep(0.05) except Exception: pass await message.answer(f"Broadcast sent to {sent} users.")

-------- Media capture via caption "code: XXXX" --------

@dp.message(F.caption) async def on_captioned_media(message: Message): caption = message.caption or "" if caption.lower().startswith("code:"): if not is_allowed_uploader(message.from_user.id): await message.answer("Only the owner or allowed uploaders can save files.") return code = caption.split(":", 1)[1].strip() file_id, file_type = extract_media(message) if not file_id: await message.answer("No supported media found in your message.") return try: db_execute( "INSERT OR REPLACE INTO codes(code, file_id, file_type, added_by) VALUES(?,?,?,?)", (code, file_id, file_type, message.from_user.id), ) await message.answer(f"✅ Saved. Code "{code}" now maps to this {file_type}.") except Exception as e: await message.answer(f"Error saving: {e}")

-------------------- Media extractor --------------------

def extract_media(msg: Message) -> Tuple[Optional[str], Optional[str]]: if msg.video: return msg.video.file_id, "video" if msg.document: return msg.document.file_id, "document" if msg.audio: return msg.audio.file_id, "audio" if msg.photo: # take the best resolution photo return msg.photo[-1].file_id, "photo" if msg.animation: return msg.animation.file_id, "animation" if msg.voice: return msg.voice.file_id, "voice" return None, None

-------------------- Startup --------------------

async def on_startup(): init_db() # Ensure owner in users table (optional convenience) try: db_execute( "INSERT OR IGNORE INTO users(user_id, first_name, username) VALUES(?,?,?)", (OWNER_ID, "Owner", None), ) except Exception: pass

async def main(): await on_startup() print("Bot is running...") await dp.start_polling(bot)

if name == "main": try: asyncio.run(main()) except (KeyboardInterrupt, SystemExit): print("Bot stopped.")

