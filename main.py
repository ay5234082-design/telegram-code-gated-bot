# main.py - Updated for Render.com deployment
import os
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Set
import hashlib
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FileAccessBot:
    def __init__(self):
        # Load configuration from environment variables
        self.bot_token = os.environ.get("7559492905:AAFEtoyWTIB0l83RFw2fZOhp3bU9geVTTpA")
        self.owner_id = int(os.environ.get("5045767844", "0"))
        self.backup_channel_id = os.environ.get("-1003099354644", "")
        self.db_path = "file_bot.db"
        self.init_database()
        
        # In-memory storage for temporary data
        self.pending_uploads: Dict[int, dict] = {}
        self.uploaded_users: Set[int] = set()
        
    # ================= Database =================
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                access_code TEXT UNIQUE NOT NULL,
                file_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                uploaded_by INTEGER NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS authorized_uploaders (
                user_id INTEGER PRIMARY KEY,
                authorized_by INTEGER NOT NULL,
                authorized_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shared_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                shared_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delete_at TIMESTAMP NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # ================= Utilities =================
    def generate_access_code(self) -> str:
        """Generate a unique 8-character access code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT access_code FROM files WHERE access_code = ?", (code,))
            if not cursor.fetchone():
                conn.close()
                return code
            conn.close()
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None):
        """Add user to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, first_name))
        conn.commit()
        conn.close()
    
    def is_authorized_uploader(self, user_id: int) -> bool:
        """Check if user is authorized to upload files"""
        if user_id == self.owner_id:
            return True
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM authorized_uploaders WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return bool(result)
    
    async def check_channel_membership(self, bot: Bot, user_id: int) -> bool:
        """Check if user is member of backup channel"""
        try:
            member = await bot.get_chat_member(self.backup_channel_id, user_id)
            return member.status in ['member', 'administrator', 'creator']
        except TelegramError:
            return False
    
    # ================= Commands =================
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.add_user(user.id, user.username, user.first_name)
        await update.message.reply_text(
            "🤖 Welcome to File Access Bot!\n\n📝 Write code and get your file."
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id == self.owner_id:
            help_text = """
🔧 Owner Commands:
/check_users - View total users
/broadcast <msg> - Send to all users
/authorize <user_id> - Authorize uploader
/revoke <user_id> - Revoke permission
/upload - Upload file
/list_files - List uploaded files
"""
        else:
            help_text = "👤 Send access code to get your file. Join backup channel first!"
        await update.message.reply_text(help_text)
    
    # You can keep all other functions as in your current code:
    # handle_message, handle_access_code, check_join_callback, delete_file_callback, upload_command, 
    # handle_file_upload, check_users_command, broadcast_command, authorize_command, revoke_command, list_files_command
    
    # ================= Run Bot =================
    def run(self):
        """Start the bot"""
        if not self.bot_token or not self.owner_id or not self.backup_channel_id:
            logger.error("❌ BOT_TOKEN, OWNER_ID, or BACKUP_CHANNEL_ID is not set in environment variables!")
            return
        
        application = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("upload", self.upload_command))
        application.add_handler(CommandHandler("check_users", self.check_users_command))
        application.add_handler(CommandHandler("broadcast", self.broadcast_command))
        application.add_handler(CommandHandler("authorize", self.authorize_command))
        application.add_handler(CommandHandler("revoke", self.revoke_command))
        application.add_handler(CommandHandler("list_files", self.list_files_command))
        
        application.add_handler(CallbackQueryHandler(self.check_join_callback, pattern=r"check_join:"))
        application.add_handler(MessageHandler(filters.Document.ALL, self.handle_file_upload))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("✅ Bot started successfully!")
        application.run_polling()

# ================= Main =================
if __name__ == "__main__":
    bot = FileAccessBot()
    bot.run()
