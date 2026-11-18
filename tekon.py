import os
import time
import threading
import requests

TOKEN = os.getenv("BOT_TOKEN")
FINNHUB_KEY = os.getenv("FINNHUB_KEY")
CHAT_ID = os.getenv("CHAT_ID")  # اختياري: رقم الشات اللي يستقبل الأخبار التلقائية

URL = f"https://api.telegram.org/bot{TOKEN}/"
NEWS_URL = "https://finnhub.io/api/v1/news"
CHECK_EVERY = 600  # كل كام ثانية يفحص أخبار جديدة (600 = 10 دقايق)
GOLD_WORDS = ("gold", "xau", "bullion")

subscribers = set()
seen_ids = set()

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


def format_item(item):
    return f"📰 {item.get('headline', '')}\n{item.get('source', '')}\n{item.get('url', '')}"


def is_gold(item):
    text = (item.get("headline", "") + " " + item.get("summary", "")).lower()
    return any(w in text for w in GOLD_WORDS)


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
            "/stop - إيقاف الأخبار التلقائية\n\n"
            "هتوصلك الأخبار الجديدة تلقائيًا كل فترة.",
        )
    elif cmd == "/news":
        send_news(chat_id)
    elif cmd == "/gold":
        send_news(chat_id, gold_only=True)
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
