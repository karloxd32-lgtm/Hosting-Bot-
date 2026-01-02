import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import logging
import threading
import re
import sys
import atexit
import requests
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Telegram Bot is Running!"

@app.route('/health')
def health():
    return {
        "status": "healthy",
        "service": "Telegram Bot Hosting Platform",
        "timestamp": datetime.now().isoformat()
    }

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print(f"✅ Flask server started on port {os.environ.get('PORT', 8000)}")

# Get environment variables with defaults
TOKEN = os.getenv('BOT_TOKEN', '8308556375:AAHrb500ylL3vXOG1prDIU_kBklXCMWr6p4')
OWNER_ID = int(os.getenv('OWNER_ID', '7151606562'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '7151606562'))
YOUR_USERNAME = os.getenv('YOUR_USERNAME', '@LuffyBots')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'https://t.me/EscrowMoon')

# AI API Configuration
A4F_API_URL = os.getenv('A4F_API_URL', 'https://samuraiapi.in/v1/chat/completions')
A4F_API_KEY = os.getenv('A4F_API_KEY', 'sk-NK6SS9tpWghyFJwkZLoCis1sMaF6RwQ5WF09mUoKKR0VKCm7')
A4F_MODEL = os.getenv('A4F_MODEL', 'provider10-claude-sonnet-4-20250514(clinesp)')

# Validate token
if not TOKEN:
    print("❌ ERROR: BOT_TOKEN not found in environment variables!")
    print("Please set BOT_TOKEN in Railway variables")
    sys.exit(1)

# Bot setup
BOT_START_TIME = datetime.now()
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Constants
FREE_USER_LIMIT = 20
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Setup directories
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Global variables
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Button layouts
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "⏱ Uptime"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner", "🤖 MPX Ai"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "/ping"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Run All Scripts"],
    ["👑 Admin Panel", "📞 Contact Owner"],
    ["🤖 MPX Ai", "⏱ Uptime"],
]

def get_uptime():
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

# Database functions
def init_db():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                 (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_files
                 (user_id INTEGER, file_name TEXT, file_type TEXT,
                  PRIMARY KEY (user_id, file_name))''')
    c.execute('''CREATE TABLE IF NOT EXISTS active_users
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY)''')
    
    c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
    if ADMIN_ID != OWNER_ID:
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def load_data():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    # Load subscriptions
    c.execute('SELECT user_id, expiry FROM subscriptions')
    for user_id, expiry in c.fetchall():
        try:
            user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
        except:
            pass
    
    # Load user files
    c.execute('SELECT user_id, file_name, file_type FROM user_files')
    for user_id, file_name, file_type in c.fetchall():
        if user_id not in user_files:
            user_files[user_id] = []
        user_files[user_id].append((file_name, file_type))
    
    # Load active users
    c.execute('SELECT user_id FROM active_users')
    active_users.update(user_id for (user_id,) in c.fetchall())
    
    # Load admins
    c.execute('SELECT user_id FROM admins')
    admin_ids.update(user_id for (user_id,) in c.fetchall())
    
    conn.close()
    logger.info(f"Loaded {len(active_users)} users, {len(user_subscriptions)} subscriptions")

# Initialize database
init_db()
load_data()

def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    if user_id in admin_ids:
        return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    if script_key not in bot_scripts:
        return False
    
    script_info = bot_scripts[script_key]
    if 'process' not in script_info:
        return False
    
    process = script_info['process']
    try:
        return process.poll() is None
    except:
        return False

def kill_process_tree(process_info):
    if not process_info or 'process' not in process_info:
        return
    
    process = process_info['process']
    try:
        if process.poll() is None:
            process.terminate()
            time.sleep(1)
            if process.poll() is None:
                process.kill()
    except:
        pass
    
    if 'log_file' in process_info:
        try:
            process_info['log_file'].close()
        except:
            pass

# Module mappings for auto-install
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'requests': 'requests',
    'flask': 'Flask',
    'psutil': 'psutil',
    'pillow': 'Pillow',
    'bs4': 'beautifulsoup4',
    'sqlalchemy': 'SQLAlchemy',
}

# Script running functions
def run_script(script_path, script_owner_id, user_folder, file_name, message):
    script_key = f"{script_owner_id}_{file_name}"
    
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message, f"❌ Script '{file_name}' not found!")
            return
        
        # Create log file
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        
        # Start process
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            encoding='utf-8',
            errors='ignore'
        )
        
        # Store process info
        bot_scripts[script_key] = {
            'process': process,
            'log_file': log_file,
            'file_name': file_name,
            'script_owner_id': script_owner_id,
            'user_folder': user_folder
        }
        
        bot.reply_to(message, f"✅ Python script '{file_name}' started!")
        
    except Exception as e:
        logger.error(f"Error running script: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message):
    script_key = f"{script_owner_id}_{file_name}"
    
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message, f"❌ Script '{file_name}' not found!")
            return
        
        # Create log file
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        
        # Start process
        process = subprocess.Popen(
            ['node', script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            encoding='utf-8',
            errors='ignore'
        )
        
        # Store process info
        bot_scripts[script_key] = {
            'process': process,
            'log_file': log_file,
            'file_name': file_name,
            'script_owner_id': script_owner_id,
            'user_folder': user_folder
        }
        
        bot.reply_to(message, f"✅ JavaScript script '{file_name}' started!")
        
    except FileNotFoundError:
        bot.reply_to(message, "❌ Node.js not installed!")
    except Exception as e:
        logger.error(f"Error running JS script: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

# Database lock
DB_LOCK = threading.Lock()

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                  (user_id, file_name, file_type))
        conn.commit()
        conn.close()
        
        if user_id not in user_files:
            user_files[user_id] = []
        user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
        user_files[user_id].append((file_name, file_type))

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
        conn.commit()
        conn.close()
        
        if user_id in user_files:
            user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
            if not user_files[user_id]:
                del user_files[user_id]

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()

# UI Functions
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if user_id in admin_ids:
        markup.row(
            types.InlineKeyboardButton('📢 Updates', url=UPDATE_CHANNEL),
            types.InlineKeyboardButton('📤 Upload', callback_data='upload')
        )
        markup.row(
            types.InlineKeyboardButton('📂 Files', callback_data='check_files'),
            types.InlineKeyboardButton('⚡ Speed', callback_data='speed')
        )
        markup.row(
            types.InlineKeyboardButton('📊 Stats', callback_data='stats'),
            types.InlineKeyboardButton('💳 Subs', callback_data='subscription')
        )
        markup.row(
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
            types.InlineKeyboardButton('🔒 Lock' if not bot_locked else '🔓 Unlock', 
                                     callback_data='lock_bot' if not bot_locked else 'unlock_bot')
        )
        markup.row(
            types.InlineKeyboardButton('👑 Admin', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Run All', callback_data='run_all_scripts')
        )
        markup.row(
            types.InlineKeyboardButton('📞 Contact', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'),
            types.InlineKeyboardButton('🤖 MPX AI', callback_data='mpx_ai')
        )
        markup.row(types.InlineKeyboardButton('⏱ Uptime', callback_data='uptime'))
    else:
        markup.row(
            types.InlineKeyboardButton('📢 Updates', url=UPDATE_CHANNEL),
            types.InlineKeyboardButton('📤 Upload', callback_data='upload')
        )
        markup.row(
            types.InlineKeyboardButton('📂 Files', callback_data='check_files'),
            types.InlineKeyboardButton('⚡ Speed', callback_data='speed')
        )
        markup.row(
            types.InlineKeyboardButton('📊 Stats', callback_data='stats'),
            types.InlineKeyboardButton('📞 Contact', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
        )
        markup.row(
            types.InlineKeyboardButton('🤖 MPX AI', callback_data='mpx_ai'),
            types.InlineKeyboardButton('⏱ Uptime', callback_data='uptime')
        )
    
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if user_id in admin_ids:
        for row in ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC:
            markup.row(*[types.KeyboardButton(text) for text in row])
    else:
        for row in COMMAND_BUTTONS_LAYOUT_USER_SPEC:
            markup.row(*[types.KeyboardButton(text) for text in row])
    
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
        )
    
    markup.row(
        types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
        types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
    )
    markup.row(types.InlineKeyboardButton("🔙 Back", callback_data='check_files'))
    
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Sub', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Sub', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Sub', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

# File handling
def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    
    try:
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, file_name_zip)
        
        with open(zip_path, 'wb') as f:
            f.write(downloaded_file_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find main script
        main_script = None
        file_type = None
        
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith('.py') and not main_script:
                    main_script = os.path.join(root, file)
                    file_type = 'py'
                elif file.endswith('.js') and not main_script:
                    main_script = os.path.join(root, file)
                    file_type = 'js'
        
        if not main_script:
            bot.reply_to(message, "❌ No Python or JS script found in archive.")
            return
        
        # Move files to user folder
        for item in os.listdir(temp_dir):
            src = os.path.join(temp_dir, item)
            dst = os.path.join(user_folder, item)
            
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        
        # Save and run
        main_file_name = os.path.basename(main_script)
        save_user_file(user_id, main_file_name, file_type)
        
        bot.reply_to(message, f"✅ Files extracted. Main script: `{main_file_name}`")
        
        script_path = os.path.join(user_folder, main_file_name)
        if file_type == 'py':
            threading.Thread(target=run_script, args=(script_path, user_id, user_folder, main_file_name, message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(script_path, user_id, user_folder, main_file_name, message)).start()
    
    except Exception as e:
        logger.error(f"Error processing zip: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

# Message handlers
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    user_id = message.from_user.id
    
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "🔒 Bot is locked by admin.")
        return
    
    add_active_user(user_id)
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    
    if user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry = user_subscriptions[user_id]['expiry']
        if expiry > datetime.now():
            days_left = (expiry - datetime.now()).days
            user_status = f"⭐ Premium ({days_left} days)"
        else:
            user_status = "👤 Free"
    else:
        user_status = "👤 Free"
    
    welcome_msg = f"""
👋 Welcome, {message.from_user.first_name}!

🆔 Your ID: `{user_id}`
👤 Status: {user_status}
📁 Files: {current_files}/{file_limit if file_limit != float('inf') else '∞'}

📌 Upload Python (.py) or JavaScript (.js) files
📦 Upload ZIP archives
⚡ Run your scripts in the cloud
"""
    
    markup = create_reply_keyboard_main_menu(user_id)
    bot.send_message(message.chat.id, welcome_msg, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['mpx'])
def handle_mpx_command(message):
    user_id = message.from_user.id
    
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "🔒 Bot is locked.")
        return
    
    if not message.text or len(message.text.split()) < 2:
        bot.reply_to(message, "❌ Usage: `/mpx your question`", parse_mode='Markdown')
        return
    
    query = message.text.split(' ', 1)[1]
    bot.send_chat_action(message.chat.id, 'typing')
    
    try:
        headers = {
            "Authorization": f"Bearer {A4F_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": A4F_MODEL,
            "messages": [{"role": "user", "content": query}],
            "temperature": 0.7
        }
        
        response = requests.post(A4F_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        answer = result.get('choices', [{}])[0].get('message', {}).get('content', 'No response')
        
        if len(answer) > 4000:
            for x in range(0, len(answer), 4000):
                bot.reply_to(message, answer[x:x+4000])
        else:
            bot.reply_to(message, answer)
            
    except Exception as e:
        logger.error(f"AI error: {e}")
        bot.reply_to(message, "❌ AI service error.")

@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "🔒 Bot is locked.")
        return
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    
    if current_files >= file_limit:
        bot.reply_to(message, f"❌ File limit reached ({current_files}/{file_limit}).")
        return
    
    doc = message.document
    file_name = doc.file_name
    
    if not file_name:
        bot.reply_to(message, "❌ File has no name.")
        return
    
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "❌ Only .py, .js, or .zip files allowed.")
        return
    
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "❌ File too large (max 20MB).")
        return
    
    try:
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        
        bot.reply_to(message, f"✅ File '{file_name}' saved.")
        
        if file_ext == '.zip':
            handle_zip_file(downloaded_file, file_name, message)
        elif file_ext == '.py':
            save_user_file(user_id, file_name, 'py')
            threading.Thread(target=run_script, args=(file_path, user_id, user_folder, file_name, message)).start()
        elif file_ext == '.js':
            save_user_file(user_id, file_name, 'js')
            threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, message)).start()
            
    except Exception as e:
        logger.error(f"Upload error: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

# Callback handlers
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    if bot_locked and user_id not in admin_ids and data not in ['uptime', 'speed']:
        bot.answer_callback_query(call.id, "🔒 Bot is locked.", show_alert=True)
        return
    
    try:
        if data == 'upload':
            if bot_locked and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "🔒 Bot is locked.", show_alert=True)
                return
            
            file_limit = get_user_file_limit(user_id)
            current_files = get_user_file_count(user_id)
            
            if current_files >= file_limit:
                bot.answer_callback_query(call.id, f"File limit reached ({current_files}/{file_limit})", show_alert=True)
                return
            
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "📤 Send your .py, .js, or .zip file.")
            
        elif data == 'check_files':
            bot.answer_callback_query(call.id)
            
            user_files_list = user_files.get(user_id, [])
            if not user_files_list:
                bot.send_message(call.message.chat.id, "📭 No files uploaded.")
                return
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            for file_name, file_type in user_files_list:
                is_running = is_bot_running(user_id, file_name)
                status = "🟢" if is_running else "🔴"
                markup.add(types.InlineKeyboardButton(
                    f"{status} {file_name} ({file_type})",
                    callback_data=f'file_{user_id}_{file_name}'
                ))
            
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
            bot.send_message(call.message.chat.id, "📁 Your Files:", reply_markup=markup)
            
        elif data == 'speed':
            bot.answer_callback_query(call.id)
            start_time = time.time()
            msg = bot.send_message(call.message.chat.id, "⚡ Testing speed...")
            ping_time = round((time.time() - start_time) * 1000, 2)
            bot.edit_message_text(f"⚡ Response: {ping_time} ms\n⏱ Uptime: {get_uptime()}",
                                call.message.chat.id, msg.message_id)
            
        elif data == 'stats':
            bot.answer_callback_query(call.id)
            total_users = len(active_users)
            total_files = sum(len(files) for files in user_files.values())
            running_scripts = len(bot_scripts)
            
            stats_msg = f"""
📊 Bot Statistics:

👥 Users: {total_users}
📁 Files: {total_files}
🟢 Running: {running_scripts}
🔒 Status: {'Locked' if bot_locked else 'Unlocked'}
⏱ Uptime: {get_uptime()}
            """
            bot.send_message(call.message.chat.id, stats_msg)
            
        elif data == 'uptime':
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"⏱ Uptime: `{get_uptime()}`", parse_mode='Markdown')
            
        elif data == 'mpx_ai':
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "Send your query using /mpx command.")
            
        elif data == 'back_to_main':
            bot.answer_callback_query(call.id)
            markup = create_main_menu_inline(user_id)
            bot.edit_message_text("Main Menu", call.message.chat.id, call.message.message_id, reply_markup=markup)
            
        elif data.startswith('file_'):
            parts = data.split('_')
            if len(parts) >= 3:
                file_owner_id = int(parts[1])
                file_name = '_'.join(parts[2:])
                
                if user_id != file_owner_id and user_id not in admin_ids:
                    bot.answer_callback_query(call.id, "❌ Permission denied.", show_alert=True)
                    return
                
                is_running = is_bot_running(file_owner_id, file_name)
                file_type = next((ft for fn, ft in user_files.get(file_owner_id, []) if fn == file_name), 'unknown')
                
                msg = f"📁 File: `{file_name}`\n👤 Owner: `{file_owner_id}`\n📊 Type: {file_type}\n🟢 Status: {'Running' if is_running else 'Stopped'}"
                
                markup = create_control_buttons(file_owner_id, file_name, is_running)
                bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, 
                                    reply_markup=markup, parse_mode='Markdown')
                bot.answer_callback_query(call.id)
                
        elif data.startswith('start_'):
            parts = data.split('_')
            if len(parts) >= 3:
                file_owner_id = int(parts[1])
                file_name = '_'.join(parts[2:])
                
                if user_id != file_owner_id and user_id not in admin_ids:
                    bot.answer_callback_query(call.id, "❌ Permission denied.", show_alert=True)
                    return
                
                bot.answer_callback_query(call.id, "Starting...")
                
                user_folder = get_user_folder(file_owner_id)
                file_path = os.path.join(user_folder, file_name)
                file_type = next((ft for fn, ft in user_files.get(file_owner_id, []) if fn == file_name), 'py')
                
                if file_type == 'py':
                    threading.Thread(target=run_script, args=(file_path, file_owner_id, user_folder, file_name, call.message)).start()
                elif file_type == 'js':
                    threading.Thread(target=run_js_script, args=(file_path, file_owner_id, user_folder, file_name, call.message)).start()
                
                time.sleep(1)
                is_running = is_bot_running(file_owner_id, file_name)
                markup = create_control_buttons(file_owner_id, file_name, is_running)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
                
        elif data.startswith('stop_'):
            parts = data.split('_')
            if len(parts) >= 3:
                file_owner_id = int(parts[1])
                file_name = '_'.join(parts[2:])
                
                if user_id != file_owner_id and user_id not in admin_ids:
                    bot.answer_callback_query(call.id, "❌ Permission denied.", show_alert=True)
                    return
                
                bot.answer_callback_query(call.id, "Stopping...")
                
                script_key = f"{file_owner_id}_{file_name}"
                if script_key in bot_scripts:
                    kill_process_tree(bot_scripts[script_key])
                    del bot_scripts[script_key]
                
                markup = create_control_buttons(file_owner_id, file_name, False)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
                
        elif data.startswith('delete_'):
            parts = data.split('_')
            if len(parts) >= 3:
                file_owner_id = int(parts[1])
                file_name = '_'.join(parts[2:])
                
                if user_id != file_owner_id and user_id not in admin_ids:
                    bot.answer_callback_query(call.id, "❌ Permission denied.", show_alert=True)
                    return
                
                bot.answer_callback_query(call.id, "Deleting...")
                
                script_key = f"{file_owner_id}_{file_name}"
                if script_key in bot_scripts:
                    kill_process_tree(bot_scripts[script_key])
                    del bot_scripts[script_key]
                
                remove_user_file_db(file_owner_id, file_name)
                
                user_folder = get_user_folder(file_owner_id)
                file_path = os.path.join(user_folder, file_name)
                log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
                
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    if os.path.exists(log_path):
                        os.remove(log_path)
                except:
                    pass
                
                bot.edit_message_text(f"✅ `{file_name}` deleted.", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
                
        elif data == 'subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ Admin only.", show_alert=True)
                return
            
            bot.answer_callback_query(call.id)
            markup = create_subscription_menu()
            bot.edit_message_text("📋 Subscription Management", call.message.chat.id, call.message.message_id, reply_markup=markup)
            
        elif data == 'broadcast':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ Admin only.", show_alert=True)
                return
            
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "📢 Send broadcast message:")
            
        elif data in ['lock_bot', 'unlock_bot']:
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ Admin only.", show_alert=True)
                return
            
            global bot_locked
            bot_locked = (data == 'lock_bot')
            status = "locked" if bot_locked else "unlocked"
            bot.answer_callback_query(call.id, f"Bot {status}.")
            
            markup = create_main_menu_inline(user_id)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
            
        elif data == 'admin_panel':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ Admin only.", show_alert=True)
                return
            
            bot.answer_callback_query(call.id)
            markup = create_admin_panel()
            bot.edit_message_text("👑 Admin Panel", call.message.chat.id, call.message.message_id, reply_markup=markup)
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error occurred.")

# Cleanup function
def cleanup():
    logger.info("🛑 Cleaning up...")
    for script_key, script_info in bot_scripts.items():
        kill_process_tree(script_info)
    bot_scripts.clear()

atexit.register(cleanup)

# Main execution
if __name__ == '__main__':
    print("="*50)
    print("🚀 Telegram Bot Hosting Platform")
    print(f"🤖 Bot: @{bot.get_me().username}")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"📁 Storage: {UPLOAD_BOTS_DIR}")
    print("="*50)
    
    # Start Flask server
    keep_alive()
    
    # Start bot polling
    print("🔄 Starting bot polling...")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        print("🔄 Restarting in 10 seconds...")
        time.sleep(10)
