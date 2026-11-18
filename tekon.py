import os
import re
import time
import threading
from collections import deque
import requests

TOKEN = os.getenv("BOT_TOKEN")
FINNHUB_KEY = os.getenv("FINNHUB_KEY")
CHAT_ID = os.getenv("CHAT_ID")  # اختياري: رقم الشات اللي يستقبل الأخبار التلقائية

URL = f"https://api.telegram.org/bot{TOKEN}/"
NEWS_URL = "https://finnhub.io/api/v1/news"
CHECK_EVERY = 600  # كل كام ثانية يفحص أخبار جديدة (600 = 10 دقايق)
GOLD_RE = re.compile(r"\b(gold|xau|xauusd|bullion)\b")
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
TRANSLATE = False  # الترجمة متوقفة دلوقتي، خليها True لما نشغّلها
SHOW_ORIGINAL = False  # خليها True لو عايز العنوان الإنجليزي تحت العربي

subscribers = set()
seen_ids = set()
translation_cache = {}

if CHAT_ID:
    try:
        subscribers.add(int(CHAT_ID))
    except ValueError:
        print("CHAT_ID غير صالح")


def get_updates(offset=None):
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    r = requests.get(URL + "getUpdates", params=params, timeout=40)
    return r.json()


def send_message(chat_id, text):
    for i in range(0, len(text), 4000):
        try:
            requests.post(
                URL + "sendMessage",
                data={
                    "chat_id": chat_id,
                    "text": text[i:i + 4000],
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
        except requests.RequestException as e:
            print("send error:", e)


def fetch_news(category):
    if not FINNHUB_KEY:
        return []
    try:
        r = requests.get(
            NEWS_URL,
            params={"category": category, "token": FINNHUB_KEY},
            timeout=15,
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except (requests.RequestException, ValueError) as e:
        print("news error:", e)
        return []


def translate_ar(text):
    if not text:
        return text
    if text in translation_cache:
        return translation_cache[text]
    try:
        r = requests.get(
            TRANSLATE_URL,
            params={"client": "gtx", "sl": "en", "tl": "ar", "dt": "t", "q": text},
            timeout=10,
        )
        data = r.json()
        result = "".join(part[0] for part in data[0] if part and part[0])
        if result:
            if len(translation_cache) > 2000:
                translation_cache.clear()
            translation_cache[text] = result
            return result
    except Exception as e:
        print("translate error:", e)
    return text


def format_item(item):
    headline = item.get("headline", "")
    title = translate_ar(headline) if TRANSLATE else headline
    lines = [f"📰 {title}"]
    if SHOW_ORIGINAL and title != headline:
        lines.append(headline)
    lines.append(item.get("source", ""))
    lines.append(item.get("url", ""))
    return "\n".join(lines)


def is_gold(item):
    text = (item.get("headline", "") + " " + item.get("summary", "")).lower()
    return bool(GOLD_RE.search(text))


def send_news(chat_id, gold_only=False):
    if not FINNHUB_KEY:
        send_message(chat_id, "مفتاح الأخبار FINNHUB_KEY مش متضاف في Railway.")
        return
    if gold_only:
        items = [i for i in fetch_news("forex") + fetch_news("general") if is_gold(i)]
    else:
        items = fetch_news("forex")
    items.sort(key=lambda i: i.get("datetime", 0), reverse=True)
    items = items[:5]
    if not items:
        send_message(chat_id, "مفيش أخبار متاحة دلوقتي.")
        return
    for item in items:
        send_message(chat_id, format_item(item))


# ---------------- السيولة (شراء / بيع) ----------------
FLOW_ENABLED = True
FLOW_EVERY = 20          # كل كام ثانية يفحص الصفقات
FLOW_WINDOW = 300        # نافذة التجميع بالثواني (5 دقايق)
FLOW_DOMINANCE = 0.70    # لازم جهة واحدة تكون 70% أو أكتر من الحجم
FLOW_COOLDOWN = 600      # أقل وقت بين تنبيهين لنفس العملة (ثواني)
MARKET_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]

# big_trade = صفقة واحدة كبيرة (دولار) | window_alert = حجم جهة واحدة في 5 دقايق (دولار)
FLOW_SYMBOLS = {
    "PAXGUSDT": {"name": "الذهب (PAXG)", "big_trade": 150_000, "window_alert": 1_000_000},
    "BTCUSDT": {"name": "بيتكوين", "big_trade": 1_000_000, "window_alert": 15_000_000},
    "ETHUSDT": {"name": "إيثريوم", "big_trade": 500_000, "window_alert": 8_000_000},
}

SIDE_AR = {"buy": "شراء 🟢", "sell": "بيع 🔴"}
flow_state = {
    sym: {"last_id": None, "history": deque(), "last_alert": 0.0}
    for sym in FLOW_SYMBOLS
}


def money(x):
    if x >= 1_000_000:
        return f"${x / 1_000_000:.2f}M"
    return f"${x / 1_000:.0f}K"


def market_get(path, params):
    for host in MARKET_HOSTS:
        try:
            r = requests.get(host + path, params=params, timeout=10)
            if r.status_code == 200:
                return r.json()
            print("market status:", host, r.status_code)
        except (requests.RequestException, ValueError) as e:
            print("market error:", host, e)
    return None


def broadcast(text):
    for chat in list(subscribers):
        send_message(chat, text)


def flow_cycle(symbol, cfg):
    st = flow_state[symbol]
    if st["last_id"] is None:
        data = market_get("/api/v3/aggTrades", {"symbol": symbol, "limit": 1})
        if data:
            st["last_id"] = data[-1]["a"]
        return

    buy = sell = 0.0
    big = []
    last_price = None
    for _ in range(10):
        data = market_get(
            "/api/v3/aggTrades",
            {"symbol": symbol, "fromId": st["last_id"] + 1, "limit": 1000},
        )
        if not data:
            break
        for t in data:
            price = float(t["p"])
            usd = price * float(t["q"])
            last_price = price
            # m = True يعني المشتري هو الـ maker، يعني اللي ضرب السوق بائع
            side = "sell" if t["m"] else "buy"
            if side == "buy":
                buy += usd
            else:
                sell += usd
            if usd >= cfg["big_trade"]:
                big.append((usd, side, price))
        st["last_id"] = data[-1]["a"]
        if len(data) < 1000:
            break

    now = time.time()
    st["history"].append((now, buy, sell, last_price))
    while st["history"] and now - st["history"][0][0] > FLOW_WINDOW * 2:
        st["history"].popleft()

    # صفقات كبيرة
    for usd, side, price in sorted(big, reverse=True)[:3]:
        broadcast(
            f"🐋 صفقة كبيرة {SIDE_AR[side]}\n"
            f"{cfg['name']}\n"
            f"💰 {money(usd)} | السعر: {price:,.2f}"
        )

    # دخول سيولة في اتجاه واحد خلال آخر 5 دقايق
    recent = [h for h in st["history"] if now - h[0] <= FLOW_WINDOW]
    rb = sum(h[1] for h in recent)
    rs = sum(h[2] for h in recent)
    total = rb + rs
    if total <= 0:
        return
    side, vol = ("buy", rb) if rb >= rs else ("sell", rs)
    if (
        vol >= cfg["window_alert"]
        and vol / total >= FLOW_DOMINANCE
        and now - st["last_alert"] >= FLOW_COOLDOWN
    ):
        st["last_alert"] = now
        price = last_price or next((h[3] for h in reversed(recent) if h[3]), 0)
        icon = "📈" if side == "buy" else "📉"
        broadcast(
            f"{icon} دخول سيولة {SIDE_AR[side]}\n"
            f"{cfg['name']} (آخر 5 دقايق)\n"
            f"🟢 شراء {money(rb)} | 🔴 بيع {money(rs)}\n"
            f"الجهة الأقوى: {vol / total * 100:.0f}% | السعر: {price:,.2f}"
        )


def flow_report():
    now = time.time()
    lines = ["📊 السيولة آخر 5 دقايق (صفقات السوق الفوري):"]
    for symbol, cfg in FLOW_SYMBOLS.items():
        hist = [h for h in flow_state[symbol]["history"] if now - h[0] <= FLOW_WINDOW]
        b = sum(h[1] for h in hist)
        s_ = sum(h[2] for h in hist)
        t = b + s_
        if not hist or t <= 0:
            lines.append(f"\n{cfg['name']}: لسه بيجمع بيانات")
            continue
        lines.append(
            f"\n{cfg['name']}\n"
            f"🟢 شراء {money(b)} ({b / t * 100:.0f}%)\n"
            f"🔴 بيع {money(s_)} ({s_ / t * 100:.0f}%)"
        )
    return "\n".join(lines)


def flow_loop():
    while True:
        for symbol, cfg in FLOW_SYMBOLS.items():
            try:
                flow_cycle(symbol, cfg)
            except Exception as e:
                print("flow error:", symbol, e)
        time.sleep(FLOW_EVERY)


def handle(msg):
    chat_id = msg["chat"]["id"]
    parts = msg["text"].strip().lower().split()
    if not parts:
        return
    cmd = parts[0].split("@")[0]

    if cmd == "/start":
        subscribers.add(chat_id)
        send_message(
            chat_id,
            "🚀 أهلاً بك! أنا بوت الذهب والفوركس الخاص بك\n\n"
            "/news - آخر أخبار الفوركس\n"
            "/gold - أخبار الذهب\n"
            "/flow - السيولة (شراء/بيع) آخر 5 دقايق\n"
            "/stop - إيقاف الأخبار التلقائية\n\n"
            "هتوصلك الأخبار الجديدة تلقائيًا كل فترة.",
        )
    elif cmd == "/news":
        send_news(chat_id)
    elif cmd == "/gold":
        send_news(chat_id, gold_only=True)
    elif cmd == "/flow":
        send_message(chat_id, flow_report())
    elif cmd == "/id":
        send_message(chat_id, f"رقم الشات: {chat_id}")
    elif cmd == "/stop":
        subscribers.discard(chat_id)
        send_message(chat_id, "تم إيقاف الأخبار التلقائية. ابعت /start لتشغيلها تاني.")


def auto_news_loop():
    first_run = True
    while True:
        try:
            items = fetch_news("forex") + fetch_news("general")
            if items:
                items.sort(key=lambda i: i.get("datetime", 0))
                new = [i for i in items if i.get("id") not in seen_ids]
                for i in items:
                    seen_ids.add(i.get("id"))
                if len(seen_ids) > 5000:
                    seen_ids.clear()
                if not first_run:
                    for item in new[-5:]:
                        for chat in list(subscribers):
                            send_message(chat, format_item(item))
                first_run = False
        except Exception as e:
            print("auto news error:", e)
        time.sleep(CHECK_EVERY)


def main():
    print("البوت يعمل الآن ويراقب الرسائل...")
    if not TOKEN:
        print("BOT_TOKEN مش موجود في Variables")
    if not FINNHUB_KEY:
        print("FINNHUB_KEY مش موجود في Variables")

    threading.Thread(target=auto_news_loop, daemon=True).start()
    if FLOW_ENABLED:
        threading.Thread(target=flow_loop, daemon=True).start()

    offset = None
    while True:
        try:
            updates = get_updates(offset)
            if not updates.get("ok"):
                print("telegram error:", updates)
                time.sleep(5)
                continue
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if msg and "text" in msg:
                    handle(msg)
        except Exception as e:
            print("loop error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
