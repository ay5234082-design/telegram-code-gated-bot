
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
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FileAccessBot:
    def __init__(self, bot_token: str, owner_id: int, backup_channel_id: str):
        self.bot_token = bot_token
        self.owner_id = owner_id
        self.backup_channel_id = backup_channel_id  # Channel username or ID (e.g., @mychannel or -1001234567890)
        self.db_path = "file_bot.db"
        self.init_database()
        
        # In-memory storage for temporary data
        self.pending_uploads: Dict[int, dict] = {}
        self.uploaded_users: Set[int] = set()
        
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Files table
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
        
        # Authorized uploaders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS authorized_uploaders (
                user_id INTEGER PRIMARY KEY,
                authorized_by INTEGER NOT NULL,
                authorized_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Shared files tracking (for auto-deletion)
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
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        self.add_user(user.id, user.username, user.first_name)
        
        welcome_text = "🤖 Welcome to File Access Bot!\n\n📝 Write code and get your file."
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = update.effective_user.id
        
        if user_id == self.owner_id:
            help_text = """
🔧 **Owner Commands:**
/check_users - View total users count
/broadcast <message> - Send message to all users  
/authorize <user_id> - Authorize user to upload files
/revoke <user_id> - Revoke upload permission
/upload - Upload a new file
/list_files - List all uploaded files

👤 **User Commands:**
Just send an access code to get your file!
            """
        else:
            help_text = """
👤 **How to use:**
1. Join our backup channel
2. Send me your access code
3. Get your file (available for 15 minutes)

Need help? Contact the bot owner!
            """
        
        await update.message.reply_text(help_text)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (access codes)"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        # Check if it's an access code (8 characters, alphanumeric)
        if len(text) == 8 and text.isalnum() and text.isupper():
            await self.handle_access_code(update, context, text)
            return
        
        # Handle upload process
        if user_id in self.pending_uploads:
            if self.pending_uploads[user_id]['step'] == 'waiting_code':
                # User provided filename/description
                if len(text) <= 50:
                    self.pending_uploads[user_id]['description'] = text
                    self.pending_uploads[user_id]['step'] = 'waiting_file'
                    await update.message.reply_text("📎 Now send the file you want to upload.")
                else:
                    await update.message.reply_text("❌ Description too long. Max 50 characters.")
                return
        
        await update.message.reply_text("❓ Please send a valid 8-character access code or use /help for assistance.")
    
    async def handle_access_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE, access_code: str):
        """Handle access code submission"""
        user_id = update.effective_user.id
        
        # Check channel membership first
        if not await self.check_channel_membership(context.bot, user_id):
            keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{self.backup_channel_id.replace('@', '')}")],
                       [InlineKeyboardButton("✅ I Joined", callback_data=f"check_join:{access_code}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚠️ You must join our backup channel to access files!",
                reply_markup=reply_markup
            )
            return
        
        # Check if access code exists
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, filename FROM files WHERE access_code = ?", (access_code,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            await update.message.reply_text("❌ Invalid access code. Please check and try again.")
            return
        
        file_id, filename = result
        
        # Send file with deletion warning
        try:
            message = await context.bot.send_document(
                chat_id=user_id,
                document=file_id,
                caption=f"📁 **{filename}**\n\n⚠️ **This file will be deleted after 15 minutes!**",
                parse_mode='Markdown'
            )
            
            # Schedule auto-deletion
            delete_time = datetime.now() + timedelta(minutes=15)
            
            # Store in database for deletion tracking
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO shared_files (message_id, chat_id, file_id, delete_at)
                VALUES (?, ?, ?, ?)
            ''', (message.message_id, user_id, file_id, delete_time))
            conn.commit()
            conn.close()
            
            # Schedule deletion
            context.job_queue.run_once(
                self.delete_file_callback,
                when=timedelta(minutes=15),
                data={'message_id': message.message_id, 'chat_id': user_id}
            )
            
            logger.info(f"File {filename} shared to user {user_id} with code {access_code}")
            
        except TelegramError as e:
            await update.message.reply_text("❌ Error sending file. Please try again later.")
            logger.error(f"Error sending file: {e}")
    
    async def check_join_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'I Joined' button callback"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        access_code = query.data.split(':')[1]
        
        if await self.check_channel_membership(context.bot, user_id):
            await query.edit_message_text("✅ Great! Now processing your access code...")
            
            # Process the access code
            fake_update = type('obj', (object,), {
                'message': type('obj', (object,), {
                    'reply_text': query.message.reply_text
                })(),
                'effective_user': query.from_user
            })()
            
            await self.handle_access_code(fake_update, context, access_code)
        else:
            await query.edit_message_text("❌ You have not joined yet! Please join the channel first.")
    
    async def delete_file_callback(self, context: ContextTypes.DEFAULT_TYPE):
        """Callback to delete shared files after 15 minutes"""
        data = context.job.data
        message_id = data['message_id']
        chat_id = data['chat_id']
        
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            
            # Remove from database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shared_files WHERE message_id = ? AND chat_id = ?", (message_id, chat_id))
            conn.commit()
            conn.close()
            
            logger.info(f"Auto-deleted file message {message_id} from chat {chat_id}")
            
        except TelegramError as e:
            logger.error(f"Error deleting message {message_id}: {e}")
    
    async def upload_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /upload command"""
        user_id = update.effective_user.id
        
        if not self.is_authorized_uploader(user_id):
            await update.message.reply_text("❌ You are not authorized to upload files.")
            return
        
        self.pending_uploads[user_id] = {'step': 'waiting_code'}
        await update.message.reply_text("📝 Please provide a description for this file (max 50 characters):")
    
    async def handle_file_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file uploads"""
        user_id = update.effective_user.id
        
        if user_id not in self.pending_uploads or self.pending_uploads[user_id]['step'] != 'waiting_file':
            await update.message.reply_text("❌ Use /upload command first to start uploading.")
            return
        
        if not update.message.document:
            await update.message.reply_text("❌ Please send a document file.")
            return
        
        # Generate access code
        access_code = self.generate_access_code()
        file_id = update.message.document.file_id
        filename = self.pending_uploads[user_id]['description']
        
        # Store in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO files (access_code, file_id, filename, uploaded_by)
            VALUES (?, ?, ?, ?)
        ''', (access_code, file_id, filename, user_id))
        conn.commit()
        conn.close()
        
        # Clean up pending upload
        del self.pending_uploads[user_id]
        
        await update.message.reply_text(
            f"✅ **File uploaded successfully!**\n\n"
            f"🔑 **Access Code:** `{access_code}`\n"
            f"📁 **Description:** {filename}\n\n"
            f"Share this code with users to give them access to the file.",
            parse_mode='Markdown'
        )
        
        logger.info(f"File uploaded by user {user_id} with code {access_code}")
    
    async def check_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check_users command (owner only)"""
        if update.effective_user.id != self.owner_id:
            await update.message.reply_text("❌ This command is for the owner only.")
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        conn.close()
        
        await update.message.reply_text(f"👥 **Total Users:** {total_users}")
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /broadcast command (owner only)"""
        if update.effective_user.id != self.owner_id:
            await update.message.reply_text("❌ This command is for the owner only.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Usage: /broadcast <your message>")
            return
        
        message = ' '.join(context.args)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
        
        sent_count = 0
        failed_count = 0
        
        status_msg = await update.message.reply_text("📤 Broadcasting message...")
        
        for (user_id,) in users:
            try:
                await context.bot.send_message(chat_id=user_id, text=f"📢 **Broadcast Message:**\n\n{message}", parse_mode='Markdown')
                sent_count += 1
                await asyncio.sleep(0.05)  # Rate limiting
            except TelegramError:
                failed_count += 1
        
        await status_msg.edit_text(
            f"✅ **Broadcast Complete!**\n\n"
            f"📤 Sent: {sent_count}\n"
            f"❌ Failed: {failed_count}",
            parse_mode='Markdown'
        )
    
    async def authorize_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /authorize command (owner only)"""
        if update.effective_user.id != self.owner_id:
            await update.message.reply_text("❌ This command is for the owner only.")
            return
        
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("❌ Usage: /authorize <user_id>")
            return
        
        user_id = int(context.args[0])
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO authorized_uploaders (user_id, authorized_by)
            VALUES (?, ?)
        ''', (user_id, self.owner_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ User {user_id} has been authorized to upload files.")
    
    async def revoke_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /revoke command (owner only)"""
        if update.effective_user.id != self.owner_id:
            await update.message.reply_text("❌ This command is for the owner only.")
            return
        
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("❌ Usage: /revoke <user_id>")
            return
        
        user_id = int(context.args[0])
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM authorized_uploaders WHERE user_id = ?", (user_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if affected > 0:
            await update.message.reply_text(f"✅ Upload permission revoked for user {user_id}.")
        else:
            await update.message.reply_text(f"❌ User {user_id} was not authorized.")
    
    async def list_files_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_files command (owner only)"""
        if update.effective_user.id != self.owner_id:
            await update.message.reply_text("❌ This command is for the owner only.")
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT access_code, filename, upload_date, uploaded_by 
            FROM files 
            ORDER BY upload_date DESC 
            LIMIT 20
        ''')
        files = cursor.fetchall()
        conn.close()
        
        if not files:
            await update.message.reply_text("📁 No files uploaded yet.")
            return
        
        text = "📁 **Recent Files:**\n\n"
        for code, filename, date, uploader in files:
            text += f"🔑 `{code}` - {filename}\n"
            text += f"   📅 {date} | 👤 {uploader}\n\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    def run(self):
        """Start the bot"""
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
        
        logger.info("Bot started successfully!")
        application.run_polling()

# Configuration from environment vari
