import json
import os
import uuid
from datetime import datetime

import telebot
from dotenv import load_dotenv
from telebot import types

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
SCHEDULE_FILE = os.path.join(os.path.dirname(__file__), "schedule.json")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID не найден в переменных окружения!")
try:
    ADMIN_ID_INT = int(ADMIN_ID)
except ValueError as exc:
    raise ValueError("ADMIN_ID должен быть числом Telegram пользователя.") from exc

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
            post["dispatch_at"] = datetime.fromisoformat(post["dispatch_at"])
            return [post]
        # Новый формат (список постов)
        if isinstance(data, list):
            posts = []
            for post in data:
                # Пропускаем уже отправленные посты
                if post.get("sent", False):
                    continue
                if isinstance(post.get("dispatch_at"), str):
                    post["dispatch_at"] = datetime.fromisoformat(post["dispatch_at"])
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


@bot.message_handler(commands=["schedule"])
def handle_schedule(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "Эта команда доступна только администратору.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Формат: /schedule YYYY-MM-DD HH:MM [текст сообщения]\n"
            "Например: /schedule 2025-11-24 18:30 Привет всем!\n"
            "Или: /schedule 2025-11-24 18:30",
        )
        return

    try:
        dispatch_at = datetime.strptime(parts[1], "%Y-%m-%d %H:%M")
    except ValueError:
        bot.reply_to(message, "Неверный формат даты. Используй YYYY-MM-DD HH:MM.")
        return

    if dispatch_at <= datetime.now():
        bot.reply_to(message, "Время должно быть в будущем.")
        return

    message_text = parts[2] if len(parts) > 2 else "Привет"
    
    posts = _read_schedule()
    new_post = {
        "id": str(uuid.uuid4()),
        "dispatch_at": dispatch_at,
        "message_text": message_text,
    }
    posts.append(new_post)
    _write_schedule(posts)
    
    bot.reply_to(
        message, 
        f"Пост запланирован на {dispatch_at.strftime('%Y-%m-%d %H:%M')}.\n"
        f"Текст: {message_text}"
    )


@bot.message_handler(commands=["schedule_status"])
def handle_schedule_status(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "Эта команда доступна только администратору.")
        return

    posts = _read_schedule()
    if not posts:
        bot.reply_to(message, "Нет запланированных постов.")
        return

    if len(posts) == 1:
        post = posts[0]
        bot.reply_to(
            message,
            f"Пост запланирован на {post['dispatch_at'].strftime('%Y-%m-%d %H:%M')}.\n"
            f"Текст: {post.get('message_text', 'Привет')}"
        )
    else:
        text = f"Всего запланировано постов: {len(posts)}\n\n"
        for i, post in enumerate(posts, 1):
            dispatch_time = post['dispatch_at'].strftime('%Y-%m-%d %H:%M')
            message_preview = post.get('message_text', 'Привет')[:30]
            if len(post.get('message_text', 'Привет')) > 30:
                message_preview += "..."
            text += f"{i}. {dispatch_time} - ⏳ ожидает отправки\n   {message_preview}\n"
        bot.reply_to(message, text)

@bot.chat_join_request_handler()
def approve_join_request(message):
    bot.approve_chat_join_request(message.chat.id, message.from_user.id)


if __name__ == "__main__":
    bot.infinity_polling(allowed_updates=["chat_join_request", "message"])
