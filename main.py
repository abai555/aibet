import telebot
import sqlite3
from flask import Flask
from threading import Thread
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

# === Flask uptime ===
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# === DB ===
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    access INTEGER DEFAULT 0
)
""")
conn.commit()

# === Start ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔍 Analyze Match", "💳 Donate & Get Access")
    bot.send_message(message.chat.id,
        "<b>🤖 AI Match Analyzer</b>\n\n"
        "Analyze football matches using AI.\n\n"
        "<b>Pricing:</b>\n"
        "• One-time – $5\n"
        "• Weekly – $25\n"
        "• Monthly – $65\n"
        "• Yearly – $390",
        parse_mode="HTML",
        reply_markup=markup
    )

# === Donate Info ===
@bot.message_handler(func=lambda msg: msg.text == "💳 Donate & Get Access")
def donate_info(msg):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("✅ I Paid", callback_data="paid"))
    bot.send_message(msg.chat.id,
        f"Send donation to:\n\n"
        f"💳 MIR Card: <code>{MIR_CARD}</code>\n"
        f"🪙 Crypto (TRC20): <code>{CRYPTO_ADDRESS}</code>\n\n"
        "Then press '✅ I Paid'. Access will be granted after confirmation.",
        parse_mode="HTML",
        reply_markup=markup
    )

# === Handle "I Paid" ===
@bot.callback_query_handler(func=lambda call: call.data == "paid")
def paid(call):
    uid = call.message.chat.id
    bot.send_message(uid, "🕓 Payment submitted. Please wait for approval.")
    bot.send_message(ADMIN_ID,
        f"🧾 New request from @{call.from_user.username} ({uid})",
        reply_markup=telebot.types.InlineKeyboardMarkup([
            [telebot.types.InlineKeyboardButton("✅ Grant", callback_data=f"grant_{uid}"),
             telebot.types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}")]
        ])
    )

# === Handle Admin Callback ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("grant_") or call.data.startswith("reject_"))
def admin_confirm(call):
    uid = int(call.data.split("_")[1])
    if call.from_user.id != ADMIN_ID:
        return
    if call.data.startswith("grant_"):
        cursor.execute("INSERT OR REPLACE INTO users (user_id, access) VALUES (?, 1)", (uid,))
        conn.commit()
        bot.send_message(uid, "✅ Access granted!")
    else:
        bot.send_message(uid, "❌ Access denied.")

# === Analyze Match Button ===
@bot.message_handler(func=lambda msg: msg.text == "🔍 Analyze Match")
def match_button(msg):
    cursor.execute("SELECT access FROM users WHERE user_id=?", (msg.chat.id,))
    access = cursor.fetchone()
    if access and access[0] == 1:
        bot.send_message(msg.chat.id, "Send the match name and stage:")
    else:
        bot.send_message(msg.chat.id, "❌ You need to donate to get access.")

# === Match Analysis ===
@bot.message_handler(func=lambda msg: True)
def analyze(msg):
    cursor.execute("SELECT access FROM users WHERE user_id=?", (msg.chat.id,))
    access = cursor.fetchone()
    if not access or access[0] != 1:
        return
    bot.send_message(msg.chat.id, "⚡ Analyzing match...")
    try:
        prompt = f"""Ты спортивный аналитик. Проанализируй матч кратко по ключевым критериям:
- Исход (одна команда или ничья)
- Тотал матча (меньше/больше)
- Тотал первого или второго тайма
- Тотал одной из команд

Пример:
Исход: Победа Реала
Тотал: Больше 2.5
1-й тайм: Тотал меньше 1.5
Команда: Реал больше 1.5

Матч: {msg.text}
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
