import time
import threading
import requests
import telebot
from flask import Flask

#1. Chat ID
TOKEN = "9093659313:AAHUFVsccFTF1xTcF9p85hrC_PxB_8kV49Q"
CHAT_ID = "8835091147"

bot = telebot.TeleBot(TOKEN)

# 2. سيرفر Flask البسيط للحفاظ على استمرار تشغيل البوت 24/7 على السحابة
app = Flask(__name__)

@app.route('/')
def home():
    return "Interactive Bot is running 24/7 successfully!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# 3. دالة جلب بيانات السوق والسيولة الحية
def get_market_data():
    market_status = {}
    try:
        btc_res = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=10)
        if btc_res.status_code == 200:
            btc_data = btc_res.json()
            market_status["btc_price"] = float(btc_data.get("lastPrice", 0))
            market_status["btc_change"] = float(btc_data.get("priceChangePercent", 0))

        gold_res = requests.get("https://api.gold-api.com/price/XAU", timeout=10)
        if gold_res.status_code == 200:
            market_status["gold_price"] = float(gold_res.json().get("price", 0))
    except Exception as e:
        print(f"API Error: {e}")
    return market_status

# 4. الاستجابة التلقائية لأوامر تليجرام (مش محتاج تدخل يدوياً)
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🤖 أهلاً بك يا هندسة!\nانا بوت التداول والسيولة الشغال معاك تلقائياً.\n\nالأوامر المتاحة:\n/market - لمعرفة حالة السوق والسيولة الحالية فوراً.")

@bot.message_handler(commands=['market'])
def send_market_status(message):
    bot.reply_to(message, "⏳ جاري فحص السوق والسيولة الآن...")
    data = get_market_data()
    btc_price = data.get("btc_price", 0)
    btc_change = data.get("btc_change", 0)
    gold_price = data.get("gold_price", 0)
    
    report = (
        f"📊 *تقرير حالة السوق الفوري:*\n\n"
        f"💰 سعر البيتكوين: `{btc_price}`\n"
        f"📈 تغير البيتكوين (السيولة): `{btc_change}%`\n"
        f"🪙 سعر الذهب: `{gold_price}`"
    )
    bot.send_message(message.chat.id, report, parse_mode="Markdown")

# 5. تشغيل الاستماع التلقائي للأوامر في الخلفية
def run_telegram_bot():
    print("🤖 بدء الاستماع لأوامر تليجرام تلقائياً...")
    bot.infinity_polling(none_stop=True)

if __name__ == "__main__":
    # تشغيل سيرفر الويب لضمان الـ 24/7
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()
    
    # تشغيل البوت التفاعلي
    t_bot = threading.Thread(target=run_telegram_bot)
    t_bot.daemon = True
    t_bot.start()
    
    # إبقاء السكريبت شغالاً للأبد
    while True:
        time.sleep(1)
