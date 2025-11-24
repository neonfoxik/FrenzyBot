import json
import os
from datetime import datetime

import telebot
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
SCHEDULE_FILE = os.path.join(os.path.dirname(__file__), "schedule.json")
MESSAGE_TEXT = "Привет"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")
if not TARGET_CHAT_ID:
    raise ValueError("TARGET_CHAT_ID не найден в переменных окружения!")

bot = telebot.TeleBot(BOT_TOKEN)


def _read_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return None
    with open(SCHEDULE_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)
        data["dispatch_at"] = datetime.fromisoformat(data["dispatch_at"])
        return data


def _write_schedule(data):
    payload = {
        "dispatch_at": data["dispatch_at"].isoformat(),
        "sent": data.get("sent", False),
    }
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def main():
    schedule = _read_schedule()
    if not schedule:
        return

    if schedule.get("sent"):
        return

    now = datetime.now()
    if now < schedule["dispatch_at"]:
        return

    bot.send_message(TARGET_CHAT_ID, MESSAGE_TEXT)
    schedule["sent"] = True
    _write_schedule(schedule)


if __name__ == "__main__":
    main()

