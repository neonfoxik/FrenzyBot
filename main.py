import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import telebot
from dotenv import load_dotenv
from telebot import types

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
    if len(parts) < 2:
        bot.reply_to(
            message,
            "Формат: /schedule YYYY-MM-DD HH:MM [текст сообщения]\n"
            "Время указывается в МСК (Московское время)\n"
            "Например: /schedule 2025-11-24 18:30 Привет всем!\n"
            "Или: /schedule 2025-11-24 18:30",
        )
        return

    try:
        # Парсим время как МСК
        dispatch_at_msk = datetime.strptime(parts[1], "%Y-%m-%d %H:%M")
        dispatch_at_msk = dispatch_at_msk.replace(tzinfo=MSK_TZ)
    except ValueError:
        bot.reply_to(message, "Неверный формат даты. Используй YYYY-MM-DD HH:MM.")
        return

    # Конвертируем из МСК в UTC (вычитаем 3 часа)
    dispatch_at_utc = dispatch_at_msk.astimezone(UTC_TZ)
    
    # Проверяем, что время в будущем (используем UTC время сервера)
    now_utc = datetime.now(UTC_TZ)
    if dispatch_at_utc <= now_utc:
        bot.reply_to(message, "Время должно быть в будущем.")
        return

    message_text = parts[2] if len(parts) > 2 else "Привет"
    
    # Читаем существующие посты - ВАЖНО: всегда читаем заново из файла
    existing_posts = _read_schedule()
    
    # Убеждаемся, что existing_posts - это список
    if not isinstance(existing_posts, list):
        existing_posts = []
    
    # Проверяем, что мы правильно прочитали существующие посты
    existing_count = len(existing_posts)
    
    # Создаем новый пост
    new_post = {
        "id": str(uuid.uuid4()),
        "dispatch_at": dispatch_at_utc,  # Сохраняем в UTC
        "message_text": message_text,
    }
    
    # СОЗДАЕМ НОВЫЙ список: сначала все существующие посты, потом новый
    all_posts = []
    # Добавляем все существующие посты (создаем новые объекты, чтобы не терять данные)
    for existing_post in existing_posts:
        all_posts.append({
            "id": existing_post.get("id", str(uuid.uuid4())),
            "dispatch_at": existing_post.get("dispatch_at"),
            "message_text": existing_post.get("message_text", "Привет"),
        })
    
    # Добавляем новый пост в конец списка
    all_posts.append(new_post)
    
    # Проверяем, что список правильный перед сохранением
    if len(all_posts) != existing_count + 1:
        bot.reply_to(message, f"Ошибка: количество постов не совпадает. Было: {existing_count}, должно стать: {existing_count + 1}, получилось: {len(all_posts)}")
        return
    
    # Сохраняем ВЕСЬ список постов
    _write_schedule(all_posts)
    
    # Проверяем, что данные сохранились правильно
    verify_posts = _read_schedule()
    verify_count = len(verify_posts) if verify_posts else 0
    
    if verify_count != len(all_posts):
        bot.reply_to(
            message,
            f"⚠️ Внимание: было сохранено {len(all_posts)} постов, но прочитано {verify_count}. "
            f"Проверьте файл schedule.json"
        )
    
    # Подтверждаем добавление
    bot.reply_to(
        message, 
        f"Пост запланирован на {dispatch_at_msk.strftime('%Y-%m-%d %H:%M')} МСК.\n"
        f"Текст: {message_text}\n"
        f"Всего запланировано постов: {verify_count}"
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
    bot.infinity_polling(allowed_updates=["chat_join_request", "message"])
