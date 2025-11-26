import json
import os
import uuid
from datetime import datetime, timedelta, timezone
import threading

import telebot
from dotenv import load_dotenv
from telebot import types
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Часовые пояса
MSK_TZ = timezone(timedelta(hours=3))  # МСК = UTC+3
UTC_TZ = timezone.utc  # UTC

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

# Временное хранилище (user_id: dict)
schedule_step_buffer = {}
schedule_step_lock = threading.Lock()

SUPPORTED_MEDIA_TYPES = ("photo", "document", "video", "audio")


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
    
    # Поддержка старого формата (один пост) - автоматическая миграция
    # ВАЖНО: это должно происходить только один раз при миграции
    if isinstance(data, dict) and "dispatch_at" in data:
        # Пропускаем уже отправленные посты старого формата
        if data.get("sent", False):
            # Удаляем файл старого формата
            try:
                os.remove(SCHEDULE_FILE)
            except:
                pass
            return []
        
        # Мигрируем старый формат в новый
        dispatch_at_str = data.get("dispatch_at")
        if not dispatch_at_str:
            try:
                os.remove(SCHEDULE_FILE)
            except:
                pass
            return []
            
        try:
            dispatch_at = datetime.fromisoformat(dispatch_at_str)
        except (ValueError, TypeError):
            # Если не удается распарсить дату, удаляем файл
            try:
                os.remove(SCHEDULE_FILE)
            except:
                pass
            return []
        
        # Если время без timezone, считаем его UTC
        if dispatch_at.tzinfo is None:
            dispatch_at = dispatch_at.replace(tzinfo=UTC_TZ)
        
        post = {
            "id": data.get("id", str(uuid.uuid4())),
            "dispatch_at": dispatch_at,
            "message_text": data.get("message_text", "Привет"),
        }
        
        # Сохраняем в новом формате и возвращаем список
        # ВАЖНО: после миграции файл должен быть в новом формате
        _write_schedule([post])
        return [post]
    
    # Новый формат (список постов)
    if isinstance(data, list):
        posts = []
        total_in_file = len(data)
        skipped_count = 0
        
        for post_data in data:
            # Пропускаем некорректные записи
            if not isinstance(post_data, dict):
                skipped_count += 1
                continue
                
            # Пропускаем уже отправленные посты
            if post_data.get("sent", False):
                skipped_count += 1
                continue
            
            # Создаем новый словарь для поста, чтобы не модифицировать исходный
            dispatch_at_str = post_data.get("dispatch_at")
            if not dispatch_at_str:
                skipped_count += 1
                continue
                
            try:
                if isinstance(dispatch_at_str, str):
                    dispatch_at = datetime.fromisoformat(dispatch_at_str)
                elif isinstance(dispatch_at_str, datetime):
                    dispatch_at = dispatch_at_str
                else:
                    skipped_count += 1
                    continue  # Пропускаем посты с некорректным форматом времени
            except (ValueError, TypeError):
                skipped_count += 1
                continue  # Пропускаем посты с некорректной датой
            
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
        
        # Логируем, если мы пропустили посты
        if skipped_count > 0:
            print(f"При чтении пропущено {skipped_count} из {total_in_file} постов")
        
        return posts
    
    # Если формат не распознан, возвращаем пустой список
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
    skipped_count = 0
    
    for post in posts:
        if not isinstance(post, dict):
            skipped_count += 1
            continue
            
        # Извлекаем dispatch_at
        dispatch_at = post.get("dispatch_at")
        if dispatch_at is None:
            skipped_count += 1
            continue
            
        if isinstance(dispatch_at, datetime):
            dispatch_at_str = dispatch_at.isoformat()
        elif isinstance(dispatch_at, str):
            dispatch_at_str = dispatch_at
        else:
            skipped_count += 1
            continue  # Пропускаем посты с некорректным форматом
        
        # Создаем запись для сохранения
        payload_item = {
            "id": post.get("id", str(uuid.uuid4())),
            "dispatch_at": dispatch_at_str,
            "message_text": post.get("message_text", "Привет"),
            "media": post.get("media", []),
        }
        payload.append(payload_item)
    
    # Проверяем, что мы не потеряли посты
    if skipped_count > 0:
        print(f"Предупреждение: пропущено {skipped_count} постов при записи")
    
    if not payload:
        # Если после обработки ничего не осталось, удаляем файл
        if os.path.exists(SCHEDULE_FILE):
            os.remove(SCHEDULE_FILE)
        return
    
    # Записываем в файл (создаем временный файл для атомарности записи)
    temp_file = SCHEDULE_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        
        # Атомарно заменяем старый файл новым
        if os.path.exists(temp_file):
            if os.path.exists(SCHEDULE_FILE):
                os.replace(temp_file, SCHEDULE_FILE)
            else:
                os.rename(temp_file, SCHEDULE_FILE)
    except Exception as e:
        print(f"Ошибка при записи файла расписания: {e}")
        # Удаляем временный файл при ошибке
        if os.path.exists(temp_file):
            os.remove(temp_file)


@bot.message_handler(commands=["schedule"])
def handle_schedule(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "Эта команда доступна только администратору.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(
            message,
            "Формат: /schedule YYYY-MM-DD HH:MM\n"
            "Сначала отправьте дату и время, например:/schedule 2025-12-01 16:30",
        )
        return

    time_part = parts[1] + " " + parts[2]
    try:
        dispatch_at_msk = datetime.strptime(time_part, "%Y-%m-%d %H:%M")
        dispatch_at_msk = dispatch_at_msk.replace(tzinfo=MSK_TZ)
    except ValueError:
        bot.reply_to(message, "Неверный формат даты. Используй YYYY-MM-DD HH:MM.")
        return

    dispatch_at_utc = dispatch_at_msk.astimezone(UTC_TZ)
    now_utc = datetime.now(UTC_TZ)
    if dispatch_at_utc <= now_utc:
        bot.reply_to(message, "Время должно быть в будущем.")
        return

    with schedule_step_lock:
        schedule_step_buffer[message.from_user.id] = {
            "dispatch_at": dispatch_at_utc,
        }
    bot.reply_to(
        message,
        f"ОК! Дата и время запланированы: {dispatch_at_msk.strftime('%Y-%m-%d %H:%M')} МСК\nТеперь отправьте текст сообщения, который надо запланировать.",
    )
    bot.register_next_step_handler(message, handle_schedule_message_text)


def handle_schedule_message_text(message):
    user_id = message.from_user.id
    with schedule_step_lock:
        data = schedule_step_buffer.pop(user_id, None)
    if data is None:
        bot.reply_to(message, "Ошибка: этап не найден. Начните с /schedule.")
        return
    message_text = message.text if message.text else "Привет"
    dispatch_at_utc = data["dispatch_at"]
    # Начинаем этап сбора файлов
    with schedule_step_lock:
        schedule_step_buffer[user_id] = {
            "dispatch_at": dispatch_at_utc,
            "message_text": message_text,
            "media": [],
            "active": True,  # помечаем, что этап добавления файлов открыт
        }
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Продолжить", callback_data="done_media_upload"))
    bot.reply_to(
        message,
        "Теперь вы можете отправить 1 или несколько файлов (фото, видео, документ, аудио).\nКогда закончите — нажмите 'Продолжить'.",
        reply_markup=markup,
    )

# Исправить: сообщения с медиа добавляются только если этап активен, и нет next_step_handler после каждого файла
@bot.message_handler(content_types=["photo", "document", "video", "audio"])
def handle_media_during_schedule(message):
    user_id = message.from_user.id
    with schedule_step_lock:
        data = schedule_step_buffer.get(user_id)
        if not data or not data.get("active"):
            return  # Игнор отсутсвия этапа
        # добавляем файл
        added = False
        for attr in SUPPORTED_MEDIA_TYPES:
            file = getattr(message, attr, None)
            if file:
                if isinstance(file, list):
                    for photo in file:
                        data["media"].append({"type": attr, "file_id": photo.file_id})
                        added = True
                else:
                    data["media"].append({"type": attr, "file_id": file.file_id})
                    added = True
        schedule_step_buffer[user_id] = data
    if added:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Продолжить", callback_data="done_media_upload"))
        bot.reply_to(
            message,
            "Файл добавлен! Можете отправить ещё или нажмите 'Продолжить' для завершения.",
            reply_markup=markup,
        )

@bot.callback_query_handler(func=lambda call: call.data == 'done_media_upload')
def schedule_inline_finish(call):
    user_id = call.from_user.id
    with schedule_step_lock:
        data = schedule_step_buffer.pop(user_id, None)
    if data is None or not data.get("active"):
        bot.answer_callback_query(call.id, text="Этап не найден, начните сначала /schedule.")
        return
    data["active"] = False
    finish_schedule_with_media(call.message, data)
    bot.answer_callback_query(call.id, text="Пост сохранён!")

def finish_schedule_with_media(message, data):
    dispatch_at_utc = data["dispatch_at"]
    message_text = data["message_text"]
    media = data.get("media", [])
    # Читаем существующие посты
    existing_posts = _read_schedule()
    if not isinstance(existing_posts, list):
        existing_posts = []
    # Дубликаты запрещаем если совпадает всё
    duplicate = False
    for existing_post in existing_posts:
        d1 = existing_post.get("dispatch_at")
        if isinstance(d1, str):
            try:
                d1 = datetime.fromisoformat(d1)
            except Exception:
                pass
        if isinstance(d1, datetime):
            d1 = d1.astimezone(UTC_TZ).isoformat()
        d2 = dispatch_at_utc.astimezone(UTC_TZ).isoformat()
        if (
            d1 == d2 and
            existing_post.get("message_text", "Привет") == message_text and
            existing_post.get("media", []) == media
        ):
            duplicate = True
            break
    if duplicate:
        bot.reply_to(message, "Пост с таким содержимым уже есть!")
        return
    # Добавляем пост
    new_post = {
        "id": str(uuid.uuid4()),
        "dispatch_at": dispatch_at_utc,
        "message_text": message_text,
        "media": media or [],
    }
    all_posts = [
        {
            "id": existing_post.get("id", str(uuid.uuid4())),
            "dispatch_at": existing_post.get("dispatch_at"),
            "message_text": existing_post.get("message_text", "Привет"),
            "media": existing_post.get("media", []),
        }
        for existing_post in existing_posts
    ]
    all_posts.append(new_post)
    _write_schedule(all_posts)
    verify_posts = _read_schedule()
    verify_count = len(verify_posts) if verify_posts else 0
    bot.reply_to(
        message,
        f"Пост запланирован на {dispatch_at_utc.astimezone(MSK_TZ).strftime('%Y-%m-%d %H:%M')} МСК!\nВсего запланировано: {verify_count}\nФайлов прикреплено: {len(media)}",
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

    def format_time_for_display(dt):
        """Конвертирует UTC время в МСК для отображения"""
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC_TZ)
        dt_msk = dt.astimezone(MSK_TZ)
        return dt_msk.strftime('%Y-%m-%d %H:%M')

    if len(posts) == 1:
        post = posts[0]
        dispatch_at = post['dispatch_at']
        if isinstance(dispatch_at, str):
            dispatch_at = datetime.fromisoformat(dispatch_at)
        if dispatch_at.tzinfo is None:
            dispatch_at = dispatch_at.replace(tzinfo=UTC_TZ)
        dispatch_msk = dispatch_at.astimezone(MSK_TZ)
        
        bot.reply_to(
            message,
            f"Пост запланирован на {dispatch_msk.strftime('%Y-%m-%d %H:%M')} МСК.\n"
            f"Текст: {post.get('message_text', 'Привет')}"
        )
    else:
        text = f"Всего запланировано постов: {len(posts)}\n\n"
        for i, post in enumerate(posts, 1):
            dispatch_at = post['dispatch_at']
            if isinstance(dispatch_at, str):
                dispatch_at = datetime.fromisoformat(dispatch_at)
            if dispatch_at.tzinfo is None:
                dispatch_at = dispatch_at.replace(tzinfo=UTC_TZ)
            dispatch_msk = dispatch_at.astimezone(MSK_TZ)
            
            dispatch_time = dispatch_msk.strftime('%Y-%m-%d %H:%M')
            message_preview = post.get('message_text', 'Привет')[:30]
            if len(post.get('message_text', 'Привет')) > 30:
                message_preview += "..."
            text += f"{i}. {dispatch_time} МСК - ⏳ ожидает отправки\n   {message_preview}\n"
        bot.reply_to(message, text)

@bot.chat_join_request_handler()
def approve_join_request(message):
    bot.approve_chat_join_request(message.chat.id, message.from_user.id)


if __name__ == "__main__":
    bot.infinity_polling(allowed_updates=["message", "callback_query", "chat_join_request"])
