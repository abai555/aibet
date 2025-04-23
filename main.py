import telebot
import sqlite3
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
from groq import Groq
import os

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MIR_CARD = os.getenv("MIR_CARD")
CRYPTO_ADDRESS = os.getenv("CRYPTO_ADDRESS")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# === Flask Uptime ===
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# === Database ===
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    expires_at TEXT
)
""")
conn.commit()

# === Helper: check subscription ===
def has_active_subscription(user_id):
    cursor.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row:
        return datetime.now() < datetime.fromisoformat(row[0])
    return False

# === /start ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔍 Analyze Match", "💳 Donate & Get Access", "/status")
    bot.send_message(message.chat.id,
        "<b>🤖 AI Match Analyzer</b>\n\n"
        "Analyze football matches with AI.\n\n"
        "<b>Pricing:</b>\n"
        "• One-time (1 match): $5\n"
        "• Weekly: $25\n"
        "• Monthly: $65\n"
        "• Yearly: $390",
        parse_mode="HTML",
        reply_markup=markup
    )

# === /status ===
@bot.message_handler(commands=['status'])
def check_status(message):
    cursor.execute("SELECT expires_at FROM users WHERE user_id=?", (message.chat.id,))
    row = cursor.fetchone()
    if row:
        expires_at = datetime.fromisoformat(row[0])
        if datetime.now() < expires_at:
            bot.send_message(message.chat.id, f"✅ Your access is valid until: {expires_at.strftime('%Y-%m-%d %H:%M')}")
            return
    bot.send_message(message.chat.id, "❌ No active subscription found.")

# === Payment Info ===
@bot.message_handler(func=lambda msg: msg.text == "💳 Donate & Get Access")
def donate_info(msg):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("✅ I Paid", callback_data="paid"))
    bot.send_message(msg.chat.id,
        f"<b>To get access:</b>\n\n"
        f"💳 MIR Card: <code>{MIR_CARD}</code>\n"
        f"🪙 USDT (TRC20): <code>{CRYPTO_ADDRESS}</code>\n\n"
        f"Then press the button below.",
        parse_mode="HTML",
        reply_markup=markup
    )

# === "I Paid" button pressed ===
@bot.callback_query_handler(func=lambda call: call.data == "paid")
def handle_payment(call):
    markup = telebot.types.InlineKeyboardMarkup()
    for label, days in [("1 Match", 0), ("1 Day", 1), ("1 Week", 7), ("1 Month", 30), ("1 Year", 365)]:
        markup.add(telebot.types.InlineKeyboardButton(label, callback_data=f"grant_{call.from_user.id}_{days}"))
    bot.send_message(ADMIN_ID,
        f"💰 Payment request from @{call.from_user.username or 'User'} ({call.from_user.id})",
        reply_markup=markup
    )
    bot.send_message(call.message.chat.id, "🕓 Payment submitted. Please wait for confirmation.")

# === Admin grants access ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("grant_"))
def grant_access(call):
    if call.from_user.id != ADMIN_ID:
        return
    _, user_id, days = call.data.split("_")
    user_id = int(user_id)
    days = int(days)
    if days == 0:
        expires_at = datetime.now() + timedelta(minutes=15)
    else:
        expires_at = datetime.now() + timedelta(days=days)
    cursor.execute("INSERT OR REPLACE INTO users (user_id, expires_at) VALUES (?, ?)", (user_id, expires_at.isoformat()))
    conn.commit()
    bot.send_message(user_id, f"✅ Access granted until {expires_at.strftime('%Y-%m-%d %H:%M')}")
    bot.send_message(call.message.chat.id, "User access confirmed.")

# === Match Button ===
@bot.message_handler(func=lambda msg: msg.text == "🔍 Analyze Match")
def analyze_prompt(msg):
    if has_active_subscription(msg.chat.id):
        bot.send_message(msg.chat.id, "✅ Send match info (teams, stage, etc):")
    else:
        bot.send_message(msg.chat.id, "❌ Access denied. Click 💳 Donate & Get Access")

# === Analyze Logic ===
@bot.message_handler(func=lambda msg: True)
def analyze_match(msg):
    if not has_active_subscription(msg.chat.id):
        return
    bot.send_message(msg.chat.id, "⚡ Analyzing match...")
    try:
        prompt = f"""
You are a sports analyst AI. Provide compact match predictions using this structure:

• Winner: [Team or Draw]  
• Total Goals: [Over/Under X.X]  
• Half Total: [First or Second Half Over/Under]  
• Team Total: [Team and Over/Under]  
• Confidence: [Low / Medium / High / Very High]

Match details: {msg.text}
"""
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content
        for part in range(0, len(answer), 4000):
            bot.send_message(msg.chat.id, answer[part:part+4000])
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Error: {e}")

bot.polling()
