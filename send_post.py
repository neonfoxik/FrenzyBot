import json
import os
import uuid
from datetime import datetime

import telebot
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
SCHEDULE_FILE = os.path.join(os.path.dirname(__file__), "schedule.json")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")
if not TARGET_CHAT_ID:
    raise ValueError("TARGET_CHAT_ID не найден в переменных окружения!")

bot = telebot.TeleBot(BOT_TOKEN)


def _read_schedule():
    """Читает список запланированных постов из файла"""
    if not os.path.exists(SCHEDULE_FILE):
        return []
    with open(SCHEDULE_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)
        # Поддержка старого формата (один пост)
        if isinstance(data, dict) and "dispatch_at" in data:
            post = {
                "id": str(uuid.uuid4()),
                "dispatch_at": data["dispatch_at"],
                "message_text": data.get("message_text", "Привет"),
                "sent": data.get("sent", False),
            }
            post["dispatch_at"] = datetime.fromisoformat(post["dispatch_at"])
            return [post]
        # Новый формат (список постов)
        if isinstance(data, list):
            for post in data:
                if isinstance(post.get("dispatch_at"), str):
                    post["dispatch_at"] = datetime.fromisoformat(post["dispatch_at"])
            return data
        return []


def _write_schedule(posts):
    """Записывает список запланированных постов в файл"""
    if not posts:
        # Если постов нет, не создаём файл или удаляем существующий
        if os.path.exists(SCHEDULE_FILE):
            os.remove(SCHEDULE_FILE)
        return
    
    payload = []
    for post in posts:
        payload.append({
            "id": post.get("id", str(uuid.uuid4())),
            "dispatch_at": post["dispatch_at"].isoformat() if isinstance(post["dispatch_at"], datetime) else post["dispatch_at"],
            "message_text": post.get("message_text", "Привет"),
        })
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def main():
    posts = _read_schedule()
    if not posts:
        return

    now = datetime.now()
    posts_to_keep = []
    updated = False

    for post in posts:
        # Пропускаем уже отправленные посты (старый формат)
        if post.get("sent"):
            continue

        # Проверяем, наступило ли время отправки
        if now >= post["dispatch_at"]:
            try:
                bot.send_message(TARGET_CHAT_ID, post.get("message_text", "Привет"))
                # Не добавляем пост в список для сохранения - удаляем его
                updated = True
            except Exception as e:
                print(f"Ошибка при отправке поста {post.get('id')}: {e}")
                # В случае ошибки оставляем пост для повторной попытки
                posts_to_keep.append(post)
        else:
            # Пост ещё не готов к отправке - сохраняем его
            posts_to_keep.append(post)

    # Сохраняем только неотправленные посты (удаляем отправленные)
    # Обновляем файл если что-то изменилось или если список постов изменился
    if updated or len(posts) != len(posts_to_keep):
        _write_schedule(posts_to_keep)


if __name__ == "__main__":
    main()

