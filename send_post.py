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
    
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, IOError) as e:
        # Если файл поврежден, удаляем его и возвращаем пустой список
        print(f"Ошибка чтения файла расписания: {e}")
        if os.path.exists(SCHEDULE_FILE):
            os.remove(SCHEDULE_FILE)
        return []
    
    # Поддержка старого формата (один пост)
    if isinstance(data, dict) and "dispatch_at" in data:
        # Пропускаем уже отправленные посты старого формата
        if data.get("sent", False):
            return []
        try:
            dispatch_at = datetime.fromisoformat(data["dispatch_at"])
        except (ValueError, TypeError):
            return []
        # Если время без timezone, считаем его UTC
        if dispatch_at.tzinfo is None:
            dispatch_at = dispatch_at.replace(tzinfo=UTC_TZ)
        post = {
            "id": str(uuid.uuid4()),
            "dispatch_at": dispatch_at,
            "message_text": data.get("message_text", "Привет"),
        }
        return [post]
    
    # Новый формат (список постов)
    if isinstance(data, list):
        posts = []
        for post_data in data:
            # Пропускаем некорректные записи
            if not isinstance(post_data, dict):
                continue
                
            # Пропускаем уже отправленные посты
            if post_data.get("sent", False):
                continue
            
            # Создаем новый словарь для поста
            dispatch_at_str = post_data.get("dispatch_at")
            if not dispatch_at_str:
                continue
                
            try:
                if isinstance(dispatch_at_str, str):
                    dispatch_at = datetime.fromisoformat(dispatch_at_str)
                elif isinstance(dispatch_at_str, datetime):
                    dispatch_at = dispatch_at_str
                else:
                    continue
            except (ValueError, TypeError):
                continue
            
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
    # Убеждаемся, что posts - это список
    if not isinstance(posts, list):
        posts = []
    
    if not posts:
        # Если постов нет, не создаём файл или удаляем существующий
        if os.path.exists(SCHEDULE_FILE):
            os.remove(SCHEDULE_FILE)
        return
    
    # Создаем payload с правильной структурой
    payload = []
    for post in posts:
        # Извлекаем dispatch_at
        dispatch_at = post.get("dispatch_at")
        if isinstance(dispatch_at, datetime):
            dispatch_at_str = dispatch_at.isoformat()
        elif isinstance(dispatch_at, str):
            dispatch_at_str = dispatch_at
        else:
            continue  # Пропускаем посты с некорректным форматом
        
        # Создаем запись для сохранения
        payload_item = {
            "id": post.get("id", str(uuid.uuid4())),
            "dispatch_at": dispatch_at_str,
            "message_text": post.get("message_text", "Привет"),
        }
        payload.append(payload_item)
    
    # Записываем в файл (создаем временный файл для атомарности записи)
    temp_file = SCHEDULE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    
    # Атомарно заменяем старый файл новым
    if os.path.exists(temp_file):
        if os.path.exists(SCHEDULE_FILE):
            os.replace(temp_file, SCHEDULE_FILE)
        else:
            os.rename(temp_file, SCHEDULE_FILE)


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

