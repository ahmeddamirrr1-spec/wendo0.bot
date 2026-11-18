import requests
import os

TOKEN = "9212754473:AAHC9ohMwDYCNqV5aG_PsVlSK7XJxJy5txk"
URL = f"https://api.telegram.org/bot{TOKEN}/"
def get_updates(offset=None):
    url = URL + "getUpdates?timeout=100"
    if offset:
        url += f"&offset={offset}"
    response = requests.get(url)
    return response.json()

def send_message(chat_id, text):
    url = URL + f"sendMessage?chat_id={chat_id}&text={text}"
    requests.get(url)

def main():
    print("البوت يعمل الآن ويراقب الرسائل...")
    last_update_id = None
    
    while True:
        updates = get_updates(last_update_id)
        if "result" in updates:
            for update in updates["result"]:
                last_update_id = update["update_id"] + 1
                
                if "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    user_message = update["message"]["text"]
                    
                    print(f"وصلت رسالة: {user_message}")
                    
                    if user_message.lower() in ["hi", "hello", "/start"]:
                        send_message(chat_id, "أهلاً بك! أنا بوت الذهب والفوركس الخاص بك 🚀")
                    else:
                        send_message(chat_id, f"لقد استقبلت رسالتك: {user_message}")
        
        time.sleep(1)

if __name__ == "__main__":
    main()
