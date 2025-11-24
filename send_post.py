import json
import os
import uuid
from datetime import datetime, timezone

import telebot
from dotenv import load_dotenv

UTC_TZ = timezone.utc  # UTC

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
            # Пропускаем уже отправленные посты старого формата
            if data.get("sent", False):
                return []
            post = {
                "id": str(uuid.uuid4()),
                "dispatch_at": data["dispatch_at"],
                "message_text": data.get("message_text", "Привет"),
            }
            dispatch_at = datetime.fromisoformat(post["dispatch_at"])
            # Если время без timezone, считаем его UTC
            if dispatch_at.tzinfo is None:
                dispatch_at = dispatch_at.replace(tzinfo=UTC_TZ)
            post["dispatch_at"] = dispatch_at
            return [post]
        # Новый формат (список постов)
        if isinstance(data, list):
            posts = []
            for post_data in data:
                # Пропускаем уже отправленные посты (старый формат)
                if post_data.get("sent", False):
                    continue
                
                # Создаем новый словарь для поста, чтобы не модифицировать исходный
                dispatch_at_str = post_data.get("dispatch_at")
                if isinstance(dispatch_at_str, str):
                    dispatch_at = datetime.fromisoformat(dispatch_at_str)
                elif isinstance(dispatch_at_str, datetime):
                    dispatch_at = dispatch_at_str
                else:
                    continue  # Пропускаем посты с некорректным форматом времени
                
                # Если время без timezone, считаем его UTC
                if dispatch_at.tzinfo is None:
                    dispatch_at = dispatch_at.replace(tzinfo=UTC_TZ)
                
                # Создаем новый пост с правильным форматом
                post = {
                    "id": post_data.get("id", str(uuid.uuid4())),
                    "dispatch_at": dispatch_at,
                    "message_text": post_data.get("message_text", "Привет"),
                }
                posts.append(post)
            return posts
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

    now = datetime.now(UTC_TZ)  # Используем UTC время
    posts_to_keep = []
    updated = False

    for post in posts:
        dispatch_at = post["dispatch_at"]
        # Убеждаемся, что время в UTC
        if isinstance(dispatch_at, str):
            dispatch_at = datetime.fromisoformat(dispatch_at)
        if dispatch_at.tzinfo is None:
            dispatch_at = dispatch_at.replace(tzinfo=UTC_TZ)
        post["dispatch_at"] = dispatch_at

        # Проверяем, наступило ли время отправки
        if now >= dispatch_at:
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

