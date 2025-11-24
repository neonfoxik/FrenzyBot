import json
import os
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
    if not os.path.exists(SCHEDULE_FILE):
        return None
    with open(SCHEDULE_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)
        if "dispatch_at" not in data:
            return None
        data["dispatch_at"] = datetime.fromisoformat(data["dispatch_at"])
        return data


def _write_schedule(dispatch_at: datetime):
    payload = {"dispatch_at": dispatch_at.isoformat(), "sent": False}
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


@bot.message_handler(commands=["schedule"])
def handle_schedule(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "Эта команда доступна только администратору.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Формат: /schedule YYYY-MM-DD HH:MM\nНапример: /schedule 2025-11-24 18:30",
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

    _write_schedule(dispatch_at)
    bot.reply_to(
        message, f"Пост запланирован на {dispatch_at.strftime('%Y-%m-%d %H:%M')}."
    )


@bot.message_handler(commands=["schedule_status"])
def handle_schedule_status(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "Эта команда доступна только администратору.")
        return

    schedule = _read_schedule()
    if not schedule:
        bot.reply_to(message, "Пост не запланирован.")
        return

    dispatched = "отправлен" if schedule.get("sent") else "ожидает отправки"
    bot.reply_to(
        message,
        f"Пост запланирован на {schedule['dispatch_at'].strftime('%Y-%m-%d %H:%M')}, статус: {dispatched}.",
    )


FORWARDABLE_CONTENT_TYPES = [
    "text",
    "photo",
    "video",
    "animation",
    "document",
    "audio",
    "voice",
    "video_note",
    "sticker",
]


@bot.message_handler(
    func=lambda message: message.forward_from_chat is not None
    and str(message.from_user.id) == ADMIN_ID,
    content_types=FORWARDABLE_CONTENT_TYPES,
)
def handle_forwarded_chat(message: types.Message):
    chat = message.forward_from_chat
    chat_id = chat.id
    chat_name = chat.title or chat.username or chat_id
    bot.reply_to(message, f"ID форварднутого чата '{chat_name}': {chat_id}")
    bot.send_message(
        ADMIN_ID_INT,
        f"ID чата (через пересланное сообщение) '{chat_name}': {chat_id}",
    )


@bot.chat_join_request_handler()
def approve_join_request(message):
    bot.approve_chat_join_request(message.chat.id, message.from_user.id)


if __name__ == "__main__":
    bot.infinity_polling(allowed_updates=["chat_join_request", "message"])