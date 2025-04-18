import telebot
import sqlite3
from flask import Flask
from threading import Thread
from groq import Groq
from datetime import datetime, timedelta

# === CONFIG ===
TELEGRAM_TOKEN = "7241781324:AAExPfLBo-66jenP-rdXo6ZGGXjtSa_LIVk"
GROQ_API_KEY = "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"
ADMIN_ID = 1023932092
MIR_CARD = "2200701901154812"
CRYPTO_ADDRESS = "TH92J3hUqbAgpXiC5NtkxFHGe2vB9yUonH"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# === Flask (Uptime)
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"
def run(): Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 8080}).start()
run()

# === DB
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    until TIMESTAMP
)""")
conn.commit()

# === /start
@bot.message_handler(commands=['start'])
def start(msg):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔍 Analyze Match", "💳 Donate & Get Access", "/status")
    bot.send_message(msg.chat.id,
        "<b>🤖 AI Match Analyzer</b>\n\n"
        "Analyze football matches using AI predictions.\n"
        "Access requires payment.\n\n"
        "<b>Prices:</b>\n"
        "• 1 Day – $5\n"
        "• 1 Week – $25\n"
        "• 1 Month – $65\n"
        "• 1 Year – $390",
        parse_mode="HTML", reply_markup=markup
    )

# === Donate
@bot.message_handler(func=lambda m: m.text == "💳 Donate & Get Access")
def donate(msg):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("✅ I Paid", callback_data="paid"))
    bot.send_message(msg.chat.id,
        f"Send payment to:\n\n"
        f"💳 MIR Card: <code>{MIR_CARD}</code>\n"
        f"🪙 USDT (TRC20): <code>{CRYPTO_ADDRESS}</code>\n\n"
        "After payment, press '✅ I Paid'. Admin will confirm and set your access.",
        parse_mode="HTML", reply_markup=markup
    )

# === Confirm
@bot.callback_query_handler(func=lambda c: c.data == "paid")
def paid(call):
    uid = call.message.chat.id
    bot.send_message(uid, "Your payment request is sent. Please wait for confirmation.")
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("1 Day", callback_data=f"sub_1_{uid}"),
        telebot.types.InlineKeyboardButton("1 Week", callback_data=f"sub_7_{uid}"),
        telebot.types.InlineKeyboardButton("1 Month", callback_data=f"sub_30_{uid}"),
        telebot.types.InlineKeyboardButton("1 Year", callback_data=f"sub_365_{uid}")
    )
    bot.send_message(ADMIN_ID,
        f"User @{call.from_user.username or 'NoUsername'} ({uid}) pressed I Paid.\n"
        f"Choose access period:",
        reply_markup=markup
    )

# === Admin Set Period
@bot.callback_query_handler(func=lambda c: c.data.startswith("sub_"))
def set_sub(call):
    if call.from_user.id != ADMIN_ID: return
    days, uid = int(call.data.split("_")[1]), int(call.data.split("_")[2])
    until = datetime.now() + timedelta(days=days)
    cursor.execute("INSERT OR REPLACE INTO users (user_id, until) VALUES (?, ?)", (uid, until))
    conn.commit()
    bot.send_message(uid, f"✅ Access granted until {until.strftime('%Y-%m-%d %H:%M')}")
    bot.send_message(ADMIN_ID, f"✅ Subscription activated for user {uid}")

# === Status
@bot.message_handler(commands=['status'])
def status(msg):
    cursor.execute("SELECT until FROM users WHERE user_id=?", (msg.chat.id,))
    row = cursor.fetchone()
    if row:
        end = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f")
        bot.send_message(msg.chat.id, f"⏳ Your access is valid until:\n<b>{end.strftime('%Y-%m-%d %H:%M')}</b>", parse_mode="HTML")
    else:
        bot.send_message(msg.chat.id, "❌ You don't have active access.")

# === Analyze Button
@bot.message_handler(func=lambda m: m.text == "🔍 Analyze Match")
def access_check(msg):
    cursor.execute("SELECT until FROM users WHERE user_id=?", (msg.chat.id,))
    row = cursor.fetchone()
    if row:
        until = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f")
        if until > datetime.now():
            bot.send_message(msg.chat.id, "✅ Send match details:")
        else:
            bot.send_message(msg.chat.id, "❌ Your access expired. Renew it via 💳 Donate & Get Access")
    else:
        bot.send_message(msg.chat.id, "❌ No active subscription. Use 💳 Donate & Get Access")

# === Match Analysis
@bot.message_handler(func=lambda msg: True)
def analyze_match(msg):
    cursor.execute("SELECT until FROM users WHERE user_id=?", (msg.chat.id,))
    row = cursor.fetchone()
    if not row or datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f") < datetime.now():
        return
    bot.send_message(msg.chat.id, "⚡ Analyzing...")
    try:
        prompt = f"""You are a match prediction assistant. Respond in this structure:
        
Match: {msg.text}

Prediction:
• Winner or Draw
• Match Total
• 1st Half or 2nd Half Total
• Team Total

Return only the result in a short format with clear betting lines and no extra text."""
        res = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.choices[0].message.content
        bot.send_message(msg.chat.id, text)
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Error:\n{e}")

bot.polling()
