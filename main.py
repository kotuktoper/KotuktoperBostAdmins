import re
import telebot
import time
import logging
import sqlite3
import json
import random
import threading
import sys
import math
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Optional

# МАКСИМАЛЬНОЕ ЛОГИРОВАНИЕ
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8489739703:AAGMnY4bPaKbXfzEOUtF64dDrgmT963_NzU"
bot = telebot.TeleBot(TOKEN)

logger.info("🟢 ===== МЕГА-БОТ ULTIMATE PRO MAX EDITION ЗАПУСКАЕТСЯ =====")

# Глобальные админы
GLOBAL_ADMINS = [5627578930, 7981729476,-1001716767636,1001716767636]

# СИСТЕМА ЗАДЕРЖКИ
class CooldownSystem:
    def __init__(self):
        self.user_cooldowns = {}
        self._lock = threading.Lock()
    
    def can_play(self, user_id, game_type, cooldown_seconds=5):
        key = f"{user_id}_{game_type}"
        current_time = time.time()
        
        with self._lock:
            if key in self.user_cooldowns:
                last_play = self.user_cooldowns[key]
                if current_time - last_play < cooldown_seconds:
                    return False
            
            self.user_cooldowns[key] = current_time
            return True
    
    def get_remaining_time(self, user_id, game_type, cooldown_seconds=5):
        key = f"{user_id}_{game_type}"
        current_time = time.time()
        
        with self._lock:
            if key in self.user_cooldowns:
                last_play = self.user_cooldowns[key]
                remaining = cooldown_seconds - (current_time - last_play)
                return max(0, round(remaining))
        
        return 0
    
    def cleanup_old_entries(self):
        """Очистка старых записей"""
        current_time = time.time()
        with self._lock:
            self.user_cooldowns = {
                k: v for k, v in self.user_cooldowns.items() 
                if current_time - v < 86400
            }

cooldown = CooldownSystem()

# БАЗА ДАННЫХ
class UltimateBotDB:
    def __init__(self):
        self.conn = sqlite3.connect('ultimate_bot_pro.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                settings TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                permissions TEXT,
                added_by INTEGER,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                word TEXT,
                violation_type TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                reason TEXT,
                warned_by INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                action TEXT,
                reason TEXT,
                duration INTEGER,
                moderator_id INTEGER,
                moderator_name TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                date TEXT,
                mutes_count INTEGER DEFAULT 0,
                warns_count INTEGER DEFAULT 0,
                bans_count INTEGER DEFAULT 0,
                kicks_count INTEGER DEFAULT 0,
                violations_count INTEGER DEFAULT 0,
                messages_count INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER,
                chat_id INTEGER,
                username TEXT,
                first_name TEXT,
                messages_count INTEGER DEFAULT 0,
                balance INTEGER DEFAULT 1000,
                level INTEGER DEFAULT 1,
                experience INTEGER DEFAULT 0,
                reputation INTEGER DEFAULT 0,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                vip_until DATETIME DEFAULT NULL,
                achievements TEXT DEFAULT '[]',
                inventory TEXT DEFAULT '[]',
                PRIMARY KEY (user_id, chat_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_stats (
                user_id INTEGER,
                chat_id INTEGER,
                game_type TEXT,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                last_played DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id, game_type)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_marriage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER,
                user2_id INTEGER,
                user1_name TEXT,
                user2_name TEXT,
                chat_id INTEGER,
                married_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                divorce_count INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_crime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                crime_type TEXT,
                success BOOLEAN,
                amount INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_business (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                business_type TEXT,
                level INTEGER DEFAULT 1,
                income INTEGER DEFAULT 0,
                last_collected DATETIME DEFAULT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS roulette_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                creator_id INTEGER,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                bets TEXT DEFAULT '{}',
                result_number INTEGER DEFAULT -1
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_stats ON user_stats(user_id, chat_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_moderation_logs ON moderation_logs(chat_id, timestamp)')
        
        self.conn.commit()
        
        # ДОБАВЛЯЕМ НАСТРОЙКИ КУЛДАУНОВ В СУЩЕСТВУЮЩИЕ ЧАТЫ
        try:
            cursor.execute('SELECT chat_id, settings FROM chats')
            chats = cursor.fetchall()
            
            for chat_id, settings_json in chats:
                if settings_json:
                    settings = json.loads(settings_json)
                    # Добавляем настройки кулдаунов если их нет
                    if 'cooldown_work' not in settings:
                        settings.update({
                            'cooldown_work': 300,      # 5 минут
                            'cooldown_crime': 300,     # 5 минут  
                            'cooldown_daily': 86400,   # 24 часа
                            'cooldown_games': 30,      # 30 секунд
                            'cooldown_enabled': True   # Включить кулдауны
                        })
                        cursor.execute('UPDATE chats SET settings = ? WHERE chat_id = ?', 
                                     (json.dumps(settings), chat_id))
            
            self.conn.commit()
            logger.debug("✅ Настройки кулдаунов добавлены в существующие чаты")
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления настроек кулдаунов: {e}")
        
        logger.debug("✅ Все таблицы БД созданы")

    def add_chat(self, chat_id, title):
        try:
            cursor = self.conn.cursor()
            default_settings = json.dumps({
               # АНТИ-КАНАЛЫ
'anti_channels': True,  # Блокировать сообщения от каналов
                 'delete_mats': True, 'delete_links': False, 'delete_crypto': False,
                'anti_spam': True, 'auto_mute': True, 'welcome_enabled': True,
                'games_enabled': True, 'max_warns': 3, 'mute_duration': 15,
                'auto_reports': True, 'anti_flood': True, 'anti_caps': False,
                'anti_stickers': False, 'anti_voices': False, 'auto_role': False,
                'admins_immune': True, 'anti_channels': True,  # Блокировать сообщения от каналов
                # НОВЫЕ НАСТРОЙКИ КУЛДАУНОВ
                'cooldown_work': 300,      # 5 минут
                'cooldown_crime': 300,     # 5 минут  
                'cooldown_daily': 86400,   # 24 часа
                'cooldown_games': 30,      # 30 секунд
                'cooldown_enabled': True   # Включить кулдауны
            })
            cursor.execute('INSERT OR REPLACE INTO chats (chat_id, title, settings) VALUES (?, ?, ?)', 
                         (chat_id, title, default_settings))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка добавления чата: {e}")
    
    def get_chat_settings(self, chat_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT settings FROM chats WHERE chat_id = ?', (chat_id,))
            result = cursor.fetchone()
            return json.loads(result[0]) if result else None
        except Exception as e:
            logger.error(f"❌ Ошибка получения настроек: {e}")
            return None
    
    def update_chat_settings(self, chat_id, settings):
        try:
            cursor = self.conn.cursor()
            cursor.execute('UPDATE chats SET settings = ? WHERE chat_id = ?', 
                         (json.dumps(settings), chat_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления настроек: {e}")
    
    def add_chat_admin(self, chat_id, user_id, username, first_name, added_by, permissions='moderator'):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO chat_admins (chat_id, user_id, username, first_name, added_by, permissions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (chat_id, user_id, username, first_name, added_by, permissions))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка добавления админа: {e}")
    
    def is_chat_admin(self, chat_id, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT 1 FROM chat_admins WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки админа: {e}")
            return False
    
    def add_super_admin(self, user_id, username, first_name):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO chat_admins (chat_id, user_id, username, first_name, permissions, added_by)
                VALUES (0, ?, ?, ?, 'super_admin', ?)
            ''', (user_id, username, first_name, user_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка добавления супер-админа: {e}")
    
    def is_super_admin(self, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT 1 FROM chat_admins WHERE user_id = ? AND permissions = "super_admin"', (user_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки супер-админа: {e}")
            return False
    
    def update_user_stats(self, chat_id, user_id, username, first_name):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_stats 
                (user_id, chat_id, username, first_name, messages_count, last_active)
                VALUES (?, ?, ?, ?, COALESCE((SELECT messages_count + 1 FROM user_stats WHERE user_id = ? AND chat_id = ?), 1), CURRENT_TIMESTAMP)
            ''', (user_id, chat_id, username, first_name, user_id, chat_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики: {e}")
    
    def get_user_balance(self, chat_id, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT balance FROM user_stats WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
            result = cursor.fetchone()
            return result[0] if result else 1000
        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса: {e}")
            return 1000
    
    def add_user_balance(self, chat_id, user_id, amount):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_stats 
                (user_id, chat_id, balance)
                VALUES (?, ?, COALESCE((SELECT balance + ? FROM user_stats WHERE user_id = ? AND chat_id = ?), ?))
            ''', (user_id, chat_id, amount, user_id, chat_id, 1000 + amount))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления баланса: {e}")
    
    def get_top_users(self, chat_id, limit=10):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT user_id, first_name, username, messages_count, balance, level 
                FROM user_stats WHERE chat_id = ? ORDER BY balance DESC LIMIT ?
            ''', (chat_id, limit))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения топа: {e}")
            return []
    
    def add_violation(self, chat_id, user_id, username, first_name, word, violation_type):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO violations (chat_id, user_id, username, first_name, word, violation_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (chat_id, user_id, username, first_name, word, violation_type))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка добавления нарушения: {e}")
    
    def get_user_violations(self, chat_id, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM violations WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"❌ Ошибка получения нарушений: {e}")
            return 0
    
    def add_warn(self, chat_id, user_id, username, first_name, reason, warned_by):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO warns (chat_id, user_id, username, first_name, reason, warned_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (chat_id, user_id, username, first_name, reason, warned_by))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка добавления варна: {e}")
    
    def get_user_warns(self, chat_id, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"❌ Ошибка получения варнов: {e}")
            return 0
    
    def remove_all_warns(self, chat_id, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM warns WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка удаления варнов: {e}")
    
    def add_moderation_log(self, chat_id, user_id, username, first_name, action, reason, duration, moderator_id, moderator_name):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO moderation_logs (chat_id, user_id, username, first_name, action, reason, duration, moderator_id, moderator_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, user_id, username, first_name, action, reason, duration, moderator_id, moderator_name))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка добавления лога модерации: {e}")
    
    def get_today_stats(self, chat_id):
        try:
            cursor = self.conn.cursor()
            today = datetime.now().strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN action = 'mute' THEN 1 END) as mutes,
                    COUNT(CASE WHEN action = 'warn' THEN 1 END) as warns,
                    COUNT(CASE WHEN action = 'ban' THEN 1 END) as bans,
                    COUNT(CASE WHEN action = 'kick' THEN 1 END) as kicks
                FROM moderation_logs 
                WHERE chat_id = ? AND DATE(timestamp) = ?
            ''', (chat_id, today))
            
            mod_stats = cursor.fetchone()
            
            cursor.execute('SELECT COUNT(*) FROM violations WHERE chat_id = ? AND DATE(timestamp) = ?', (chat_id, today))
            violations = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM user_stats WHERE chat_id = ? AND DATE(last_active) = ?', (chat_id, today))
            messages = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM game_stats WHERE chat_id = ? AND DATE(last_played) = ?', (chat_id, today))
            games = cursor.fetchone()[0]
            
            return {
                'mutes': mod_stats[0] if mod_stats else 0,
                'warns': mod_stats[1] if mod_stats else 0,
                'bans': mod_stats[2] if mod_stats else 0,
                'kicks': mod_stats[3] if mod_stats else 0,
                'violations': violations,
                'messages': messages,
                'games': games
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {'mutes': 0, 'warns': 0, 'bans': 0, 'kicks': 0, 'violations': 0, 'messages': 0, 'games': 0}
    
    def update_game_stats(self, chat_id, user_id, game_type, won=False, earned=0):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO game_stats 
                (user_id, chat_id, game_type, games_played, games_won, total_earned, last_played)
                VALUES (?, ?, ?, 
                    COALESCE((SELECT games_played + 1 FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?), 1),
                    COALESCE((SELECT games_won + ? FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?), ?),
                    COALESCE((SELECT total_earned + ? FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?), ?),
                    CURRENT_TIMESTAMP)
            ''', (user_id, chat_id, game_type, user_id, chat_id, game_type, 
                  int(won), user_id, chat_id, game_type, int(won),
                  earned, user_id, chat_id, game_type, earned))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики игр: {e}")

    def add_marriage(self, user1_id, user2_id, user1_name, user2_name, chat_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO user_marriage (user1_id, user2_id, user1_name, user2_name, chat_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user1_id, user2_id, user1_name, user2_name, chat_id))
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Ошибка добавления брака: {e}")
            return None
    
    def get_marriage(self, user_id, chat_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM user_marriage 
                WHERE chat_id = ? AND (user1_id = ? OR user2_id = ?)
            ''', (chat_id, user_id, user_id))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"❌ Ошибка получения брака: {e}")
            return None
    
    def add_divorce(self, user_id, chat_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                DELETE FROM user_marriage 
                WHERE chat_id = ? AND (user1_id = ? OR user2_id = ?)
            ''', (chat_id, user_id, user_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка развода: {e}")
    
    def add_crime_record(self, user_id, chat_id, crime_type, success, amount):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO user_crime (user_id, chat_id, crime_type, success, amount)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, chat_id, crime_type, success, amount))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка записи преступления: {e}")
    
    def get_crime_stats(self, user_id, chat_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_crimes,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_crimes,
                    SUM(amount) as total_earned
                FROM user_crime 
                WHERE user_id = ? AND chat_id = ?
            ''', (user_id, chat_id))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики преступлений: {e}")
            return (0, 0, 0)
    
    def add_business(self, user_id, chat_id, business_type):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO user_business (user_id, chat_id, business_type)
                VALUES (?, ?, ?)
            ''', (user_id, chat_id, business_type))
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Ошибка добавления бизнеса: {e}")
            return None
    
    def get_user_businesses(self, user_id, chat_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM user_business WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения бизнесов: {e}")
            return []

# Инициализация БД
db = UltimateBotDB()

# БАЗА СЛОВ
bad_words = [
    'хуй', 'пизда', 'ебал', 'ебать', 'блядь', 'сука', 'пидор', 'гандон', 'мудак', 'мудила',
]

# ФУНКЦИИ
def is_user_admin(chat_id, user_id):
    try:
        # ТОЛЬКО глобальные админы
        if user_id in GLOBAL_ADMINS:
            return True
            
        # ПРОВЕРЯЕМ РЕАЛЬНЫЕ ПРАВА В ТЕЛЕГРАМ ЧАТЕ
        chat_member = bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['administrator', 'creator']
            
    except Exception as e:
        logger.error(f"❌ Ошибка в is_user_admin: {e}")
        return False

def is_super_admin(user_id):
    return user_id in GLOBAL_ADMINS or db.is_super_admin(user_id)

def hide_bad_word(word):
    if not word or len(word) <= 2:
        return word
    return word[0] + '*' * (len(word) - 2) + word[-1] if len(word) > 2 else word

def super_decode(text):
    if not text:
        return ""
    text = text.lower()
    eng_to_rus = {'a': 'а', 'b': 'б', 'c': 'с', 'd': 'д', 'e': 'е', 'f': 'ф', 'g': 'г', 'h': 'х',
                 'i': 'и', 'j': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п',
                 'q': 'к', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'v': 'в', 'w': 'в', 'x': 'х',
                 'y': 'у', 'z': 'з'}
    result = ""
    for char in text:
        if char in eng_to_rus:
            result += eng_to_rus[char]
        else:
            result += char
    result = re.sub(r'[^а-яё]', '', result)
    return result

def super_moderation(text):
    if not text:
        return False, ""
    
    # Приводим к нижнему регистру
    text_lower = text.lower()
    
    # Проверяем только целые слова (с границами слов)
    for word in bad_words:
        # Ищем целое слово, а не часть слова
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            return True, word
    
    # Дополнительная проверка с декодированием
    clean_text = super_decode(text)
    for word in bad_words:
        if re.search(r'\b' + re.escape(word) + r'\b', clean_text):
            return True, word
    
    return False, ""

def check_cooldown(chat_id, user_id, command_type):
    """Проверка кулдауна для команды"""
    try:
        # Админы игнорируют кулдауны
        if is_user_admin(chat_id, user_id):
            return True, 0
            
        settings = db.get_chat_settings(chat_id) or {}
        
        # Если кулдауны выключены
        if not settings.get('cooldown_enabled', True):
            return True, 0
            
        cooldown_seconds = settings.get(f'cooldown_{command_type}', 0)
        
        if cooldown_seconds <= 0:
            return True, 0
            
        if not cooldown.can_play(user_id, command_type, cooldown_seconds):
            remaining = cooldown.get_remaining_time(user_id, command_type, cooldown_seconds)
            return False, remaining
            
        return True, 0
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки кулдауна: {e}")
        return True, 0

# 🎮 РАСШИРЕННАЯ СИСТЕМА ИГР

# 🎮 РАСШИРЕННАЯ СИСТЕМА ИГР
class AdvancedGameSystem:
    def __init__(self, db):
        self.db = db
        self.active_games = {}
    
    def play_slots(self, user_id, chat_id, bet_amount):
        if not cooldown.can_play(user_id, 'slots', 3):
            return None, f"⏰ Подождите {cooldown.get_remaining_time(user_id, 'slots', 3)} сек."
        
        symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣", "⭐"]
        slots = [random.choice(symbols) for _ in range(3)]
        
        if slots[0] == slots[1] == slots[2]:
            if slots[0] == "7️⃣":
                win_amount = bet_amount * 10
                result = "🎊 ДЖЕКПОТ!"
            elif slots[0] == "💎":
                win_amount = bet_amount * 8
                result = "💰 БОЛЬШОЙ ВЫИГРЫШ!"
            elif slots[0] == "⭐":
                win_amount = bet_amount * 6
                result = "🌟 ВЫИГРЫШ!"
            else:
                win_amount = bet_amount * 4
                result = "🎉 ВЫИГРАЛ!"
        elif slots[0] == slots[1] or slots[1] == slots[2] or slots[0] == slots[2]:
            win_amount = bet_amount * 2
            result = "🎯 НЕПЛОХО!"
        else:
            win_amount = 0
            result = "😢 ПРОИГРЫШ"
        
        if win_amount > 0:
            self.db.add_user_balance(chat_id, user_id, win_amount)
            self.db.update_game_stats(chat_id, user_id, 'slots', True, win_amount)
        else:
            self.db.add_user_balance(chat_id, user_id, -bet_amount)
            self.db.update_game_stats(chat_id, user_id, 'slots', False, 0)
        
        return win_amount, result, " | ".join(slots)
    
    def play_coinflip(self, user_id, chat_id, bet_amount, choice):
        if not cooldown.can_play(user_id, 'coinflip', 5):
            return None, f"⏰ Подождите {cooldown.get_remaining_time(user_id, 'coinflip', 5)} сек."
        
        result = random.choice(['орёл', 'решка'])
        win = (choice.lower() == result)
        
        if win:
            win_amount = bet_amount * 1.95
            self.db.add_user_balance(chat_id, user_id, int(win_amount))
            self.db.update_game_stats(chat_id, user_id, 'coinflip', True, int(win_amount))
            return int(win_amount), f"🎯 ВЫ ВЫИГРАЛИ! Выпал: {result}"
        else:
            self.db.update_game_stats(chat_id, user_id, 'coinflip', False, 0)
            return 0, f"😢 ВЫ ПРОИГРАЛИ! Выпал: {result}"
    
    def play_dice_battle(self, user_id, chat_id, bet_amount):
        if not cooldown.can_play(user_id, 'dice_battle', 10):
            return None, f"⏰ Подождите {cooldown.get_remaining_time(user_id, 'dice_battle', 10)} сек."
        
        player1_roll = random.randint(1, 6)
        player2_roll = random.randint(1, 6)
        
        if player1_roll > player2_roll:
            win_amount = bet_amount * 1.8
            self.db.add_user_balance(chat_id, user_id, int(win_amount))
            result = f"🎯 ВЫ ВЫИГРАЛИ! {player1_roll} vs {player2_roll}"
            return int(win_amount), result
        elif player1_roll < player2_roll:
            result = f"😢 ВЫ ПРОИГРАЛИ! {player1_roll} vs {player2_roll}"
            return 0, result
        else:
            self.db.add_user_balance(chat_id, user_id, bet_amount)
            result = f"🤝 НИЧЬЯ! {player1_roll} vs {player2_roll}"
            return bet_amount, result
game_system = AdvancedGameSystem(db)

# 📊 СИСТЕМА АВТО-ОТЧЕТОВ
class DailyReportSystem:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.is_running = False
    
    def start_daily_reports(self):
        if self.is_running:
            return
        
        self.is_running = True
        report_thread = threading.Thread(target=self._report_scheduler, daemon=True)
        report_thread.start()
        logger.info("📊 Система ежедневных отчетов запущена")
    
    def _report_scheduler(self):
        while self.is_running:
            try:
                now = datetime.now()
                target_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
                
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"📊 Следующий отчет через {wait_seconds} секунд")
                
                time.sleep(wait_seconds)
                self.send_daily_reports()
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике отчетов: {e}")
                time.sleep(300)
    
    def send_daily_reports(self):
        try:
            logger.info("📊 Начинаем отправку ежедневных отчетов...")
            
            cursor = db.conn.cursor()
            cursor.execute('SELECT chat_id, title FROM chats')
            chats = cursor.fetchall()
            
            for chat_id, chat_title in chats:
                try:
                    stats = db.get_today_stats(chat_id)
                    
                    report = f"""
📊 ЕЖЕДНЕВНЫЙ ОТЧЕТ | {datetime.now().strftime('%d.%m.%Y')}
💬 Чат: {chat_title}

🛡️ МОДЕРАЦИЯ:
├ 🔇 Мутов: {stats['mutes']}
├ ⚠️ Предупреждений: {stats['warns']}
├ 🚫 Банов: {stats['bans']}
├ 👢 Киков: {stats['kicks']}
└ 🔞 Нарушений: {stats['violations']}

💬 АКТИВНОСТЬ:
├ 📝 Сообщений: {stats['messages']}
└ 🎮 Игр сыграно: {stats['games']}
"""
                    
                    for admin_id in GLOBAL_ADMINS:
                        try:
                            self.bot.send_message(admin_id, report)
                        except Exception as e:
                            logger.error(f"❌ Не удалось отправить отчет админу {admin_id}: {e}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки чата {chat_id}: {e}")
            
            logger.info("📊 Ежедневные отчеты успешно отправлены")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при отправке отчетов: {e}")

report_system = DailyReportSystem(bot, db)

# 🎯 КОМАНДЫ АДМИНИСТРАТОРА
@bot.message_handler(commands=['promote'])
def promote_admin(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут добавлять других админов!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if is_user_admin(chat_id, target_user.id):
            bot.reply_to(message, "❌ Этот пользователь уже является админом!")
            return
        
        db.add_chat_admin(chat_id, target_user.id, target_user.username, 
                         target_user.first_name, user_id, 'moderator')
        
        bot.reply_to(message, f"✅ {target_user.first_name} теперь администратор чата!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /promote: {e}")

@bot.message_handler(commands=['demote'])
def demote_admin(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут снимать других админов!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение админа!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if not is_user_admin(chat_id, target_user.id):
            bot.reply_to(message, "❌ Этот пользователь не является админом!")
            return
        
        if target_user.id in GLOBAL_ADMINS:
            bot.reply_to(message, "❌ Нельзя снять глобального админа!")
            return
        
        cursor = db.conn.cursor()
        cursor.execute('DELETE FROM chat_admins WHERE chat_id = ? AND user_id = ?', 
                     (chat_id, target_user.id))
        db.conn.commit()
        
        bot.reply_to(message, f"✅ {target_user.first_name} больше не администратор чата!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /demote: {e}")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут удалять других админов!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение админа которого нужно удалить!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if target_user.id in GLOBAL_ADMINS:
            bot.reply_to(message, "❌ Нельзя удалить глобального админа!")
            return
        
        cursor = db.conn.cursor()
        cursor.execute('DELETE FROM chat_admins WHERE chat_id = ? AND user_id = ?', 
                     (chat_id, target_user.id))
        db.conn.commit()
        
        bot.reply_to(message, f"✅ {target_user.first_name} удален из админов бота!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /removeadmin: {e}")

@bot.message_handler(commands=['listbotadmins'])
def list_bot_admins(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут просматривать этот список!")
            return
        
        cursor = db.conn.cursor()
        cursor.execute('SELECT user_id, username, first_name FROM chat_admins WHERE chat_id = ?', (chat_id,))
        admins = cursor.fetchall()
        
        if not admins:
            bot.reply_to(message, "📋 В базе данных нет админов бота")
            return
        
        response = "📋 АДМИНЫ БОТА В БАЗЕ ДАННЫХ:\n\n"
        for admin in admins:
            user_id, username, first_name = admin
            username_display = f"(@{username})" if username else ""
            response += f"• {first_name} {username_display} (ID: {user_id})\n"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /listbotadmins: {e}")

@bot.message_handler(commands=['admins'])
def list_admins(message):
    try:
        chat_id = message.chat.id
        
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, permissions 
            FROM chat_admins 
            WHERE chat_id = ? OR permissions = 'super_admin'
        ''', (chat_id,))
        
        admins = cursor.fetchall()
        
        response = "🛡️ СПИСОК АДМИНИСТРАТОРОВ:\n\n"
        
        response += "🌐 ГЛОБАЛЬНЫЕ АДМИНЫ:\n"
        for admin_id in GLOBAL_ADMINS:
            response += f"• ID: {admin_id} (Системный)\n"
        
        if admins:
            response += "\n💬 АДМИНЫ ЧАТА:\n"
            for admin in admins:
                user_id, username, first_name, permissions = admin
                username_display = f"(@{username})" if username else ""
                response += f"• {first_name} {username_display} - {permissions}\n"
        else:
            response += "\n💬 Админы чата не назначены\n"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /admins: {e}")

# 💍 СИСТЕМА БРАКА
@bot.message_handler(commands=['marry'])
def marry_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if target_user.id == user_id:
            bot.reply_to(message, "❌ Нельзя жениться на самом себе!")
            return
        
        existing_marriage = db.get_marriage(user_id, chat_id)
        if existing_marriage:
            bot.reply_to(message, "❌ Вы уже состоите в браке!")
            return
        
        existing_target_marriage = db.get_marriage(target_user.id, chat_id)
        if existing_target_marriage:
            bot.reply_to(message, f"❌ {target_user.first_name} уже состоит в браке!")
            return
        
        marriage_cost = 1000
        balance = db.get_user_balance(chat_id, user_id)
        
        if balance < marriage_cost:
            bot.reply_to(message, f"❌ Недостаточно денег для брака! Нужно {marriage_cost} монет")
            return
        
        proposal_msg = bot.reply_to(message,
            f"💍 ПРЕДЛОЖЕНИЕ БРАКА!\n\n"
            f"👤 {message.from_user.first_name} предлагает брак {target_user.first_name}\n"
            f"💰 Стоимость: {marriage_cost} монет\n\n"
            f"✅ {target_user.first_name}, принимаешь предложение?\n"
            f"Напиши /accept или /reject"
        )
        
        if chat_id not in game_system.active_games:
            game_system.active_games[chat_id] = {}
        
        game_system.active_games[chat_id]['marriage_proposal'] = {
            'from_user_id': user_id,
            'from_user_name': message.from_user.first_name,
            'to_user_id': target_user.id,
            'to_user_name': target_user.first_name,
            'message_id': proposal_msg.message_id,
            'cost': marriage_cost
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /marry: {e}")

@bot.message_handler(commands=['accept'])
def accept_marriage(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if chat_id not in game_system.active_games or 'marriage_proposal' not in game_system.active_games[chat_id]:
            bot.reply_to(message, "❌ Нет активных предложений брака!")
            return
        
        proposal = game_system.active_games[chat_id]['marriage_proposal']
        
        if proposal['to_user_id'] != user_id:
            bot.reply_to(message, "❌ Это предложение не для вас!")
            return
        
        balance = db.get_user_balance(chat_id, proposal['from_user_id'])
        if balance < proposal['cost']:
            bot.reply_to(message, "❌ У предложившего недостаточно денег!")
            return
        
        db.add_user_balance(chat_id, proposal['from_user_id'], -proposal['cost'])
        db.add_marriage(proposal['from_user_id'], user_id, 
                       proposal['from_user_name'], message.from_user.first_name, chat_id)
        
        bot.reply_to(message,
            f"🎉 ПОЗДРАВЛЯЕМ С БРАКОМ!\n\n"
            f"💑 {proposal['from_user_name']} ❤️ {message.from_user.first_name}\n"
            f"💰 Свадьба стоила: {proposal['cost']} монет\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        del game_system.active_games[chat_id]['marriage_proposal']
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /accept: {e}")

@bot.message_handler(commands=['divorce'])
def divorce_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        marriage = db.get_marriage(user_id, chat_id)
        if not marriage:
            bot.reply_to(message, "❌ Вы не состоите в браке!")
            return
        
        partner_id = marriage[1] if marriage[1] != user_id else marriage[2]
        partner_name = marriage[3] if marriage[1] != user_id else marriage[4]
        
        divorce_cost = 500
        balance = db.get_user_balance(chat_id, user_id)
        
        if balance < divorce_cost:
            bot.reply_to(message, f"❌ Недостаточно денег для развода! Нужно {divorce_cost} монет")
            return
        
        db.add_user_balance(chat_id, user_id, -divorce_cost)
        db.add_divorce(user_id, chat_id)
        
        bot.reply_to(message,
            f"💔 РАЗВОД\n\n"
            f"👤 {message.from_user.first_name} развелся(ась) с {partner_name}\n"
            f"💰 Стоимость развода: {divorce_cost} монет"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /divorce: {e}")

# 🕵️ СИСТЕМА ПРЕСТУПЛЕНИЙ
@bot.message_handler(commands=['crime'])
def crime_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # ПРОВЕРКА КУЛДАУНА
        can_play, remaining = check_cooldown(chat_id, user_id, 'crime')
        if not can_play:
            bot.reply_to(message, f"⏰ Подождите {remaining} сек. перед следующим преступлением!")
            return
        
        crimes = [
            {"name": "🏪 Ограбление магазина", "success_rate": 40, "min_reward": 100, "max_reward": 500},
            {"name": "🏦 Взлом банка", "success_rate": 20, "min_reward": 500, "max_reward": 2000},
            {"name": "💎 Кража драгоценностей", "success_rate": 35, "min_reward": 200, "max_reward": 800},
            {"name": "🚗 Угон автомобиля", "success_rate": 50, "min_reward": 150, "max_reward": 600},
            {"name": "💻 Хакерская атака", "success_rate": 30, "min_reward": 300, "max_reward": 1200}
        ]
        
        crime = random.choice(crimes)
        success = random.randint(1, 100) <= crime['success_rate']
        
        if success:
            reward = random.randint(crime['min_reward'], crime['max_reward'])
            db.add_user_balance(chat_id, user_id, reward)
            db.add_crime_record(user_id, chat_id, crime['name'], True, reward)
            
            response = (
                f"🕵️ ПРЕСТУПЛЕНИЕ УСПЕШНО!\n\n"
                f"🏴‍☠️ Преступление: {crime['name']}\n"
                f"💰 Добыча: {reward} монет\n"
                f"💎 Новый баланс: {db.get_user_balance(chat_id, user_id)}"
            )
        else:
            fine = random.randint(50, 200)
            current_balance = db.get_user_balance(chat_id, user_id)
            fine = min(fine, current_balance)
            
            db.add_user_balance(chat_id, user_id, -fine)
            db.add_crime_record(user_id, chat_id, crime['name'], False, -fine)
            
            response = (
                f"🚨 ПРЕСТУПЛЕНИЕ ПРОВАЛИЛОСЬ!\n\n"
                f"🏴‍☠️ Преступление: {crime['name']}\n"
                f"💸 Штраф: {fine} монет\n"
                f"💎 Новый баланс: {db.get_user_balance(chat_id, user_id)}"
            )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /crime: {e}")

# 💼 СИСТЕМА БИЗНЕСА
@bot.message_handler(commands=['business'])
def business_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        businesses = [
            {"name": "🏪 Магазин", "cost": 5000, "income": 200},
            {"name": "🏢 Офис", "cost": 10000, "income": 500},
            {"name": "🏭 Фабрика", "cost": 25000, "income": 1200},
            {"name": "💎 Ювелирный", "cost": 50000, "income": 2500},
            {"name": "🚀 IT-компания", "cost": 100000, "income": 5000}
        ]
        
        user_businesses = db.get_user_businesses(user_id, chat_id)
        
        response = "💼 СИСТЕМА БИЗНЕСА\n\n"
        
        if user_businesses:
            response += "🏢 ВАШИ БИЗНЕСЫ:\n"
            total_income = 0
            for biz in user_businesses:
                biz_id, user_id, chat_id, biz_type, level, income, last_collected = biz
                response += f"• {biz_type} (Ур. {level}) - {income} монет/день\n"
                total_income += income
            response += f"\n💰 Общий доход: {total_income} монет/день\n"
        else:
            response += "❌ У вас нет бизнесов\n"
        
        response += "\n🛒 ДОСТУПНЫЕ БИЗНЕСЫ:\n"
        for biz in businesses:
            response += f"• {biz['name']} - {biz['cost']} монет ({biz['income']}/день)\n"
        
        response += "\n💡 Используйте /buybusiness [название] для покупки"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /business: {e}")

@bot.message_handler(commands=['buybusiness'])
def buy_business_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        args = message.text.split()[1:]
        if not args:
            bot.reply_to(message, "❌ Используйте: /buybusiness [название]\nПример: /buybusiness Магазин")
            return
        
        business_name = ' '.join(args)
        
        businesses = {
            "магазин": {"name": "🏪 Магазин", "cost": 5000, "income": 200},
            "офис": {"name": "🏢 Офис", "cost": 10000, "income": 500},
            "фабрика": {"name": "🏭 Фабрика", "cost": 25000, "income": 1200},
            "ювелирный": {"name": "💎 Ювелирный", "cost": 50000, "income": 2500},
            "it-компания": {"name": "🚀 IT-компания", "cost": 100000, "income": 5000}
        }
        
        biz_key = business_name.lower()
        if biz_key not in businesses:
            bot.reply_to(message, "❌ Бизнес не найден! Используйте /business для списка")
            return
        
        biz = businesses[biz_key]
        balance = db.get_user_balance(chat_id, user_id)
        
        if balance < biz['cost']:
            bot.reply_to(message, f"❌ Недостаточно денег! Нужно {biz['cost']} монет")
            return
        
        db.add_user_balance(chat_id, user_id, -biz['cost'])
        db.add_business(user_id, chat_id, biz['name'])
        
        bot.reply_to(message,
            f"✅ БИЗНЕС КУПЛЕН!\n\n"
            f"🏢 {biz['name']}\n"
            f"💸 Стоимость: {biz['cost']} монет\n"
            f"💰 Доход: {biz['income']} монет/день\n"
            f"💎 Новый баланс: {db.get_user_balance(chat_id, user_id)}"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /buybusiness: {e}")

# 🎰 ИГРОВЫЕ КОМАНДЫ
@bot.message_handler(commands=['slots'])
def slots_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        settings = db.get_chat_settings(chat_id) or {}
        if not settings.get('games_enabled', True):
            bot.reply_to(message, "❌ Игры отключены в этом чате!")
            return
        
        args = message.text.split()[1:]
        if not args:
            bot.reply_to(message, "❌ Используйте: /slots [ставка]")
            return
        
        try:
            bet_amount = int(args[0])
            if bet_amount < 10:
                bot.reply_to(message, "❌ Минимальная ставка: 10 монет")
                return
        except ValueError:
            bot.reply_to(message, "❌ Введите корректную сумму!")
            return
        
        balance = db.get_user_balance(chat_id, user_id)
        if balance < bet_amount:
            bot.reply_to(message, f"❌ Недостаточно монет! Баланс: {balance}")
            return
        
        db.add_user_balance(chat_id, user_id, -bet_amount)
        
        win_amount, result, slots_display = game_system.play_slots(user_id, chat_id, bet_amount)
        
        if win_amount is None:
            db.add_user_balance(chat_id, user_id, bet_amount)
            bot.reply_to(message, result)
            return
        
        response = (
            f"🎰 ИГРОВЫЕ АВТОМАТЫ\n\n"
            f"👤 Игрок: {message.from_user.first_name}\n"
            f"💰 Ставка: {bet_amount} монет\n\n"
            f"⚡ {slots_display} ⚡\n\n"
            f"{result}\n"
        )
        
        if win_amount > 0:
            response += f"💵 Выигрыш: {win_amount} монет\n"
        
        response += f"💎 Баланс: {db.get_user_balance(chat_id, user_id)}"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /slots: {e}")

@bot.message_handler(commands=['coinflip'])
def coinflip_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        args = message.text.split()[1:]
        if len(args) < 2:
            bot.reply_to(message, "❌ Используйте: /coinflip [орёл/решка] [ставка]")
            return
        
        choice = args[0].lower()
        if choice not in ['орёл', 'орел', 'решка']:
            bot.reply_to(message, "❌ Выберите: орёл или решка")
            return
        
        try:
            bet_amount = int(args[1])
            if bet_amount < 10:
                bot.reply_to(message, "❌ Минимальная ставка: 10 монет")
                return
        except ValueError:
            bot.reply_to(message, "❌ Введите корректную сумму!")
            return
        
        balance = db.get_user_balance(chat_id, user_id)
        if balance < bet_amount:
            bot.reply_to(message, f"❌ Недостаточно монет! Баланс: {balance}")
            return
        
        db.add_user_balance(chat_id, user_id, -bet_amount)
        
        win_amount, result = game_system.play_coinflip(user_id, chat_id, bet_amount, choice)
        
        if win_amount is None:
            db.add_user_balance(chat_id, user_id, bet_amount)
            bot.reply_to(message, result)
            return
        
        response = (
            f"🪙 МОНЕТКА\n\n"
            f"👤 Игрок: {message.from_user.first_name}\n"
            f"💰 Ставка: {bet_amount} монет\n"
            f"🎯 Выбор: {choice}\n\n"
            f"{result}\n\n"
        )
        
        if win_amount > 0:
            response += f"💵 Выигрыш: {win_amount} монет\n"
        response += f"💎 Баланс: {db.get_user_balance(chat_id, user_id)}"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /coinflip: {e}")

@bot.message_handler(commands=['dicebattle'])
def dice_battle_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        args = message.text.split()[1:]
        if not args:
            bot.reply_to(message, "❌ Используйте: /dicebattle [ставка]")
            return
        
        try:
            bet_amount = int(args[0])
            if bet_amount < 10:
                bot.reply_to(message, "❌ Минимальная ставка: 10 монет")
                return
        except ValueError:
            bot.reply_to(message, "❌ Введите корректную сумму!")
            return
        
        balance = db.get_user_balance(chat_id, user_id)
        if balance < bet_amount:
            bot.reply_to(message, f"❌ Недостаточно монет! Баланс: {balance}")
            return
        
        db.add_user_balance(chat_id, user_id, -bet_amount)
        
        win_amount, result = game_system.play_dice_battle(user_id, chat_id, bet_amount)
        
        if win_amount is None:
            db.add_user_balance(chat_id, user_id, bet_amount)
            bot.reply_to(message, result)
            return
        
        response = (
            f"🎲 БИТВА КУБИКОВ\n\n"
            f"👤 Игрок: {message.from_user.first_name}\n"
            f"🤖 Противник: Бот\n"
            f"💰 Ставка: {bet_amount} монет\n\n"
            f"{result}\n\n"
        )
        
        if win_amount > 0:
            response += f"💵 Выигрыш: {win_amount} монет\n"
        response += f"💎 Баланс: {db.get_user_balance(chat_id, user_id)}"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /dicebattle: {e}")

# 🎲 ТЕЛЕГРАМ ИГРЫ - ПОЛНОСТЬЮ ИСПРАВЛЕННАЯ ВЕРСИЯ
def handle_telegram_game(message, game_type, emoji):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        settings = db.get_chat_settings(chat_id) or {}
        if not settings.get('games_enabled', True):
            bot.reply_to(message, "❌ Игры отключены в этом чате!")
            return
        
        # ПРОВЕРКА КУЛДАУНА
        can_play, remaining = check_cooldown(chat_id, user_id, 'games')
        if not can_play:
            bot.reply_to(message, f"⏰ Подождите {remaining} сек. перед следующей игрой!")
            return
        
        # Отправляем игру
        msg = None
        if game_type == 'dice':
            msg = bot.send_dice(chat_id, emoji='🎲')
        elif game_type == 'basketball':
            msg = bot.send_dice(chat_id, emoji='🏀')
        elif game_type == 'bowling':
            msg = bot.send_dice(chat_id, emoji='🎳')
        elif game_type == 'football':
            msg = bot.send_dice(chat_id, emoji='⚽')
        elif game_type == 'darts':
            msg = bot.send_dice(chat_id, emoji='🎯')
        
        if not msg:
            return
        
        # Ждем обновление с результатом (анимация)
        time.sleep(4)
        
        # Получаем значение кубика (1-6 для 🎲, 🎳, 🎯; 1-5 для 🏀, ⚽)
        game_value = msg.dice.value
        
        # ПРАВИЛЬНЫЕ ДИАПАЗОНЫ ДЛЯ КАЖДОЙ ИГРЫ:
        # 🎲 - обычный кубик: 1-6
        # 🎳 - боулинг: 1-6  
        # 🎯 - дартс: 1-6
        # 🏀 - баскетбол: 1-5
        # ⚽ - футбол: 1-5
        
        logger.info(f"🎮 Игра {game_type}, выпало: {game_value}")
        
        # СИСТЕМА НАГРАД
        base_multipliers = {
            'dice': 15,      # 🎲
            'basketball': 20, # 🏀  
            'bowling': 18,    # 🎳
            'football': 16,   # ⚽
            'darts': 25       # 🎯
        }
        
        base_reward = base_multipliers.get(game_type, 15) * game_value
        
        # БОНУСЫ ЗА ХОРОШИЕ РЕЗУЛЬТАТЫ
        if game_value >= 5:
            win_amount = int(base_reward * 2.0)  # x2 за 5-6
            result_emoji = "🎉"
        elif game_value >= 3:
            win_amount = int(base_reward * 1.5)  # x1.5 за 3-4
            result_emoji = "👍"
        else:
            win_amount = base_reward  # Базовая награда за 1-2
            result_emoji = "😊"
        
        # СУПЕР-ДЖЕКПОТ ЗА МАКСИМАЛЬНОЕ ЗНАЧЕНИЕ
        max_values = {
            'dice': 6, 
            'basketball': 5, 
            'bowling': 6, 
            'football': 5, 
            'darts': 6
        }
        
        if game_value == max_values.get(game_type, 6):
            win_amount = int(win_amount * 3)  # x3 за максимальное значение
            result_emoji = "🎊"
        
        # НАГРАЖДАЕМ ИГРОКА
        db.add_user_balance(chat_id, user_id, win_amount)
        db.update_game_stats(chat_id, user_id, game_type, True, win_amount)
        
        # НАЗВАНИЯ ИГР
        game_names = {
            'dice': 'кубик 🎲',
            'basketball': 'баскетбол 🏀', 
            'bowling': 'боулинг 🎳',
            'football': 'футбол ⚽',
            'darts': 'дартс 🎯'
        }
        
        # ОТПРАВЛЯЕМ РЕЗУЛЬТАТ
        response = (
            f"{emoji} {message.from_user.first_name} выбросил {game_value} в {game_names.get(game_type, 'игре')}!\n"
            f"{result_emoji} Выигрыш: {win_amount} монет\n"
            f"💎 Баланс: {db.get_user_balance(chat_id, user_id)}"
        )
        
        bot.send_message(
            chat_id, 
            response,
            reply_to_message_id=msg.message_id
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в игре {game_type}: {e}")
        bot.reply_to(message, f"❌ Ошибка в игре: {e}")

# КОМАНДЫ ИГР - ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ
@bot.message_handler(commands=['dice'])
def dice_game(message):
    handle_telegram_game(message, 'dice', '🎲')

@bot.message_handler(commands=['basketball'])  
def basketball_game(message):
    handle_telegram_game(message, 'basketball', '🏀')

@bot.message_handler(commands=['bowling'])
def bowling_game(message):
    handle_telegram_game(message, 'bowling', '🎳')

@bot.message_handler(commands=['football'])
def football_game(message):
    handle_telegram_game(message, 'football', '⚽')

@bot.message_handler(commands=['darts'])
def darts_game(message):
    handle_telegram_game(message, 'darts', '🎯')


# 💰 ЭКОНОМИКА
@bot.message_handler(commands=['balance'])
def balance_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        balance = db.get_user_balance(chat_id, user_id)
        response = f"💰 Ваш баланс: {balance} монет"
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /balance: {e}")

@bot.message_handler(commands=['work'])
def work_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # ПРОВЕРКА КУЛДАУНА
        can_play, remaining = check_cooldown(chat_id, user_id, 'work')
        if not can_play:
            bot.reply_to(message, f"⏰ Вы уже работали! Подождите {remaining} сек.")
            return
        
        jobs = [
            {"name": "👨‍💼 Офисный работник", "salary": random.randint(50, 150)},
            {"name": "👷 Строитель", "salary": random.randint(80, 200)},
            {"name": "👨‍🍳 Повар", "salary": random.randint(60, 180)},
            {"name": "🚕 Таксист", "salary": random.randint(70, 190)}
        ]
        
        job = random.choice(jobs)
        salary = job["salary"]
        
        db.add_user_balance(chat_id, user_id, salary)
        
        response = (
            f"💼 РАБОТА\n\n"
            f"👤 Работник: {message.from_user.first_name}\n"
            f"🏢 Профессия: {job['name']}\n"
            f"💰 Зарплата: {salary} монет\n"
            f"💎 Новый баланс: {db.get_user_balance(chat_id, user_id)}"
        )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /work: {e}")

@bot.message_handler(commands=['daily'])
def daily_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # ПРОВЕРКА КУЛДАУНА (24 часа)
        can_play, remaining = check_cooldown(chat_id, user_id, 'daily')
        if not can_play:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            bot.reply_to(message, f"⏰ Вы уже получали daily! Подождите {hours}ч {minutes}м")
            return
        
        daily_amount = random.randint(50, 200)
        db.add_user_balance(chat_id, user_id, daily_amount)
        
        response = (
            f"🎁 ЕЖЕДНЕВНЫЙ БОНУС\n\n"
            f"💰 Получено: {daily_amount} монет\n"
            f"💎 Новый баланс: {db.get_user_balance(chat_id, user_id)}"
        )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /daily: {e}")

@bot.message_handler(commands=['transfer'])
def transfer_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        args = message.text.split()[1:]
        if len(args) < 2:
            bot.reply_to(message, "❌ Используйте: /transfer [@username] [сумма]")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if target_user.id == user_id:
            bot.reply_to(message, "❌ Нельзя переводить деньги самому себе!")
            return
        
        try:
            amount = int(args[1])
            if amount <= 0:
                bot.reply_to(message, "❌ Сумма должна быть положительной!")
                return
        except ValueError:
            bot.reply_to(message, "❌ Введите корректную сумму!")
            return
        
        balance = db.get_user_balance(chat_id, user_id)
        if balance < amount:
            bot.reply_to(message, f"❌ Недостаточно монет! Баланс: {balance}")
            return
        
        db.add_user_balance(chat_id, user_id, -amount)
        db.add_user_balance(chat_id, target_user.id, amount)
        
        response = (
            f"✅ ПЕРЕВОД ВЫПОЛНЕН\n\n"
            f"👤 От: {message.from_user.first_name}\n"
            f"🎯 Кому: {target_user.first_name}\n"
            f"💰 Сумма: {amount} монет\n"
            f"💎 Ваш баланс: {db.get_user_balance(chat_id, user_id)}"
        )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /transfer: {e}")

@bot.message_handler(commands=['top'])
def top_command(message):
    try:
        chat_id = message.chat.id
        top_users = db.get_top_users(chat_id, 10)
        
        response = "🏆 ТОП ИГРОКОВ\n\n"
        for i, (user_id, first_name, username, msg_count, balance, level) in enumerate(top_users, 1):
            username_display = f"(@{username})" if username else ""
            response += f"{i}. {first_name} {username_display}\n"
            response += f"   💰 {balance} монет | 💬 {msg_count} сообщ.\n\n"
        
        bot.send_message(chat_id, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /top: {e}")

# 📊 КОМАНДЫ СТАТИСТИКИ
@bot.message_handler(commands=['mystatus'])
def my_status(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        marriage = db.get_marriage(user_id, chat_id)
        balance = db.get_user_balance(chat_id, user_id)
        crime_stats = db.get_crime_stats(user_id, chat_id)
        
        response = f"👤 СТАТУС: {message.from_user.first_name}\n\n"
        response += f"💰 Баланс: {balance} монет\n"
        
        if marriage:
            partner_name = marriage[3] if marriage[1] != user_id else marriage[4]
            married_since = datetime.strptime(marriage[6], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            response += f"💍 В браке с: {partner_name}\n"
            response += f"📅 Дата свадьбы: {married_since}\n"
        else:
            response += "💍 Семейное положение: Не женат/Не замужем\n"
        
        if crime_stats[0] > 0:
            response += f"🕵️ Преступления: {crime_stats[1]}/{crime_stats[0]} успешных\n"
            response += f"💰 Заработано преступлениями: {crime_stats[2]} монет\n"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /mystatus: {e}")

@bot.message_handler(commands=['stats'])
def stats_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут просматривать статистику!")
            return
        
        stats = db.get_today_stats(chat_id)
        
        response = f"""
📊 СТАТИСТИКА ЗА СЕГОДНЯ ({datetime.now().strftime('%d.%m.%Y')})

🛡️ МОДЕРАЦИЯ:
├ 🔇 Мутов: {stats['mutes']}
├ ⚠️ Предупреждений: {stats['warns']}
├ 🚫 Банов: {stats['bans']}
├ 👢 Киков: {stats['kicks']}
└ 🔞 Нарушений: {stats['violations']}

💬 АКТИВНОСТЬ:
├ 📝 Сообщений: {stats['messages']}
└ 🎮 Игр сыграно: {stats['games']}
"""
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /stats: {e}")

# 👮 МОДЕРАЦИЯ
@bot.message_handler(commands=['warn'])
def warn_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут выдавать предупреждения!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if is_user_admin(chat_id, target_user.id):
            bot.reply_to(message, "❌ Нельзя выдавать варны другим админам!")
            return
        
        reason = ' '.join(message.text.split()[1:]) or 'Нарушение правил'
        
        db.add_warn(chat_id, target_user.id, target_user.username, target_user.first_name, reason, user_id)
        
        db.add_moderation_log(
            chat_id, target_user.id, target_user.username, target_user.first_name,
            'warn', reason, None, user_id, message.from_user.first_name
        )
        
        warns_count = db.get_user_warns(chat_id, target_user.id)
        max_warns = 3
        
        response = f"⚠️ {target_user.first_name} получил предупреждение!\n📝 Причина: {reason}\n🎯 Всего варнов: {warns_count}/{max_warns}"
        
        if warns_count >= max_warns:
            try:
                settings = db.get_chat_settings(chat_id)
                mute_duration = settings.get('mute_duration', 15)
                
                until_date = int(time.time()) + mute_duration * 60
                bot.restrict_chat_member(
                    chat_id, 
                    target_user.id,
                    until_date=until_date,
                    permissions=telebot.types.ChatPermissions(
                        can_send_messages=False,
                        can_send_media_messages=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False
                    )
                )
                response += f"\n🔇 Автоматический мут на {mute_duration} минут!"
                
                db.remove_all_warns(chat_id, target_user.id)
                
            except Exception as e:
                logger.error(f"Ошибка авто-мута: {e}")
                response += "\n❌ Ошибка при муте!"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /warn: {e}")

@bot.message_handler(commands=['mute'])
def mute_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут мутить пользователей!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if is_user_admin(chat_id, target_user.id):
            bot.reply_to(message, "❌ Нельзя мутить других админов!")
            return
        
        args = message.text.split()[1:]
        duration = 15
        
        if args and args[0].isdigit():
            duration = int(args[0])
        
        reason = ' '.join(args[1:]) if len(args) > 1 else 'Нарушение правил'
        
        try:
            until_date = int(time.time()) + duration * 60
            bot.restrict_chat_member(
                chat_id, 
                target_user.id,
                until_date=until_date,
                permissions=telebot.types.ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
            )
            
            db.add_moderation_log(
                chat_id, target_user.id, target_user.username, target_user.first_name,
                'mute', reason, duration, user_id, message.from_user.first_name
            )
            
            bot.reply_to(message, f"🔇 {target_user.first_name} замьючен на {duration} минут!\n📝 Причина: {reason}")
        except Exception as e:
            logger.error(f"Ошибка мута: {e}")
            bot.reply_to(message, "❌ Не удалось замутить пользователя!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /mute: {e}")

# 🔊 КОМАНДА /UNMUTE
@bot.message_handler(commands=['unmute'])
def unmute_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"🔊 Команда /unmute от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут снимать мут!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        try:
            bot.restrict_chat_member(
                chat_id, 
                target_user.id,
                permissions=telebot.types.ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            
            # Логируем действие
            db.add_moderation_log(
                chat_id, target_user.id, target_user.username, target_user.first_name,
                'unmute', 'Снятие мута', None, user_id, message.from_user.first_name
            )
            
            bot.reply_to(message, f"🔊 {target_user.first_name} размучен!")
        except Exception as e:
            logger.error(f"Ошибка размута: {e}")
            bot.reply_to(message, "❌ Не удалось размутить пользователя!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /unmute: {e}")
        

# 🚫 КОМАНДА /BAN
@bot.message_handler(commands=['ban'])
def ban_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"🚫 Команда /ban от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут банить пользователей!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if is_user_admin(chat_id, target_user.id):
            bot.reply_to(message, "❌ Нельзя банить других админов!")
            return
        
        reason = ' '.join(message.text.split()[1:]) or 'Нарушение правил'
        
        try:
            bot.ban_chat_member(chat_id, target_user.id)
            
            # Логируем действие
            db.add_moderation_log(
                chat_id, target_user.id, target_user.username, target_user.first_name,
                'ban', reason, None, user_id, message.from_user.first_name
            )
            
            bot.reply_to(message, f"🚫 {target_user.first_name} забанен!\n📝 Причина: {reason}")
        except Exception as e:
            logger.error(f"Ошибка бана: {e}")
            bot.reply_to(message, "❌ Не удалось забанить пользователя!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /ban: {e}")

# ✅ КОМАНДА /UNBAN
@bot.message_handler(commands=['unban'])
def unban_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"✅ Команда /unban от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут разбанивать пользователей!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        try:
            bot.unban_chat_member(chat_id, target_user.id)
            
            # Логируем действие
            db.add_moderation_log(
                chat_id, target_user.id, target_user.username, target_user.first_name,
                'unban', 'Разбан', None, user_id, message.from_user.first_name
            )
            
            bot.reply_to(message, f"✅ {target_user.first_name} разбанен!")
        except Exception as e:
            logger.error(f"Ошибка разбана: {e}")
            bot.reply_to(message, "❌ Не удалось разбанить пользователя!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /unban: {e}")

# 👢 КОМАНДА /KICK
@bot.message_handler(commands=['kick'])
def kick_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"👢 Команда /kick от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут кикать пользователей!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответьте на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        if is_user_admin(chat_id, target_user.id):
            bot.reply_to(message, "❌ Нельзя кикать других админов!")
            return
        
        reason = ' '.join(message.text.split()[1:]) or 'Нарушение правил'
        
        try:
            bot.ban_chat_member(chat_id, target_user.id)
            bot.unban_chat_member(chat_id, target_user.id)
            
            # Логируем действие
            db.add_moderation_log(
                chat_id, target_user.id, target_user.username, target_user.first_name,
                'kick', reason, None, user_id, message.from_user.first_name
            )
            
            bot.reply_to(message, f"👢 {target_user.first_name} кикнут!\n📝 Причина: {reason}")
        except Exception as e:
            logger.error(f"Ошибка кика: {e}")
            bot.reply_to(message, "❌ Не удалось кикнуть пользователя!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /kick: {e}")

# 🛡️ КОМАНДА /ADMIN
@bot.message_handler(commands=['admin'])
def admin_command(message):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        logger.info(f"🛡️ Команда /admin от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы имеют доступ к этой команде!")
            return
        
        response = (
            "🛡️ ПАНЕЛЬ АДМИНИСТРАТОРА\n\n"
            f"👤 Пользователь: {message.from_user.first_name}\n"
            f"🆔 ID: {user_id}\n"
            f"💬 Чат: {message.chat.title if message.chat.title else 'ЛС'}\n\n"
            "⚡ МОДЕРАЦИЯ:\n"
            "/warn - выдать предупреждение\n"
            "/mute - замутить пользователя\n" 
            "/unmute - снять мут\n"
            "/ban - забанить пользователя\n"
            "/unban - разбанить\n"
            "/kick - кикнуть пользователя\n\n"
            "⚙️ НАСТРОЙКИ:\n"
            "/settings - настройки чата\n"
            "/setup - настройка бота\n\n"
            "📊 СТАТИСТИКА:\n"
            "/botstats - статистика бота\n"
            "/analytics - аналитика чата\n"
            "/stats - статистика за сегодня\n\n"
            "🛡️ Вы имеете иммунитет к анти-мату!"
        )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /admin: {e}")

# ⚙️ КОМАНДА /SETTINGS
@bot.message_handler(commands=['settings'])
def settings_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"⚙️ Команда /settings от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут изменять настройки!")
            return
        
        args = message.text.split()[1:]
        settings = db.get_chat_settings(chat_id) or {}
        
        if not args:
            response = "⚙️ НАСТРОЙКИ ЧАТА:\n\n"
            response += f"🔞 Анти-мат: {'✅ ВКЛ' if settings.get('delete_mats', True) else '❌ ВЫКЛ'}\n"
            response += f"🔗 Анти-ссылки: {'✅ ВКЛ' if settings.get('delete_links', False) else '❌ ВЫКЛ'}\n"
            response += f"🚫 Анти-спам: {'✅ ВКЛ' if settings.get('anti_spam', True) else '❌ ВЫКЛ'}\n"
            response += f"🔇 Авто-мут: {'✅ ВКЛ' if settings.get('auto_mute', True) else '❌ ВЫКЛ'}\n"
            response += f"🎉 Приветствия: {'✅ ВКЛ' if settings.get('welcome_enabled', True) else '❌ ВЫКЛ'}\n"
            response += f"🎮 Игры: {'✅ ВКЛ' if settings.get('games_enabled', True) else '❌ ВЫКЛ'}\n"
            response += f"⏰ Мут (мин): {settings.get('mute_duration', 15)}\n"
            response += f"⚠️ Макс варнов: {settings.get('max_warns', 3)}\n"
            response += f"🛡️ Иммунитет админов: {'✅ ВКЛ' if settings.get('admins_immune', True) else '❌ ВЫКЛ'}\n"
            response += f"⏰ Кулдауны: {'✅ ВКЛ' if settings.get('cooldown_enabled', True) else '❌ ВЫКЛ'}\n"
            response += f"💼 Работа: {settings.get('cooldown_work', 300)} сек.\n"
            response += f"🕵️ Преступления: {settings.get('cooldown_crime', 300)} сек.\n"
            response += f"🎁 Daily: {settings.get('cooldown_daily', 86400)} сек.\n"
            response += f"🎮 Игры: {settings.get('cooldown_games', 30)} сек.\n\n"
            
            response += "🔄 ИЗМЕНИТЬ НАСТРОЙКУ:\n"
            response += "/settings [параметр] [значение]\n\n"
            response += "📋 ПАРАМЕТРЫ:\n"
            response += "• delete_mats on/off - анти-мат\n"
            response += "• delete_links on/off - анти-ссылки\n"
            response += "• max_warns [число] - макс варнов (3-20)\n"
            response += "• mute_duration [минуты] - время мута\n"
            response += "• games_enabled on/off - игры\n"
            response += "• admins_immune on/off - иммунитет админов\n"
            response += "• cooldown_enabled on/off - кулдауны\n"
            response += "• cooldown_work [секунды] - кулдаун работы\n"
            response += "• cooldown_crime [секунды] - кулдаун преступлений\n"
            response += "• cooldown_daily [секунды] - кулдаун daily\n"
            response += "• cooldown_games [секунды] - кулдаун игр\n\n"
            response += "💡 Пример: /settings delete_mats off"
            bot.reply_to(message, response)
            return
        
        if len(args) >= 2:
            param = args[0].lower()
            value = args[1].lower()
            
            valid_params = ['delete_mats', 'delete_links', 'anti_spam', 'auto_mute', 'welcome_enabled', 
                          'games_enabled', 'max_warns', 'mute_duration', 'admins_immune',
                          'cooldown_enabled', 'cooldown_work', 'cooldown_crime', 'cooldown_daily', 'cooldown_games']
            
            if param in valid_params:
                if param in ['max_warns', 'mute_duration', 'cooldown_work', 'cooldown_crime', 'cooldown_daily', 'cooldown_games']:
                    try:
                        int_value = int(value)
                        if param == 'max_warns' and (int_value < 3 or int_value > 20):
                            bot.reply_to(message, "❌ Макс. варнов должно быть от 3 до 20!")
                            return
                        elif param == 'mute_duration' and (int_value < 1 or int_value > 1440):
                            bot.reply_to(message, "❌ Время мута должно быть от 1 до 1440 минут!")
                            return
                        elif param in ['cooldown_work', 'cooldown_crime', 'cooldown_daily', 'cooldown_games'] and int_value < 0:
                            bot.reply_to(message, "❌ Время кулдауна не может быть отрицательным!")
                            return
                        
                        settings[param] = int_value
                        db.update_chat_settings(chat_id, settings)
                        bot.reply_to(message, f"✅ {param} установлено: {int_value}")
                        return
                    except ValueError:
                        bot.reply_to(message, "❌ Введите корректное число!")
                        return
                
                elif value in ['on', 'true', '1', 'yes', 'вкл']:
                    settings[param] = True
                    db.update_chat_settings(chat_id, settings)
                    bot.reply_to(message, f"✅ {param} ВКЛЮЧЕН!")
                elif value in ['off', 'false', '0', 'no', 'выкл']:
                    settings[param] = False
                    db.update_chat_settings(chat_id, settings)
                    bot.reply_to(message, f"✅ {param} ВЫКЛЮЧЕН!")
                else:
                    bot.reply_to(message, "❌ Используйте: on/off или число для числовых параметров")
            else:
                bot.reply_to(message, f"❌ Неизвестный параметр. Доступные: {', '.join(valid_params)}")
        else:
            bot.reply_to(message, "❌ Используйте: /settings [параметр] [значение]")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /settings: {e}")

# ⚙️ КОМАНДА /SETUP
@bot.message_handler(commands=['setup'])
def setup_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"🛡️ Команда /setup от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут настраивать бота!")
            return
        
        if message.chat.type == 'private':
            bot.reply_to(message, "❌ Добавьте бота в группу для настройки!")
            return
        
        chat_title = message.chat.title or "Без названия"
        db.add_chat(chat_id, chat_title)
        
        if user_id in GLOBAL_ADMINS:
            db.add_chat_admin(chat_id, user_id, message.from_user.username, message.from_user.first_name, user_id, 'owner')
        
        response = (
            f"✅ БОТ НАСТРОЕН В ЧАТЕ: {chat_title}\n\n"
            "🟢 ВСЕ ФУНКЦИИ АКТИВИРОВАНЫ:\n\n"
            "🔞 Анти-мат: ВКЛЮЧЕН\n"
            "🛡️ Иммунитет админов: ВКЛЮЧЕН\n"  
            "🎮 Игры: ВКЛЮЧЕНЫ\n"
            "📊 Статистика: ВКЛЮЧЕНА\n"
            "⚠️ Варны: АКТИВНЫ\n"
            "🔇 Авто-мут: ВКЛЮЧЕН\n"
            "⏰ Кулдауны: ВКЛЮЧЕНЫ\n\n"
            "📈 Ежедневные отчеты: АКТИВНЫ\n\n"
            "⚡ Используйте /menu для просмотра команд"
        )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /setup: {e}")

# 📊 КОМАНДА /BOTSTATS
@bot.message_handler(commands=['botstats'])
def bot_stats_command(message):
    try:
        user_id = message.from_user.id
        
        logger.info(f"📊 Команда /botstats от {user_id}")
        
        if not is_user_admin(message.chat.id, user_id):
            bot.reply_to(message, "❌ Только админы могут просматривать статистику бота!")
            return
        
        response = (
            "📊 СТАТИСТИКА БОТА\n\n"
            "💬 Чатов: 1+\n"
            "👥 Пользователей: 100+\n"
            "🕒 Время работы: 24/7\n"
            "⚡ Версия: ULTIMATE PRO MAX\n"
            "🛡️ Админов: 2\n"
            "📈 Ежедневные отчеты: АКТИВНЫ\n\n"
            "🔧 Все системы работают стабильно!"
        )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /botstats: {e}")

# 📈 КОМАНДА /ANALYTICS
@bot.message_handler(commands=['analytics'])
def analytics_command(message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"📈 Команда /analytics от {user_id}")
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут просматривать аналитику!")
            return
        
        top_users = db.get_top_users(chat_id, 5)
        today_stats = db.get_today_stats(chat_id)
        
        response = "📊 АНАЛИТИКА ЧАТА\n\n"
        response += "🏆 ТОП-5 АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:\n"
        
        for i, (user_id, first_name, username, msg_count, balance, level) in enumerate(top_users, 1):
            username_display = f"(@{username})" if username else ""
            response += f"{i}. {first_name} {username_display}\n"
            response += f"   💬 {msg_count} сообщ. | 💰 {balance} монет\n"
        
        response += f"\n📈 СЕГОДНЯШНЯЯ СТАТИСТИКА:\n"
        response += f"📝 Сообщений: {today_stats['messages']}\n"
        response += f"🎮 Игр: {today_stats['games']}\n"
        response += f"🔇 Мутов: {today_stats['mutes']}\n"
        response += f"⚠️ Варнов: {today_stats['warns']}\n\n"
        
        response += f"👥 Всего активных: {len(top_users)}\n"
        response += f"💬 Сообщений всего: {sum(user[3] for user in top_users)}\n"
        response += f"💰 Общий баланс: {sum(user[4] for user in top_users)} монет"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /analytics: {e}")

# 🔧 КОМАНДА /ADDADMIN
@bot.message_handler(commands=['addadmin'])
def add_admin_command(message):
    try:
        user_id = message.from_user.id
        
        if not is_super_admin(user_id):
            bot.reply_to(message, "❌ Только супер-админы могут добавлять админов!")
            return
        
        args = message.text.split()[1:]
        if len(args) < 1:
            bot.reply_to(message, "❌ Используйте: /addadmin [user_id] или ответьте на сообщение пользователя")
            return
        
        if message.reply_to_message:
            target_user = message.reply_to_message.from_user
            target_user_id = target_user.id
            username = target_user.username
            first_name = target_user.first_name
        else:
            try:
                target_user_id = int(args[0])
                username = message.from_user.username
                first_name = message.from_user.first_name
            except ValueError:
                bot.reply_to(message, "❌ Введите корректный ID пользователя!")
                return
        
        db.add_super_admin(target_user_id, username, first_name)
        
        bot.reply_to(message, f"✅ Пользователь {first_name} (@{username}) добавлен как супер-админ!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /addadmin: {e}")

# 🎯 КОМАНДА /PING
@bot.message_handler(commands=['ping'])
def ping_command(message):
    try:
        start_time = time.time()
        msg = bot.reply_to(message, "🏓 Понг...")
        end_time = time.time()
        
        ping_time = round((end_time - start_time) * 1000)
        
        bot.edit_message_text(
            f"🏓 Понг! Задержка: {ping_time}мс",
            chat_id=message.chat.id,
            message_id=msg.message_id
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /ping: {e}")

# 🆔 КОМАНДА /ID
@bot.message_handler(commands=['id'])
def id_command(message):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        response = (
            f"👤 ВАШИ ID:\n\n"
            f"🆔 User ID: {user_id}\n"
            f"💬 Chat ID: {chat_id}\n"
            f"📛 Username: @{message.from_user.username or 'нет'}\n"
            f"👑 Админ: {'✅' if is_user_admin(chat_id, user_id) else '❌'}"
        )
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /id: {e}")

# 📋 КОМАНДА HELP
@bot.message_handler(commands=['help', 'start', 'menu'])
def help_command(message):
    try:
        response = """
🤖 МЕГА-БОТ ULTIMATE PRO MAX EDITION

👮 МОДЕРАЦИЯ:
/warn - выдать предупреждение
/mute - замутить пользователя  
/unmute - снять мут
/ban - забанить пользователя
/unban - разбанить
/kick - кикнуть пользователя
/settings - настройки чата

🛡️ АДМИН-ПАНЕЛЬ:
/admin - панель администратора
/setup - настройка бота
/promote - добавить админа
/demote - снять админа
/removeadmin - удалить админа из базы
/admins - список админов
/listbotadmins - админы в базе данных
/stats - статистика за сегодня

💰 ЭКОНОМИКА:
/balance - баланс
/work - работа
/daily - ежедневный бонус
/transfer - перевод денег
/top - топ игроков
/mystatus - мой статус

💍 ОТНОШЕНИЯ:
/marry - предложить брак
/divorce - развод
/accept - принять предложение

🕵️ ПРЕСТУПЛЕНИЯ:
/crime - совершить преступление

💼 БИЗНЕС:
/business - мои бизнесы
/buybusiness - купить бизнес

🎮 ИГРЫ:
/slots [ставка] - игровые автоматы
/coinflip [орёл/решка] [ставка] - монетка
/dicebattle [ставка] - битва кубиков
/dice - бросить кубик
/basketball - баскетбол
/bowling - боулинг  
/football - футбол
/darts - дартс

🔧 УТИЛИТЫ:
/id - мой ID
/ping - проверка бота
"""
        
        bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /help: {e}")

# 📊 ОБРАБОТКА СООБЩЕНИЙ

@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'sticker', 'voice'])
def handle_all_messages(message):
    try:
        text = message.text or ""
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        logger.info(f"🔍 НОВОЕ СООБЩЕНИЕ: chat={chat_id}, user={user_id}")
        logger.info(f"🔍 SENDER_CHAT: {getattr(message, 'sender_chat', 'ОТСУТСТВУЕТ')}")
        
        # 🚫 ПРОВЕРКА НА КАНАЛЫ (ДЛЯ НЕ-АНОНИМНОГО БОТА)
        if hasattr(message, 'sender_chat') and message.sender_chat:
            logger.info(f"🎯 SENDER_CHAT: type={message.sender_chat.type}, title={message.sender_chat.title}")
            
            if message.sender_chat.type == 'channel':
                logger.info(f"🚫 ОБНАРУЖЕН КАНАЛ: {message.sender_chat.title}")
                try:
                    # Для не-анонимного бота используем restrict вместо ban
                    until_date = int(time.time()) + 31536000  # Бан на 1 год
                    
                    bot.restrict_chat_member(
                        chat_id, 
                        message.sender_chat.id,
                        until_date=until_date,
                        permissions=telebot.types.ChatPermissions(
                            can_send_messages=False,
                            can_send_media_messages=False,
                            can_send_other_messages=False,
                            can_add_web_page_previews=False
                        )
                    )
                    logger.info(f"✅ Канал {message.sender_chat.title} ограничен")
                    
                    # Удаляем сообщение
                    bot.delete_message(chat_id, message.message_id)
                    logger.info("✅ Сообщение канала удалено")
                    
                    # Уведомляем
                    warning_msg = bot.send_message(
                        chat_id,
                        f"🚫 Канал {message.sender_chat.title} заблокирован!"
                    )
                    
                    # Удаляем уведомление через 5 сек
                    threading.Timer(5.0, lambda: bot.delete_message(chat_id, warning_msg.message_id)).start()
                    
                    return
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка блокировки канала: {e}")
                    # Пытаемся хотя бы удалить сообщение
                    try:
                        bot.delete_message(chat_id, message.message_id)
                        logger.info("✅ Сообщение канала удалено (без бана)")
                    except:
                        pass
                    return
        
        logger.info(f"📝 Обычное сообщение от пользователя: {user_id}")
        
        # Остальная логика...
        db.update_user_stats(chat_id, user_id, message.from_user.username, message.from_user.first_name)
        
        if message.chat.type != 'private':
            settings = db.get_chat_settings(chat_id)
            if settings and settings.get('delete_mats', True):
                has_violation, bad_word = super_moderation(text)
                if has_violation:
                    if is_user_admin(chat_id, user_id) and settings.get('admins_immune', True):
                        logger.info(f"🛡️ Админ {user_id} использовал мат, но имеет иммунитет: {hide_bad_word(bad_word)}")
                    else:
                        try:
                            bot.delete_message(chat_id, message.message_id)
                            logger.info(f"🔞 Сообщение удалено: {user_id} использовал мат: {hide_bad_word(bad_word)}")
                            
                            db.add_violation(chat_id, user_id, message.from_user.username, 
                                           message.from_user.first_name, bad_word, 'мат')
                            
                            warning_msg = bot.send_message(
                                chat_id,
                                f"⚠️ {message.from_user.first_name}, не используйте маты!\n" +
                                f"🔞 Обнаружено слово: {hide_bad_word(bad_word)}"
                            )
                            
                            threading.Timer(5.0, lambda: bot.delete_message(chat_id, warning_msg.message_id)).start()
                            
                        except Exception as e:
                            logger.error(f"❌ Ошибка удаления сообщения: {e}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")
        if message.chat.type != 'private':
            settings = db.get_chat_settings(chat_id)
            if settings and settings.get('delete_mats', True):
                has_violation, bad_word = super_moderation(text)
                if has_violation:
                    if is_user_admin(chat_id, user_id) and settings.get('admins_immune', True):
                        logger.info(f"🛡️ Админ {user_id} использовал мат, но имеет иммунитет: {hide_bad_word(bad_word)}")
                    else:
                        try:
                            bot.delete_message(chat_id, message.message_id)
                            logger.info(f"🔞 Сообщение удалено: {user_id} использовал мат: {hide_bad_word(bad_word)}")
                            
                            db.add_violation(chat_id, user_id, message.from_user.username, 
                                           message.from_user.first_name, bad_word, 'мат')
                            
                            warning_msg = bot.send_message(
                                chat_id,
                                f"⚠️ {message.from_user.first_name}, не используйте маты!\n" +
                                f"🔞 Обнаружено слово: {hide_bad_word(bad_word)}"
                            )
                            
                            threading.Timer(5.0, lambda: bot.delete_message(chat_id, warning_msg.message_id)).start()
                            
                        except Exception as e:
                            logger.error(f"❌ Ошибка удаления сообщения: {e}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")
        return
        db.update_user_stats(chat_id, user_id, message.from_user.username, message.from_user.first_name)
        
        if message.chat.type != 'private':
            settings = db.get_chat_settings(chat_id)
            if settings and settings.get('delete_mats', True):
                has_violation, bad_word = super_moderation(text)
                if has_violation:
                    if is_user_admin(chat_id, user_id) and settings.get('admins_immune', True):
                        logger.info(f"🛡️ Админ {user_id} использовал мат, но имеет иммунитет: {hide_bad_word(bad_word)}")
                    else:
                        try:
                            bot.delete_message(chat_id, message.message_id)
                            logger.info(f"🔞 Сообщение удалено: {user_id} использовал мат: {hide_bad_word(bad_word)}")
                            
                            db.add_violation(chat_id, user_id, message.from_user.username, 
                                           message.from_user.first_name, bad_word, 'мат')
                            
                            warning_msg = bot.send_message(
                                chat_id,
                                f"⚠️ {message.from_user.first_name}, не используйте маты!\n" +
                                f"🔞 Обнаружено слово: {hide_bad_word(bad_word)}"
                            )
                            
                            threading.Timer(5.0, lambda: bot.delete_message(chat_id, warning_msg.message_id)).start()
                            
                        except Exception as e:
                            logger.error(f"❌ Ошибка удаления сообщения: {e}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")

# ЗАПУСК БОТА
def start_bot():
    logger.info("🚀 ЗАПУСК БОТА...")
    
    for admin_id in GLOBAL_ADMINS:
        db.add_super_admin(admin_id, "admin", "Administrator")
    
    report_system.start_daily_reports()
    
    def cleanup_scheduler():
        while True:
            time.sleep(6 * 3600)
            cooldown.cleanup_old_entries()
            logger.info("🧹 Очистка кэша выполнена")
    
    cleanup_thread = threading.Thread(target=cleanup_scheduler, daemon=True)
    cleanup_thread.start()
    
    while True:
        try:
            logger.info("🟢 Запуск polling...")
            bot.polling(none_stop=True, timeout=60)
            
        except Exception as e:
            logger.error(f"❌ Ошибка polling: {e}")
            logger.info("🔄 Перезапуск через 10 секунд...")
            time.sleep(10)

if __name__ == "__main__":
    try:
        logger.info("🤖 МЕГА-БОТ ULTIMATE PRO MAX EDITION ЗАПУЩЕН")
        logger.info(f"🛡️ Глобальные админы: {GLOBAL_ADMINS}")
        start_bot()
    except KeyboardInterrupt:
        logger.info("⏹ Бот остановлен")
    except Exception as e:
        logger.critical(f"💥 Критический сбой: {e}")
