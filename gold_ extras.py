import requests f
from telegram.ext import CommandHandler

BINANCE_KLINES = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "XAUUSDT"      # لو مش شغال جرّب PAXGUSDT
INTERVAL = "5m"         # الفريم: 1m / 5m / 15m / 1h

last_hammer = {}


# ---------------------------------------------------------------
# 1) سيولة الذهب
# ---------------------------------------------------------------
def gold_liquidity(symbol=SYMBOL, interval=INTERVAL, limit=12):
    r = requests.get(BINANCE_KLINES,
                     params={"symbol": symbol, "interval": interval, "limit": limit},
                     timeout=10)
    r.raise_for_status()
    candles = r.json()

    total = sum(float(c[5]) for c in candles)   # الحجم الكلي
    buy = sum(float(c[9]) for c in candles)     # شراء عدواني
    sell = total - buy
    delta = buy - sell
    buy_pct = buy / total * 100 if total else 50

    if buy_pct >= 55:
        side = "🟢 سيولة شراء داخلة"
    elif buy_pct <= 45:
        side = "🔴 سيولة بيع داخلة"
    else:
        side = "⚪ متوازن"

    return (f"🥇 سيولة الذهب ({limit} شمعة {interval})\n"
            f"{side}\n"
            f"شراء: {buy:,.0f} | بيع: {sell:,.0f}\n"
            f"الفرق (Delta): {delta:+,.0f}\n"
            f"نسبة الشراء: {buy_pct:.1f}%")


async def goldflow(update, context):
    try:
        await update.message.reply_text(gold_liquidity())
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في جلب سيولة الذهب: {e}")


# ---------------------------------------------------------------
# 2) المطرقة المؤكدة
# ---------------------------------------------------------------
def _parse(k):
    return dict(t=k[0], o=float(k[1]), h=float(k[2]), l=float(k[3]),
                c=float(k[4]), v=float(k[5]))


def check_hammer(symbol=SYMBOL, interval=INTERVAL):
    r = requests.get(BINANCE_KLINES,
                     params={"symbol": symbol, "interval": interval, "limit": 15},
                     timeout=10)
    r.raise_for_status()
    c = r.json()

    H = _parse(c[-3])   # شمعة المطرقة
    C = _parse(c[-2])   # شمعة التأكيد (آخر شمعة مقفولة)

    # 1) شكل المطرقة
    rng = H["h"] - H["l"]
    if rng == 0:
        return None
    body = abs(H["c"] - H["o"])
    lower = min(H["o"], H["c"]) - H["l"]
    upper = H["h"] - max(H["o"], H["c"])
    if not (lower >= 2 * body and lower >= rng * 0.6 and upper <= rng * 0.15):
        return None

    # 2) لازم هبوط قبلها
    if not float(c[-3][4]) < float(c[-8][4]):
        return None

    # 3) شمعة التأكيد: صعود واضح مش كدّاب
    c_rng = C["h"] - C["l"]
    c_body = C["c"] - C["o"]
    if c_rng == 0:
        return None
    confirmed = (
        c_body > 0 and
        C["c"] > H["h"] and
        C["l"] >= H["l"] and
        c_body >= c_rng * 0.5 and
        C["v"] >= H["v"] * 0.8
    )
    if not confirmed:
        return None

    return {"time": C["t"], "price": C["c"], "low": H["l"], "high": H["h"]}


async def hammer_job(context):
    chat_id = context.job.chat_id
    try:
        res = check_hammer()
    except Exception:
        return
    if res and last_hammer.get(chat_id) != res["time"]:
        last_hammer[chat_id] = res["time"]
        await context.bot.send_message(
            chat_id,
            f"🔨✅ مطرقة مؤكدة على الذهب ({INTERVAL})\n"
            f"السعر الحالي: {res['price']:.2f}\n"
            f"قمة المطرقة: {res['high']:.2f}\n"
            f"قاع المطرقة (وقف الخسارة): {res['low']:.2f}")


async def hammer_on(update, context):
    chat_id = update.effective_chat.id
    for j in context.job_queue.get_jobs_by_name(f"hammer_{chat_id}"):
        j.schedule_removal()
    context.job_queue.run_repeating(hammer_job, interval=60, first=5,
                                    chat_id=chat_id, name=f"hammer_{chat_id}")
    await update.message.reply_text("✅ تنبيه المطرقة المؤكدة اتفعّل")


async def hammer_off(update, context):
    chat_id = update.effective_chat.id
    for j in context.job_queue.get_jobs_by_name(f"hammer_{chat_id}"):
        j.schedule_removal()
    await update.message.reply_text("⛔ تنبيه المطرقة اتوقف")


# ---------------------------------------------------------------
# تسجيل كل الأوامر بسطر واحد
# ---------------------------------------------------------------
def register_gold_handlers(app):
    app.add_handler(CommandHandler("goldflow", goldflow))
    app.add_handler(CommandHandler("hammer_on", hammer_on))
    app.add_handler(CommandHandler("hammer_off", hammer_off))
