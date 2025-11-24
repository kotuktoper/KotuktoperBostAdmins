import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
import logging
import sys
from datetime import datetime
import json
import sqlite3
from contextlib import contextmanager
import re
from functools import wraps

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('telegram_bot')

# ==================== КОНФИГУРАЦИЯ ====================
# Получаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8430702039:AAEbTXJ9c1Xnyz9uWZiMrGMCcSfpW8pWMqY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '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')

# Проверяем наличие обязательных переменных
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'your_telegram_bot_token':
    logger.error("❌ TELEGRAM_BOT_TOKEN не установлен")
    sys.exit(1)

if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == 'your_openrouter_api_key':
    logger.error("❌ OPENROUTER_API_KEY не установлен")
    sys.exit(1)

# Админы бота
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

# ==================== ИСПРАВЛЕННЫЕ ФУНКЦИИ ЗАПРОСОВ ====================
def make_openrouter_request(messages: list, temperature: float = 0.9, max_tokens: int = 1000) -> str:
    """
    Универсальная функция для запросов к OpenRouter
    с исправлением проблем авторизации
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    # Правильные заголовки для OpenRouter
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://t.me/your_bot",
        "X-Title": "Telegram AI Bot",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "openai/gpt-3.5-turbo",  # Используем более доступную модель
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        # Логируем информацию о запросе (без ключа)
        logger.info(f"📤 Отправка запроса к OpenRouter: {len(messages)} сообщений")
        logger.info(f"🔑 Используется API ключ: {OPENROUTER_API_KEY[:10]}...")  # Только первые 10 символов
        
        # Ручная сериализация JSON
        json_data = json.dumps(data, ensure_ascii=False)
        
        response = requests.post(
            url, 
            data=json_data.encode('utf-8'),
            headers=headers, 
            timeout=30
        )
        
        # Детальное логирование ответа
        logger.info(f"📥 Статус ответа: {response.status_code}")
        
        if response.status_code == 401:
            logger.error("🔐 Ошибка 401: Неавторизованный доступ к OpenRouter API")
            logger.error("⚠️ Возможные причины:")
            logger.error("   - Неверный API ключ")
            logger.error("   - Истекший ключ")
            logger.error("   - Неправильные заголовки авторизации")
            return "❌ Ошибка авторизации API. Проверьте API ключ."
        
        elif response.status_code == 402:
            logger.error("💳 Ошибка 402: Недостаточно средств на счету")
            return "❌ Недостаточно средств на счету OpenRouter."
        
        elif response.status_code == 429:
            logger.error("🚦 Ошибка 429: Слишком много запросов")
            return "❌ Превышен лимит запросов. Попробуйте позже."
        
        response.raise_for_status()
        
        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        
        logger.info(f"✅ Успешный ответ от OpenRouter: {len(answer)} символов")
        return answer
        
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут запроса к OpenRouter")
        return "⚠️ Превышено время ожидания ответа от сервера. Попробуйте позже."
        
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Ошибка соединения с OpenRouter")
        return "❌ Ошибка соединения. Проверьте интернет и попробуйте еще раз."
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"🌐 HTTP ошибка от OpenRouter: {e.response.status_code} - {e.response.text}")
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
        
        # Если получили ошибку вместо результата
        if moderation_result.startswith("❌") or moderation_result.startswith("⚠️"):
            return {
                "score": 0,
                "reason": "Ошибка анализа",
                "recommendation": "Пропустить",
                "full_response": moderation_result
            }
        
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

# ==================== ПРОСТАЯ БАЗА ДАННЫХ ====================
user_stats = {}
user_messages = {}

def add_user_message(user_id: int, message_text: str, response_text: str, mode_used: str):
    """Добавление сообщения в историю (упрощенная версия)"""
    if user_id not in user_messages:
        user_messages[user_id] = []
    
    user_messages[user_id].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message_text": message_text,
        "response_text": response_text,
        "mode_used": mode_used
    })
    
    # Ограничиваем историю последними 50 сообщениями
    if len(user_messages[user_id]) > 50:
        user_messages[user_id] = user_messages[user_id][-50:]
    
    # Обновляем статистику
    if user_id not in user_stats:
        user_stats[user_id] = {"messages_count": 0}
    user_stats[user_id]["messages_count"] += 1

def get_user_messages(user_id: int, limit: int = 10):
    """Получение истории сообщений пользователя"""
    if user_id in user_messages:
        return user_messages[user_id][-limit:]
    return []

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id in ADMINS

# ==================== ИСПРАВЛЕННЫЙ ДЕКОРАТОР АДМИНА ====================
def admin_required(func):
    """Декоратор для проверки прав админа"""
    @wraps(func)
    async def wrapper(message: types.Message):
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            logger.warning(f"🚫 Попытка доступа к админ-панели от не-админа: {user_id}")
            await message.answer("❌ У вас нет прав доступа к админ-панели")
            return
        
        return await func(message)
    return wrapper

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
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

@dp.message(Command("admin"))
@admin_required
async def admin_panel(message: types.Message):
    """Админ панель (только для админов)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика бота", callback_data="admin_stats")
    builder.button(text="👥 Список пользователей", callback_data="admin_users")
    builder.button(text="🔄 Проверить API", callback_data="admin_check_api")
    builder.adjust(2)
    
    await message.answer(
        "🛠 **Админ-панель**\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@dp.message(Command("test"))
async def test_command(message: types.Message):
    """Тестовая команда для проверки API"""
    user_id = message.from_user.id
    
    await message.answer("🧪 Тестирую подключение к OpenRouter API...")
    
    test_prompt = "Привет! Ответь коротко 'Тест пройден' если ты меня слышишь."
    test_system = "Отвечай кратко и по делу."
    
    response = ask_openrouter(test_prompt, test_system, user_id)
    
    if response.startswith("❌") or response.startswith("⚠️"):
        await message.answer(f"❌ Тест не пройден:\n{response}")
    else:
        await message.answer(f"✅ Тест пройден! Ответ API: {response}")

@dp.message(Command("apikey"))
async def apikey_command(message: types.Message):
    """Показывает информацию о API ключе (только для админов)"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("❌ У вас нет прав для этой команды")
        return
    
    key_preview = OPENROUTER_API_KEY[:8] + "..." + OPENROUTER_API_KEY[-4:]
    
    await message.answer(
        f"🔑 **Информация о API ключе:**\n\n"
        f"📝 Префикс: `{key_preview}`\n"
        f"📏 Длина: {len(OPENROUTER_API_KEY)} символов\n"
        f"🤖 Бот: @{(await bot.get_me()).username}\n\n"
        f"💡 Используй /test для проверки работы API",
        parse_mode="Markdown"
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
        total_users = len(user_stats)
        total_messages = sum(stats["messages_count"] for stats in user_stats.values())
        
        stats_text = (
            "📊 **Статистика бота**\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"💬 Всего сообщений: {total_messages}\n"
            f"🕒 Время работы: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🔑 API статус: {'✅ Активен' if OPENROUTER_API_KEY else '❌ Не настроен'}"
        )
        await callback.message.edit_text(stats_text, parse_mode="Markdown")
    
    elif data == "admin_users":
        users_text = "👥 **Пользователи бота:**\n\n"
        
        for i, (user_id, stats) in enumerate(list(user_stats.items())[:10], 1):
            users_text += f"{i}. ID: `{user_id}` - {stats['messages_count']} сообщ.\n"
        
        if len(user_stats) > 10:
            users_text += f"\n... и еще {len(user_stats) - 10} пользователей"
        
        await callback.message.edit_text(users_text, parse_mode="Markdown")
    
    elif data == "admin_check_api":
        await callback.message.edit_text("🔄 Проверяю API...")
        
        test_result = make_openrouter_request([
            {"role": "system", "content": "Отвечай кратко."},
            {"role": "user", "content": "Ответь 'OK'"}
        ], max_tokens=10)
        
        if test_result == "OK":
            await callback.message.edit_text("✅ API работает корректно!")
        else:
            await callback.message.edit_text(f"❌ Проблемы с API:\n{test_result}")
    
    await callback.answer()

# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ ====================
@dp.message()
async def handle_private_message(message: types.Message):
    """Обработка личных сообщений"""
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    
    current_mode = user_modes.get(user_id, "normal")
    
    logger.info(f"📨 Входящее сообщение от {user_id} ({username}): {message.text[:50]}...")
    
    await bot.send_chat_action(message.chat.id, "typing")
    
    start_time = datetime.now()
    reply = ask_openrouter(message.text, MODES[current_mode], user_id)
    processing_time = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"📤 Ответ пользователю {user_id} отправлен за {processing_time:.2f} сек")
    
    # Сохраняем сообщение в историю
    add_user_message(user_id, message.text, reply, current_mode)
    
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await message.answer(reply[i:i+4000])
    else:
        await message.answer(reply)

# ==================== ЗАПУСК БОТА ====================
async def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск бота...")
    logger.info(f"⏰ Время запуска: {datetime.now()}")
    
    try:
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот @{bot_info.username} запущен успешно")
        logger.info(f"🆔 ID бота: {bot_info.id}")
        logger.info(f"📛 Имя бота: {bot_info.first_name}")
        
        # Проверяем API ключ
        if OPENROUTER_API_KEY:
            logger.info(f"🔑 API ключ: {OPENROUTER_API_KEY[:8]}...{OPENROUTER_API_KEY[-4:]}")
        else:
            logger.error("❌ API ключ не установлен!")
        
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
