import telebot
import sqlite3
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
from groq import Groq

# === CONFIG ===
TELEGRAM_TOKEN = "7241781324:AAExPfLBo-66jenP-rdXo6ZGGXjtSa_LIVk"
GROQ_API_KEY = "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"
ADMIN_ID = 1023932092  # Ваш Telegram ID
MIR_CARD = "2200701901154812"
CRYPTO_ADDRESS = "TH92J3hUqbAgpXiC5NtkxFHGe2vB9yUonH"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# === Flask для Uptime ===
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# === БД ===
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    access INTEGER DEFAULT 0,
    expires_at TEXT
)
""")
conn.commit()

# === Команда /start ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔍 Analyze Match", "💳 Donate & Get Access", "⏳ /status")
    bot.send_message(message.chat.id,
        "<b>🤖 AI Match Analyzer</b>\n\n"
        "Analyze matches using AI.\n\n"
        "<b>Pricing:</b>\n"
        "• One-time – $5\n"
        "• Weekly – $25\n"
        "• Monthly – $65\n"
        "• Yearly – $390\n\n"
        "Click the button below after payment.",
        parse_mode="HTML",
        reply_markup=markup
    )

# === Донат и доступ ===
@bot.message_handler(func=lambda msg: msg.text == "💳 Donate & Get Access")
def donate(msg):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("✅ I Paid", callback_data="paid"))
    bot.send_message(msg.chat.id,
        f"Send donation to:\n\n"
        f"💳 MIR: <code>{MIR_CARD}</code>\n"
        f"🪙 USDT TRC20: <code>{CRYPTO_ADDRESS}</code>\n\n"
        "Then press '✅ I Paid'.",
        parse_mode="HTML",
        reply_markup=markup
    )

# === Кнопка "I Paid" ===
@bot.callback_query_handler(func=lambda call: call.data == "paid")
def paid_handler(call):
    uid = call.from_user.id
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("1 Day", callback_data=f"sub_1_{uid}"),
        telebot.types.InlineKeyboardButton("7 Days", callback_data=f"sub_7_{uid}")
    )
    markup.add(
        telebot.types.InlineKeyboardButton("30 Days", callback_data=f"sub_30_{uid}"),
        telebot.types.InlineKeyboardButton("365 Days", callback_data=f"sub_365_{uid}")
    )
    bot.send_message(ADMIN_ID,
        f"User {call.from_user.first_name} ({uid}) requests access.",
        reply_markup=markup
    )
    bot.send_message(uid, "🕓 Payment submitted. Please wait for admin approval.")

# === Подтверждение подписки ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("sub_"))
def set_subscription(call):
    _, days, uid = call.data.split("_")
    uid = int(uid)
    expires = datetime.now() + timedelta(days=int(days))
    cursor.execute("INSERT OR REPLACE INTO users (user_id, access, expires_at) VALUES (?, 1, ?)", (uid, expires.isoformat()))
    conn.commit()
    bot.send_message(uid, f"✅ Access granted until {expires.strftime('%Y-%m-%d %H:%M')}")
    bot.send_message(call.message.chat.id, "Access confirmed.")

# === Проверка статуса /status ===
@bot.message_handler(commands=['status'])
def check_status(message):
    cursor.execute("SELECT access, expires_at FROM users WHERE user_id = ?", (message.chat.id,))
    row = cursor.fetchone()
    if row and row[0] == 1:
        until = datetime.fromisoformat(row[1])
        if until < datetime.now():
            cursor.execute("UPDATE users SET access = 0 WHERE user_id = ?", (message.chat.id,))
            conn.commit()
            bot.send_message(message.chat.id, "❌ Your access has expired.")
        else:
            bot.send_message(message.chat.id, f"✅ Access active until: {until.strftime('%Y-%m-%d %H:%M')}")
    else:
        bot.send_message(message.chat.id, "❌ No active access.")

# === Проверка доступа при анализе ===
@bot.message_handler(func=lambda msg: msg.text == "🔍 Analyze Match")
def ask_for_match(msg):
    cursor.execute("SELECT access, expires_at FROM users WHERE user_id = ?", (msg.chat.id,))
    row = cursor.fetchone()
    if row and row[0] == 1 and datetime.fromisoformat(row[1]) > datetime.now():
        bot.send_message(msg.chat.id, "Send match info (e.g. Arsenal vs Real Madrid):")
    else:
        bot.send_message(msg.chat.id, "❌ Access denied. Please donate first.")

# === Анализ матча ===
@bot.message_handler(func=lambda msg: True)
def analyze_match(msg):
    cursor.execute("SELECT access, expires_at FROM users WHERE user_id = ?", (msg.chat.id,))
    row = cursor.fetchone()
    if not row or row[0] != 1 or datetime.fromisoformat(row[1]) < datetime.now():
        return
    bot.send_message(msg.chat.id, "⚡ Analyzing match...")
    try:
        prompt = f"""
Respond in short format. Include:
1. Prediction of match result (Win/Draw)
2. Total goals in the match
3. Total goals in first or second half
4. Total for one of the teams

Example format:
Match: Arsenal vs Real Madrid
Prediction: Arsenal win
Total: Over 2.5
1st half: Under 1.5
Team total: Arsenal over 1.5

Now analyze: {msg.text}
"""
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content
        for part in range(0, len(answer), 4000):
            bot.send_message(msg.chat.id, answer[part:part+4000])
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Error:\n{e}")

bot.polling()
