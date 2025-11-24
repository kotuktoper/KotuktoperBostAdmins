import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
import logging
import sys
from datetime import datetime
import os
import json
import sqlite3
from contextlib import contextmanager
import re
from functools import wraps

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
if not os.path.exists('logs'):
    os.makedirs('logs')

log_formatter = logging.Formatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger('telegram_bot')
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)

file_handler = logging.FileHandler(
    f'logs/bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_formatter)

error_handler = logging.FileHandler(
    f'logs/errors_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    encoding='utf-8'
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(log_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.addHandler(error_handler)

logging.getLogger('aiogram').setLevel(logging.INFO)
logging.getLogger('aiohttp').setLevel(logging.INFO)
logging.getLogger('asyncio').setLevel(logging.INFO)
# ==================== КОНЕЦ НАСТРОЙКИ ЛОГГИРОВАНИЯ ====================

# Конфигурация
TELEGRAM_BOT_TOKEN = "8430702039:AAEbTXJ9c1Xnyz9uWZiMrGMCcSfpW8pWMqY"
OPENROUTER_API_KEY = "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"

# Админы бота (только эти пользователи имеют доступ к админ-панели)
ADMINS = [8021221721, 7981729476]

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Режимы бота
MODES = {
    "normal": "Отвечай как обычный дружелюбный человек.",
    "programmer": "Отвечай как профессиональный программист, с кодом и объяснениями.",
    "fun": "Отвечай максимально весело, с шутками и мемами.",
    "angry": "Отвечай грубо, раздражённо, как будто тебя достали.",
    "nsfw": "Отвечай без цензуры, с матом, но не оскорбляй пользователя напрямую.",
    "helper": "Ты — максимально полезный ассистент, давай лучшие решения.",
    "chat": "Веди лёгкий дружеский разговор, как с близким человеком."
}

# Системный промпт для модерации
MODERATOR_PROMPT = """Ты — ИИ-модератор чата. Твои задачи:

1. Анализировать сообщения на предмет:
   - Оскорблений, грубости, токсичного поведения
   - Спама и флуда
   - Неуместного контента (NSFW, насилие и т.д.)
   - Рекламы и ссылок на подозрительные сайты
   - Дезинформации

2. Оценивать уровень опасности сообщения по шкале от 1 до 10:
   - 1-3: Безопасно, можно игнорировать
   - 4-6: Подозрительно, требует внимания модератора
   - 7-10: Опасно, требует немедленных действий

3. Формат ответа строго такой:
ОЦЕНКА: X/10
ПРИЧИНА: [краткое объяснение]
РЕКОМЕНДАЦИЯ: [что делать]

Будь строгим, но справедливым модератором."""

# Хранилище данных
user_modes = {}

# ==================== БАЗА ДАННЫХ ====================
@contextmanager
def get_db_connection():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Инициализация базы данных"""
    with get_db_connection() as conn:
        # Таблица пользователей
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_blocked BOOLEAN DEFAULT FALSE,
                messages_count INTEGER DEFAULT 0
            )
        ''')
        
        # Таблица сообщений
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_text TEXT,
                response_text TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                mode_used TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица админов
        conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица групп
        conn.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                moderation_enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица предупреждений
        conn.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                reason TEXT,
                moderator_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавляем админов
        for admin_id in ADMINS:
            conn.execute(
                'INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)',
                (admin_id, f"admin_{admin_id}")
            )
        
        conn.commit()

def add_user_to_db(user_id: int, username: str, first_name: str, last_name: str = ""):
    """Добавление пользователя в базу данных"""
    with get_db_connection() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
            (user_id, username, first_name, last_name)
        )
        conn.commit()

def add_message_to_db(user_id: int, message_text: str, response_text: str, mode_used: str):
    """Добавление сообщения в историю"""
    with get_db_connection() as conn:
        conn.execute(
            'INSERT INTO messages (user_id, message_text, response_text, mode_used) VALUES (?, ?, ?, ?)',
            (user_id, message_text, response_text, mode_used)
        )
        conn.execute(
            'UPDATE users SET messages_count = messages_count + 1 WHERE user_id = ?',
            (user_id,)
        )
        conn.commit()

def add_group_to_db(chat_id: int, title: str):
    """Добавление группы в базу данных"""
    with get_db_connection() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO groups (chat_id, title) VALUES (?, ?)',
            (chat_id, title)
        )
        conn.commit()

def add_warning_to_db(user_id: int, chat_id: int, reason: str, moderator_id: int):
    """Добавление предупреждения"""
    with get_db_connection() as conn:
        conn.execute(
            'INSERT INTO warnings (user_id, chat_id, reason, moderator_id) VALUES (?, ?, ?, ?)',
            (user_id, chat_id, reason, moderator_id)
        )
        conn.commit()

def get_warnings_count(user_id: int, chat_id: int):
    """Получение количества предупреждений пользователя в чате"""
    with get_db_connection() as conn:
        result = conn.execute(
            'SELECT COUNT(*) as count FROM warnings WHERE user_id = ? AND chat_id = ?',
            (user_id, chat_id)
        ).fetchone()
        return result['count'] if result else 0

def block_user_in_db(user_id: int):
    """Блокировка пользователя в базе данных"""
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE users SET is_blocked = TRUE WHERE user_id = ?',
            (user_id,)
        )
        conn.commit()

def unblock_user_in_db(user_id: int):
    """Разблокировка пользователя в базе данных"""
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE users SET is_blocked = FALSE WHERE user_id = ?',
            (user_id,)
        )
        conn.commit()

def get_user_stats(user_id: int):
    """Получение статистики пользователя"""
    with get_db_connection() as conn:
        user = conn.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        ).fetchone()
        
        messages = conn.execute(
            'SELECT COUNT(*) as count FROM messages WHERE user_id = ?', (user_id,)
        ).fetchone()
        
        return user, messages['count'] if messages else 0

def get_all_users():
    """Получение списка всех пользователей"""
    with get_db_connection() as conn:
        return conn.execute(
            'SELECT * FROM users ORDER BY created_at DESC'
        ).fetchall()

def get_user_messages(user_id: int, limit: int = 10):
    """Получение истории сообщений пользователя"""
    with get_db_connection() as conn:
        return conn.execute(
            'SELECT * FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?',
            (user_id, limit)
        ).fetchall()

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id in ADMINS

def is_user_blocked(user_id: int) -> bool:
    """Проверка, заблокирован ли пользователь"""
    with get_db_connection() as conn:
        user = conn.execute(
            'SELECT is_blocked FROM users WHERE user_id = ?', (user_id,)
        ).fetchone()
        return user and user['is_blocked']

def get_group_settings(chat_id: int):
    """Получение настроек группы"""
    with get_db_connection() as conn:
        group = conn.execute(
            'SELECT * FROM groups WHERE chat_id = ?', (chat_id,)
        ).fetchone()
        return group

def set_group_moderation(chat_id: int, enabled: bool):
    """Включение/выключение модерации в группе"""
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE groups SET moderation_enabled = ? WHERE chat_id = ?',
            (enabled, chat_id)
        )
        conn.commit()

# ==================== ИСПРАВЛЕННЫЕ ФУНКЦИИ ЗАПРОСОВ ====================
def make_openrouter_request(messages: list, temperature: float = 0.9, max_tokens: int = 1000) -> str:
    """
    Универсальная функция для запросов к OpenRouter
    с исправлением проблем кодировки
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    # Безопасные заголовки без Unicode символов
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://t.me/your_bot",
        "X-Title": "AI Bot",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "openai/gpt-4o-mini",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        # Ручная сериализация JSON с правильной кодировкой
        json_data = json.dumps(data, ensure_ascii=False)
        
        # Логируем запрос (без конфиденциальных данных)
        logger.debug(f"📤 Отправка запроса к OpenRouter: {len(messages)} сообщений")
        
        response = requests.post(
            url, 
            data=json_data.encode('utf-8'),  # Явное кодирование в UTF-8
            headers=headers, 
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        answer = result["choices"][0]["message"]["content"]
        logger.debug(f"✅ Успешный ответ от OpenRouter: {len(answer)} символов")
        
        return answer
        
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут запроса к OpenRouter")
        return "⚠️ Превышено время ожидания ответа от сервера. Попробуйте позже."
        
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Ошибка соединения с OpenRouter")
        return "❌ Ошибка соединения. Проверьте интернет и попробуйте еще раз."
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"🌐 HTTP ошибка от OpenRouter: {e.response.status_code}")
        return f"❌ Ошибка API: {e.response.status_code}"
        
    except Exception as e:
        logger.error(f"💥 Неожиданная ошибка при запросе к OpenRouter: {str(e)}")
        return f"❌ Произошла непредвиденная ошибка: {str(e)}"

def ask_openrouter(prompt: str, system_prompt: str, user_id: int) -> str:
    """Основная функция запроса к OpenRouter"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    logger.info(f"🔄 Запрос от пользователя {user_id}")
    return make_openrouter_request(messages)

def moderate_message(message_text: str) -> dict:
    """Анализ сообщения на модерацию"""
    messages = [
        {"role": "system", "content": MODERATOR_PROMPT},
        {"role": "user", "content": f"Проанализируй сообщение: {message_text}"}
    ]
    
    try:
        moderation_result = make_openrouter_request(messages, temperature=0.3, max_tokens=200)
        
        # Парсим результат
        score_match = re.search(r'ОЦЕНКА:\s*(\d+)/10', moderation_result)
        reason_match = re.search(r'ПРИЧИНА:\s*(.+)', moderation_result)
        recommendation_match = re.search(r'РЕКОМЕНДАЦИЯ:\s*(.+)', moderation_result)
        
        score = int(score_match.group(1)) if score_match else 0
        reason = reason_match.group(1) if reason_match else "Не указана"
        recommendation = recommendation_match.group(1) if recommendation_match else "Не указана"
        
        return {
            "score": score,
            "reason": reason,
            "recommendation": recommendation,
            "full_response": moderation_result
        }
        
    except Exception as e:
        logger.error(f"Ошибка парсинга модерации: {e}")
        return {
            "score": 0,
            "reason": "Ошибка анализа",
            "recommendation": "Пропустить",
            "full_response": f"Ошибка: {str(e)}"
        }

async def handle_moderation(message: types.Message):
    """Обработка модерации сообщения"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Получаем настройки группы
    group_settings = get_group_settings(chat_id)
    if not group_settings or not group_settings['moderation_enabled']:
        return None
    
    # Пропускаем короткие сообщения чтобы не спамить
    if len(message.text.strip()) < 3:
        return None
    
    # Пропускаем команды
    if message.text.startswith('/'):
        return None
    
    logger.info(f"🔍 Анализ сообщения от {user_id} в чате {chat_id}")
    
    # Анализируем сообщение
    moderation_result = moderate_message(message.text)
    
    logger.info(f"📊 Результат модерации: оценка {moderation_result['score']}/10")
    
    # Если оценка опасности высокая
    if moderation_result['score'] >= 7:
        # Добавляем предупреждение
        add_warning_to_db(user_id, chat_id, moderation_result['reason'], (await bot.get_me()).id)
        
        warnings_count = get_warnings_count(user_id, chat_id)
        
        # Формируем сообщение предупреждения
        user_mention = message.from_user.mention if message.from_user.mention else f"Пользователь {user_id}"
        
        warning_text = (
            f"⚠️ **Предупреждение модератора**\n\n"
            f"👤 Пользователь: {user_mention}\n"
            f"📊 Уровень опасности: {moderation_result['score']}/10\n"
            f"📝 Причина: {moderation_result['reason']}\n"
            f"🔢 Предупреждений: {warnings_count}\n"
            f"💡 Рекомендация: {moderation_result['recommendation']}"
        )
        
        # Отправляем предупреждение
        await message.reply(warning_text, parse_mode="Markdown")
        
        # Если много предупреждений - предлагаем бан
        if warnings_count >= 3:
            admin_text = "\n\n👮 Администраторам: рекомендуется принять меры."
            await message.reply(
                f"🚨 У пользователя {user_mention} уже {warnings_count} предупреждений!{admin_text}",
                parse_mode="Markdown"
            )
        
        return True
    
    return False

# ==================== ИСПРАВЛЕННЫЙ ДЕКОРАТОР АДМИНА ====================
def admin_required(func):
    """Декоратор для проверки прав админа"""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            logger.warning(f"🚫 Попытка доступа к админ-панели от не-админа: {user_id}")
            await message.answer("❌ У вас нет прав доступа к админ-панели")
            return
        
        # Вызываем оригинальную функцию только с message
        return await func(message)
    return wrapper

# ==================== ЗАЩИЩЕННЫЕ АДМИН КОМАНДЫ ====================
@dp.message(Command("admin"))
@admin_required
async def admin_panel(message: types.Message):
    """Админ панель (только для админов)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика бота", callback_data="admin_stats")
    builder.button(text="👥 Список пользователей", callback_data="admin_users")
    builder.button(text="🚫 Заблокированные", callback_data="admin_blocked")
    builder.button(text="👥 Группы", callback_data="admin_groups")
    builder.button(text="🔄 Обновить базу", callback_data="admin_refresh")
    builder.adjust(2)
    
    await message.answer(
        "🛠 **Админ-панель**\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@dp.message(Command("block"))
@admin_required
async def block_user_command(message: types.Message):
    """Блокировка пользователя (только для админов)"""
    try:
        target_user_id = int(message.text.split()[1])
        block_user_in_db(target_user_id)
        
        await message.answer(f"✅ Пользователь {target_user_id} заблокирован")
        logger.info(f"🔒 Админ {message.from_user.id} заблокировал пользователя {target_user_id}")
        
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /block <user_id>")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("unblock"))
@admin_required
async def unblock_user_command(message: types.Message):
    """Разблокировка пользователя (только для админов)"""
    try:
        target_user_id = int(message.text.split()[1])
        unblock_user_in_db(target_user_id)
        
        await message.answer(f"✅ Пользователь {target_user_id} разблокирован")
        logger.info(f"🔓 Админ {message.from_user.id} разблокировал пользователя {target_user_id}")
        
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /unblock <user_id>")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("userinfo"))
@admin_required
async def user_info_command(message: types.Message):
    """Информация о пользователе (только для админов)"""
    try:
        target_user_id = int(message.text.split()[1])
        user, messages_count = get_user_stats(target_user_id)
        
        if user:
            status = "🚫 Заблокирован" if user['is_blocked'] else "✅ Активен"
            info_text = (
                f"👤 **Информация о пользователе**\n\n"
                f"🆔 ID: `{user['user_id']}`\n"
                f"📛 Имя: {user['first_name'] or 'Не указано'}\n"
                f"👤 Username: @{user['username'] or 'Не указан'}\n"
                f"📅 Регистрация: {user['created_at']}\n"
                f"📊 Сообщений: {messages_count}\n"
                f"🔒 Статус: {status}"
            )
            
            builder = InlineKeyboardBuilder()
            if user['is_blocked']:
                builder.button(text="🔓 Разблокировать", callback_data=f"unblock_{user['user_id']}")
            else:
                builder.button(text="🚫 Заблокировать", callback_data=f"block_{user['user_id']}")
            builder.button(text="📝 История сообщений", callback_data=f"history_{user['user_id']}")
            builder.adjust(2)
            
            await message.answer(info_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        else:
            await message.answer("❌ Пользователь не найден")
            
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /userinfo <user_id>")

# ==================== КОМАНДЫ ДЛЯ ГРУПП ====================
@dp.message(Command("moderation"))
async def moderation_command(message: types.Message):
    """Управление модерацией в группе"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Проверяем, что команда вызвана в группе и от админа группы
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("❌ Эта команда работает только в группах")
        return
    
    if not await is_chat_admin(chat_id, user_id):
        await message.answer("❌ Только администраторы группы могут управлять модерацией")
        return
    
    try:
        action = message.text.split()[1].lower()
        
        if action in ["on", "вкл", "enable"]:
            set_group_moderation(chat_id, True)
            await message.answer("✅ Модерация включена")
        elif action in ["off", "выкл", "disable"]:
            set_group_moderation(chat_id, False)
            await message.answer("❌ Модерация выключена")
        else:
            await message.answer("❌ Использование: /moderation on/off")
            
    except IndexError:
        # Показываем текущий статус
        group_settings = get_group_settings(chat_id)
        status = "✅ Включена" if group_settings and group_settings['moderation_enabled'] else "❌ Выключена"
        await message.answer(f"🔧 Текущий статус модерации: {status}")

async def is_chat_admin(chat_id: int, user_id: int) -> bool:
    """Проверка, является ли пользователь админом чата"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка проверки прав админа: {e}")
        return False

# ==================== ОБРАБОТЧИКИ СОБЫТИЙ ГРУПП ====================
@dp.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_chat(chat_member: ChatMemberUpdated):
    """Обработчик добавления бота в чат"""
    if chat_member.new_chat_member.user.id == (await bot.get_me()).id:
        chat_id = chat_member.chat.id
        chat_title = chat_member.chat.title
        
        # Добавляем группу в базу
        add_group_to_db(chat_id, chat_title)
        
        welcome_text = (
            "🤖 **Привет! Я ИИ-модератор и помощник!**\n\n"
            "🔧 **Мои функции:**\n"
            "• Автоматическая модерация сообщений\n"
            "• Анализ контента на опасность\n"
            "• Предупреждения о нарушениях\n"
            "• Умные ответы в разных стилях\n\n"
            "⚙️ **Команды для админов:**\n"
            "`/moderation on/off` - включить/выключить модерацию\n"
            "`/mode` - выбрать стиль общения\n\n"
            "📝 **Модерация автоматически включена.** "
            "Я буду анализировать сообщения и предупреждать о нарушениях!"
        )
        
        await bot.send_message(chat_id, welcome_text, parse_mode="Markdown")
        logger.info(f"🤖 Бот добавлен в группу: {chat_title} ({chat_id})")

# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ ====================
@dp.message()
async def handle_all_messages(message: types.Message):
    """Обработчик всех сообщений"""
    # Игнорируем служебные сообщения
    if not message.text:
        return
    
    # Если сообщение в группе - обрабатываем модерацию
    if message.chat.type in ["group", "supergroup"]:
        await handle_group_message(message)
    else:
        # Личные сообщения - обычная обработка
        await handle_private_message(message)

async def handle_group_message(message: types.Message):
    """Обработка сообщений в группах"""
    # Проверяем модерацию
    moderation_action = await handle_moderation(message)
    
    # Если сообщение не было заблокировано модерацией, обрабатываем как обычное
    if not moderation_action:
        # Можно добавить ответы бота в группах по определенным триггерам
        if message.text.startswith('!бот') or message.text.startswith('/ask'):
            await handle_private_message(message)

async def handle_private_message(message: types.Message):
    """Обработка личных сообщений"""
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    
    if is_user_blocked(user_id):
        await message.answer("❌ Вы заблокированы в этом боте")
        return
    
    # Добавляем пользователя в базу
    add_user_to_db(user_id, username, message.from_user.first_name or "", message.from_user.last_name or "")
    
    current_mode = user_modes.get(user_id, "normal")
    
    logger.info(f"📨 Входящее сообщение от {user_id} ({username}): {message.text[:50]}...")
    
    await bot.send_chat_action(message.chat.id, "typing")
    
    start_time = datetime.now()
    reply = ask_openrouter(message.text, MODES[current_mode], user_id)
    processing_time = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"📤 Ответ пользователю {user_id} отправлен за {processing_time:.2f} сек")
    
    # Сохраняем сообщение в историю
    add_message_to_db(user_id, message.text, reply, current_mode)
    
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await message.answer(reply[i:i+4000])
    else:
        await message.answer(reply)

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    if is_user_blocked(user_id):
        await message.answer("❌ Вы заблокированы в этом боте")
        return
    
    # Добавляем пользователя в базу
    add_user_to_db(user_id, message.from_user.username or "", 
                  message.from_user.first_name or "", message.from_user.last_name or "")
    
    logger.info(f"👤 Пользователь {user_id} запустил бота")
    
    builder = InlineKeyboardBuilder()
    for mode_key in MODES.keys():
        builder.button(text=mode_key.capitalize(), callback_data=f"mode_{mode_key}")
    builder.adjust(2)
    
    admin_text = "\n\n🛠 Вы администратор! Доступна команда /admin" if is_admin(user_id) else ""
    
    await message.answer(
        f"🤖 Привет! Я бот на базе OpenRouter\n\nВыбери стиль общения:{admin_text}",
        reply_markup=builder.as_markup()
    )

@dp.message(Command("mode"))
async def mode_command(message: types.Message):
    """Команда для смены режима"""
    user_id = message.from_user.id
    
    if is_user_blocked(user_id):
        await message.answer("❌ Вы заблокированы в этом боте")
        return
    
    logger.info(f"🔄 Пользователь {user_id} запросил смену режима")
    await start_command(message)

@dp.message(Command("current_mode"))
async def current_mode_command(message: types.Message):
    """Показывает текущий режим пользователя"""
    user_id = message.from_user.id
    
    if is_user_blocked(user_id):
        await message.answer("❌ Вы заблокированы в этом боте")
        return
    
    current_mode = user_modes.get(user_id, "normal")
    
    logger.info(f"📋 Пользователь {user_id} запросил текущий режим: {current_mode}")
    
    mode_descriptions = {
        "normal": "👤 Обычный режим",
        "programmer": "💻 Режим программиста", 
        "fun": "😄 Развлекательный режим",
        "angry": "😠 Злой режим",
        "nsfw": "🔞 Матерный режим",
        "helper": "🤝 Режим помощника",
        "chat": "💬 Режим общения"
    }
    
    await message.answer(
        f"📋 Твой текущий режим: {mode_descriptions.get(current_mode, '👤 Обычный')}\n"
        f"Используй /mode чтобы изменить режим"
    )

# ==================== CALLBACK ОБРАБОТЧИКИ ====================
@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    """Обработчик callback-запросов"""
    user_id = callback.from_user.id
    data = callback.data
    
    # Обработка режимов (доступно всем)
    if data.startswith("mode_"):
        mode = data[5:]
        if mode in MODES:
            user_modes[user_id] = mode
            await callback.message.edit_text(f"✅ Режим изменён на: {mode}")
        await callback.answer()
        return
    
    # Админские callback (только для админов)
    if not is_admin(user_id):
        await callback.answer("❌ Нет прав доступа")
        return
    
    # Обработка админских callback
    if data == "admin_stats":
        users = get_all_users()
        total_users = len(users)
        active_users = len([u for u in users if not u['is_blocked']])
        blocked_users = len([u for u in users if u['is_blocked']])
        total_messages = sum(user['messages_count'] for user in users)
        
        stats_text = (
            "📊 **Статистика бота**\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"✅ Активных: {active_users}\n"
            f"🚫 Заблокированных: {blocked_users}\n"
            f"💬 Всего сообщений: {total_messages}\n"
            f"🕒 Время работы: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await callback.message.edit_text(stats_text, parse_mode="Markdown")
    
    elif data == "admin_users":
        users = get_all_users()[:20]
        users_text = "👥 **Последние 20 пользователей:**\n\n"
        
        for user in users:
            status = "🚫" if user['is_blocked'] else "✅"
            users_text += f"{status} ID: `{user['user_id']}` - {user['first_name'] or 'No name'}"
            if user['username']:
                users_text += f" (@{user['username']})"
            users_text += f" - {user['messages_count']} сообщ.\n"
        
        await callback.message.edit_text(users_text, parse_mode="Markdown")
    
    elif data == "admin_blocked":
        users = get_all_users()
        blocked = [u for u in users if u['is_blocked']]
        
        if blocked:
            blocked_text = "🚫 **Заблокированные пользователи:**\n\n"
            for user in blocked[:15]:
                blocked_text += f"ID: `{user['user_id']}` - {user['first_name'] or 'No name'}"
                if user['username']:
                    blocked_text += f" (@{user['username']})\n"
                else:
                    blocked_text += "\n"
        else:
            blocked_text = "✅ Нет заблокированных пользователей"
        
        await callback.message.edit_text(blocked_text, parse_mode="Markdown")
    
    elif data.startswith("block_"):
        target_user_id = int(data[6:])
        block_user_in_db(target_user_id)
        await callback.message.edit_text(f"✅ Пользователь {target_user_id} заблокирован")
        logger.info(f"🔒 Админ {user_id} заблокировал пользователя {target_user_id}")
    
    elif data.startswith("unblock_"):
        target_user_id = int(data[8:])
        unblock_user_in_db(target_user_id)
        await callback.message.edit_text(f"✅ Пользователь {target_user_id} разблокирован")
        logger.info(f"🔓 Админ {user_id} разблокировал пользователя {target_user_id}")
    
    elif data.startswith("history_"):
        target_user_id = int(data[8:])
        messages = get_user_messages(target_user_id, 5)
        
        if messages:
            history_text = f"📝 **Последние 5 сообщений пользователя {target_user_id}:**\n\n"
            for msg in reversed(messages):
                history_text += f"🕒 {msg['timestamp']}\n"
                history_text += f"📤: {msg['message_text'][:100]}...\n"
                history_text += f"📥: {msg['response_text'][:100]}...\n"
                history_text += f"🔧 Режим: {msg['mode_used']}\n\n"
        else:
            history_text = f"📝 У пользователя {target_user_id} нет сообщений"
        
        await callback.message.edit_text(history_text, parse_mode="Markdown")
    
    elif data == "admin_refresh":
        init_database()
        await callback.message.edit_text("✅ База данных обновлена")
    
    await callback.answer()

# ==================== ЗАПУСК БОТА ====================
async def main():
    """Основная функция запуска бота"""
    # Инициализируем базу данных
    init_database()
    
    logger.info("🚀 Запуск бота...")
    logger.info(f"⏰ Время запуска: {datetime.now()}")
    
    try:
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот @{bot_info.username} запущен успешно")
        logger.info(f"🆔 ID бота: {bot_info.id}")
        logger.info(f"📛 Имя бота: {bot_info.first_name}")
        
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка при запуске бота: {e}", exc_info=True)
    finally:
        logger.info("🛑 Бот остановлен")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹ Остановка бота по команде пользователя")
    except Exception as e:
        logger.critical(f"💥 Фатальная ошибка: {e}", exc_info=True)
