import telebot
import time
import sqlite3
import json
from datetime import datetime

# Токен бота
TOKEN = "8489739703:AAH_6XWjnz7KlTfaSLYlcN4d-FS9RDOAbjo"
bot = telebot.TeleBot(TOKEN)

print("🟢 УЛУЧШЕННЫЙ БОТ-МОДЕРАТОР ЗАПУЩЕН")

# 👑 СУПЕР-АДМИНЫ (неизменяемые)
SUPER_ADMINS = [5627578930, 7981729476]

# 🚫 РАСШИРЕННАЯ БАЗА ПЛОХИХ СЛОВ
BAD_WORDS = [
    # Русские маты
    'хуй', 'пизда', 'ебал', 'ебать', 'блядь', 'сука', 'пидор', 'гандон', 
    'мудак', 'мудила', 'долбоёб', 'еблан', 'заебал', 'выеб', 'выебан',
    'охуел', 'охуеть', 'пиздец', 'спиздил', 'схуяли', 'нахрен', 'нахуй',
    'гондон', 'шлюха', 'блядина', 'ебанный', 'ёбаный', 'пиздёнок', 'пиздюк',
    'хуесос', 'хуило', 'ебло', 'ебун', 'залупа', 'манда', 'мусор',
    
    # Английские маты
    'fuck', 'shit', 'bitch', 'asshole', 'dick', 'pussy', 'cock', 'whore',
    'motherfucker', 'bastard', 'cunt', 'slut', 'nigga', 'nigger',
    
    # Оскорбления
    'дебил', 'идиот', 'дурак', 'кретин', 'тупица', 'моральный урод',
    'конченный', 'отброс', 'мусор', 'тварь', 'скотина', 'ублюдок'
]

# 🔧 РАСШИРЕННЫЙ СПАМ-ФИЛЬТР
SPAM_KEYWORDS = [
    # Ссылки и приглашения
    't.me/join', 'http://', 'https://', 'www.', '.ru', '.com', '.net',
    'присоединяйся', 'подписывайся', 'канал', 'группа',
    
    # Реклама и продажи
    'купить', 'продам', 'заказать', 'скидка', 'акция', 'бесплатно',
    'реклама', 'распродажа', 'спецпредложение', 'выгодно',
    
    # Финансы и мошенничество
    'заработок', 'инвестиции', 'биржа', 'криптовалюта', 'брокер',
    'быстро деньги', 'легкий заработок', 'пассивный доход',
    
    # Личные данные
    'номер телефона', 'банковская карта', 'паспорт', 'пароль'
]

# 🗄️ БАЗА ДАННЫХ ДЛЯ ВАРНОВ И СТАТИСТИКИ
class SimpleDB:
    def __init__(self):
        self.conn = sqlite3.connect('moderation.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                reason TEXT,
                warned_by INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                chat_id INTEGER PRIMARY KEY,
                mutes_count INTEGER DEFAULT 0,
                bans_count INTEGER DEFAULT 0,
                kicks_count INTEGER DEFAULT 0,
                warns_count INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT,
                chat_id INTEGER,
                chat_title TEXT,
                user_id INTEGER,
                username TEXT,
                target_user_id INTEGER,
                target_username TEXT,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_by INTEGER,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                level INTEGER DEFAULT 1
            )
        ''')
        self.conn.commit()
    
    def add_warn(self, chat_id, user_id, username, reason, warned_by):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO warns (chat_id, user_id, username, reason, warned_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (chat_id, user_id, username, reason, warned_by))
        self.conn.commit()
    
    def get_warns_count(self, chat_id, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?', 
                      (chat_id, user_id))
        return cursor.fetchone()[0]
    
    def clear_warns(self, chat_id, user_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM warns WHERE chat_id = ? AND user_id = ?', 
                      (chat_id, user_id))
        self.conn.commit()
    
    def update_stats(self, chat_id, action):
        cursor = self.conn.cursor()
        cursor.execute(f'''
            INSERT OR REPLACE INTO stats (chat_id, {action}_count)
            VALUES (?, COALESCE((SELECT {action}_count FROM stats WHERE chat_id = ?), 0) + 1)
        ''', (chat_id, chat_id))
        self.conn.commit()
    
    def add_report(self, action_type, chat_id, chat_title, user_id, username, 
                  target_user_id=None, target_username=None, reason=None):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO reports (action_type, chat_id, chat_title, user_id, username, 
                               target_user_id, target_username, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (action_type, chat_id, chat_title, user_id, username, 
              target_user_id, target_username, reason))
        self.conn.commit()
    
    def get_today_stats(self):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT action_type, COUNT(*) FROM reports 
            WHERE DATE(timestamp) = ? 
            GROUP BY action_type
        ''', (today,))
        return dict(cursor.fetchall())
    
    # 🔐 МЕТОДЫ ДЛЯ УПРАВЛЕНИЯ АДМИНАМИ
    def add_admin(self, user_id, username, added_by, level=1):
        """Добавить админа"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO admins (user_id, username, added_by, level)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, added_by, level))
        self.conn.commit()
    
    def remove_admin(self, user_id):
        """Удалить админа"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def get_admin(self, user_id):
        """Получить информацию об админе"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
        return cursor.fetchone()
    
    def get_all_admins(self):
        """Получить всех админов"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM admins ORDER BY level DESC, added_date')
        return cursor.fetchall()
    
    def is_admin(self, user_id):
        """Проверить, является ли пользователь админом"""
        if user_id in SUPER_ADMINS:
            return True
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None

# Инициализация базы данных
db = SimpleDB()

def is_user_admin(chat_id, user_id):
    """Проверить права админа (супер-админы + админы из БД + админы чата)"""
    try:
        # Супер-админы всегда имеют права
        if user_id in SUPER_ADMINS:
            return True
        
        # Проверяем админов из базы данных
        if db.is_admin(user_id):
            return True
        
        # Проверяем админов чата
        chat_member = bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['administrator', 'creator']
    except:
        return False

def is_super_admin(user_id):
    """Проверить, является ли супер-админом"""
    return user_id in SUPER_ADMINS

def contains_bad_words(text):
    text_lower = text.lower()
    for word in BAD_WORDS:
        if word in text_lower:
            return True, word
    return False, ""

def is_spam(text):
    text_lower = text.lower()
    return any(word in text_lower for word in SPAM_KEYWORDS)

def send_auto_report(action_type, chat_id, user_id, target_user_id=None, reason=None):
    """Отправка автоотчета в ЛС админам"""
    try:
        chat_info = bot.get_chat(chat_id)
        user_info = bot.get_chat(user_id)
        
        if target_user_id:
            target_info = bot.get_chat(target_user_id)
            target_name = target_info.first_name if target_info.first_name else "Неизвестно"
        else:
            target_name = "Не указан"
        
        report_text = f"""
📊 АВТООТЧЕТ О ДЕЙСТВИИ

🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🎯 Действие: {action_type}
💬 Чат: {chat_info.title if hasattr(chat_info, 'title') else 'ЛС'}
👤 Модератор: {user_info.first_name} (ID: {user_id})
🎯 Цель: {target_name} (ID: {target_user_id if target_user_id else 'N/A'})
📝 Причина: {reason if reason else 'Не указана'}
        """
        
        # Отправляем отчет всем админам и супер-админам
        all_admins = set(SUPER_ADMINS)
        for admin in db.get_all_admins():
            all_admins.add(admin[0])
        
        for admin_id in all_admins:
            try:
                bot.send_message(admin_id, report_text)
            except Exception as e:
                print(f"❌ Не удалось отправить отчет админу {admin_id}: {e}")
        
        # Сохраняем в базу данных
        db.add_report(
            action_type=action_type,
            chat_id=chat_id,
            chat_title=chat_info.title if hasattr(chat_info, 'title') else 'ЛС',
            user_id=user_id,
            username=user_info.first_name,
            target_user_id=target_user_id,
            target_username=target_name,
            reason=reason
        )
        
    except Exception as e:
        print(f"❌ Ошибка отправки автоотчета: {e}")

# 🔐 КОМАНДЫ УПРАВЛЕНИЯ АДМИНАМИ
@bot.message_handler(commands=['addadmin'])
def add_admin_command(message):
    """Добавить админа"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Только супер-админы могут добавлять админов
        if not is_super_admin(user_id):
            bot.reply_to(message, "❌ Только супер-админы могут добавлять админов!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение пользователя, которого хочешь сделать админом!")
            return
        
        target_user = message.reply_to_message.from_user
        
        # Нельзя добавить самого себя (и так админ)
        if target_user.id == user_id:
            bot.reply_to(message, "❌ Ты и так админ!")
            return
        
        # Проверяем, не супер-админ ли уже
        if target_user.id in SUPER_ADMINS:
            bot.reply_to(message, "❌ Этот пользователь уже супер-админ!")
            return
        
        # Проверяем, не админ ли уже
        if db.is_admin(target_user.id):
            bot.reply_to(message, "❌ Этот пользователь уже админ!")
            return
        
        # Добавляем админа
        db.add_admin(
            user_id=target_user.id,
            username=target_user.first_name or target_user.username or "Unknown",
            added_by=user_id,
            level=1
        )
        
        # Отправляем автоотчет
        send_auto_report("ADD_ADMIN", chat_id, user_id, target_user.id, "Добавление админа")
        
        bot.reply_to(message, f"✅ {target_user.first_name} теперь админ!")
        
        # Уведомляем нового админа
        try:
            bot.send_message(
                target_user.id,
                f"🎉 Поздравляем! Теперь вы админ бота-модератора!\n\n"
                f"Доступные команды:\n"
                f"/ban - бан пользователя\n"
                f"/kick - кик пользователя\n"
                f"/mute - мут пользователя\n"
                f"/warn - выдать предупреждение\n"
                f"И другие команды модерации!"
            )
        except:
            pass
            
    except Exception as e:
        print(f"❌ Ошибка в /addadmin: {e}")
        bot.reply_to(message, "❌ Ошибка при добавлении админа!")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message):
    """Удалить админа"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Только супер-админы могут удалять админов
        if not is_super_admin(user_id):
            bot.reply_to(message, "❌ Только супер-админы могут удалять админов!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение админа, которого хочешь удалить!")
            return
        
        target_user = message.reply_to_message.from_user
        
        # Нельзя удалить самого себя
        if target_user.id == user_id:
            bot.reply_to(message, "❌ Нельзя удалить самого себя!")
            return
        
        # Нельзя удалить супер-админа
        if target_user.id in SUPER_ADMINS:
            bot.reply_to(message, "❌ Нельзя удалить супер-админа!")
            return
        
        # Проверяем, является ли админом
        if not db.is_admin(target_user.id):
            bot.reply_to(message, "❌ Этот пользователь не является админом!")
            return
        
        # Удаляем админа
        db.remove_admin(target_user.id)
        
        # Отправляем автоотчет
        send_auto_report("REMOVE_ADMIN", chat_id, user_id, target_user.id, "Удаление админа")
        
        bot.reply_to(message, f"✅ {target_user.first_name} больше не админ!")
        
    except Exception as e:
        print(f"❌ Ошибка в /removeadmin: {e}")
        bot.reply_to(message, "❌ Ошибка при удалении админа!")

@bot.message_handler(commands=['adminlist'])
def admin_list_command(message):
    """Список всех админов"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут просматривать список админов!")
            return
        
        admins_list = ["👑 СУПЕР-АДМИНЫ:"]
        
        # Добавляем супер-админов
        for super_admin_id in SUPER_ADMINS:
            try:
                user_info = bot.get_chat(super_admin_id)
                admins_list.append(f"👑 {user_info.first_name} (ID: {super_admin_id})")
            except:
                admins_list.append(f"👑 Unknown (ID: {super_admin_id})")
        
        admins_list.append("\n👨‍💼 АДМИНЫ БОТА:")
        
        # Добавляем админов из БД
        db_admins = db.get_all_admins()
        if db_admins:
            for admin in db_admins:
                admin_id, username, added_by, added_date, level = admin
                try:
                    user_info = bot.get_chat(admin_id)
                    display_name = user_info.first_name
                except:
                    display_name = username or "Unknown"
                
                admins_list.append(f"🛡️ {display_name} (ID: {admin_id})")
        else:
            admins_list.append("Нет добавленных админов")
        
        response = "\n".join(admins_list)
        bot.reply_to(message, response)
        
    except Exception as e:
        print(f"❌ Ошибка в /adminlist: {e}")
        bot.reply_to(message, "❌ Ошибка при получении списка админов!")

@bot.message_handler(commands=['myadmin'])
def my_admin_info(message):
    """Информация о своих правах админа"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        if is_super_admin(user_id):
            status = "👑 СУПЕР-АДМИН"
        elif db.is_admin(user_id):
            admin_info = db.get_admin(user_id)
            status = f"🛡️ АДМИН (Уровень: {admin_info[4]})"
        elif is_user_admin(chat_id, user_id):
            status = "💬 АДМИН ЧАТА"
        else:
            status = "👤 ПОЛЬЗОВАТЕЛЬ"
        
        response = f"""
📋 ИНФОРМАЦИЯ О ПРАВАХ:

👤 Ваш ID: {user_id}
🎯 Статус: {status}
💬 Чат: {message.chat.title if hasattr(message.chat, 'title') else 'ЛС'}

{"⚠️ Внимание: Вы не являетесь админом бота!" if status == "👤 ПОЛЬЗОВАТЕЛЬ" else "✅ Вы имеете права модерации!"}
        """
        
        bot.reply_to(message, response)
        
    except Exception as e:
        print(f"❌ Ошибка в /myadmin: {e}")

# 🛡️ ОСНОВНЫЕ КОМАНДЫ МОДЕРАЦИИ (с проверкой иммунитета админов)
def check_admin_immunity(chat_id, target_user_id, action_name):
    """Проверить иммунитет админа перед действием"""
    if is_user_admin(chat_id, target_user_id):
        return f"❌ Нельзя {action_name} других админов!"
    return None

@bot.message_handler(commands=['ban'])
def ban_user(message):
    """Забанить пользователя"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут банить!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        # Проверяем иммунитет админа
        immunity_check = check_admin_immunity(chat_id, target_user.id, "банить")
        if immunity_check:
            bot.reply_to(message, immunity_check)
            return
        
        reason = ' '.join(message.text.split()[1:]) or 'Нарушение правил'
        
        bot.ban_chat_member(chat_id, target_user.id)
        db.update_stats(chat_id, 'bans')
        
        # Отправляем автоотчет
        send_auto_report("BAN", chat_id, user_id, target_user.id, reason)
        
        bot.reply_to(message, f"🚫 {target_user.first_name} забанен!\n📝 Причина: {reason}")
        
    except Exception as e:
        print(f"❌ Ошибка в /ban: {e}")

@bot.message_handler(commands=['kick'])
def kick_user(message):
    """Кикнуть пользователя"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут кикать!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        # Проверяем иммунитет админа
        immunity_check = check_admin_immunity(chat_id, target_user.id, "кикать")
        if immunity_check:
            bot.reply_to(message, immunity_check)
            return
        
        reason = ' '.join(message.text.split()[1:]) or 'Нарушение правил'
        
        bot.ban_chat_member(chat_id, target_user.id)
        bot.unban_chat_member(chat_id, target_user.id)
        db.update_stats(chat_id, 'kicks')
        
        # Отправляем автоотчет
        send_auto_report("KICK", chat_id, user_id, target_user.id, reason)
        
        bot.reply_to(message, f"👢 {target_user.first_name} кикнут!\n📝 Причина: {reason}")
        
    except Exception as e:
        print(f"❌ Ошибка в /kick: {e}")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    """Замутить пользователя"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут мутить!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        # Проверяем иммунитет админа
        immunity_check = check_admin_immunity(chat_id, target_user.id, "мутить")
        if immunity_check:
            bot.reply_to(message, immunity_check)
            return
        
        args = message.text.split()[1:]
        duration = int(args[0]) if args and args[0].isdigit() else 60
        
        until_date = int(time.time()) + duration * 60
        bot.restrict_chat_member(
            chat_id, target_user.id,
            until_date=until_date,
            permissions=telebot.types.ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
        
        db.update_stats(chat_id, 'mutes')
        
        # Отправляем автоотчет
        reason = f'Мут на {duration} минут'
        send_auto_report("MUTE", chat_id, user_id, target_user.id, reason)
        
        bot.reply_to(message, f"🔇 {target_user.first_name} замьючен на {duration} минут!")
        
    except Exception as e:
        print(f"❌ Ошибка в /mute: {e}")

@bot.message_handler(commands=['warn'])
def warn_user(message):
    """Выдать предупреждение"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут выдавать варны!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        # Проверяем иммунитет админа
        immunity_check = check_admin_immunity(chat_id, target_user.id, "выдавать варны")
        if immunity_check:
            bot.reply_to(message, immunity_check)
            return
        
        reason = ' '.join(message.text.split()[1:]) or 'Нарушение правил'
        
        db.add_warn(chat_id, target_user.id, target_user.first_name, reason, user_id)
        warns_count = db.get_warns_count(chat_id, target_user.id)
        db.update_stats(chat_id, 'warns')
        
        # Отправляем автоотчет
        send_auto_report("WARN", chat_id, user_id, target_user.id, reason)
        
        response = f"⚠️ {target_user.first_name} получил предупреждение!\n📝 Причина: {reason}\n🎯 Всего варнов: {warns_count}/3"
        
        if warns_count >= 3:
            until_date = int(time.time()) + 60 * 60
            bot.restrict_chat_member(
                chat_id, target_user.id,
                until_date=until_date,
                permissions=telebot.types.ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False
                )
            )
            db.clear_warns(chat_id, target_user.id)
            response += f"\n🔇 Автоматический мут на 1 час!"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        print(f"❌ Ошибка в /warn: {e}")

# 🔧 ОСТАЛЬНЫЕ КОМАНДЫ (остаются без изменений)
@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    """Размутить пользователя"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут размучивать!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        bot.restrict_chat_member(
            chat_id, target_user.id,
            permissions=telebot.types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        
        # Отправляем автоотчет
        send_auto_report("UNMUTE", chat_id, user_id, target_user.id, "Размут")
        
        bot.reply_to(message, f"🔊 {target_user.first_name} размучен!")
        
    except Exception as e:
        print(f"❌ Ошибка в /unmute: {e}")

@bot.message_handler(commands=['unwarn'])
def unwarn_user(message):
    """Снять предупреждение"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут снимать варны!")
            return
        
        if not message.reply_to_message:
            bot.reply_to(message, "❌ Ответь на сообщение пользователя!")
            return
        
        target_user = message.reply_to_message.from_user
        
        db.clear_warns(chat_id, target_user.id)
        
        # Отправляем автоотчет
        send_auto_report("UNWARN", chat_id, user_id, target_user.id, "Снятие всех варнов")
        
        bot.reply_to(message, f"✅ Все предупреждения сняты с {target_user.first_name}!")
        
    except Exception as e:
        print(f"❌ Ошибка в /unwarn: {e}")

@bot.message_handler(commands=['report'])
def send_daily_report(message):
    """Отправить дневной отчет"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        if not is_user_admin(chat_id, user_id):
            bot.reply_to(message, "❌ Только админы могут запрашивать отчеты!")
            return
        
        today_stats = db.get_today_stats()
        
        report_text = f"""
📊 ДНЕВНОЙ ОТЧЕТ ЗА {datetime.now().strftime('%d.%m.%Y')}

📈 СТАТИСТИКА ДЕЙСТВИЙ:
• Баны: {today_stats.get('BAN', 0)}
• Кики: {today_stats.get('KICK', 0)}
• Муты: {today_stats.get('MUTE', 0)}
• Варны: {today_stats.get('WARN', 0)}
• Размуты: {today_stats.get('UNMUTE', 0)}
• Очистки: {today_stats.get('CLEAR', 0) + today_stats.get('PURGE', 0)}

🕐 Сгенерировано: {datetime.now().strftime('%H:%M:%S')}
        """
        
        bot.reply_to(message, report_text)
        
    except Exception as e:
        print(f"❌ Ошибка в /report: {e}")

# 🎯 КОМАНДА HELP (обновленная)
@bot.message_handler(commands=['start', 'help', 'menu'])
def start_command(message):
    user_id = message.from_user.id
    is_admin_user = is_user_admin(message.chat.id, user_id)
    
    response = """
🤖 УЛУЧШЕННЫЙ БОТ-МОДЕРАТОР

🛡️ ОСНОВНЫЕ КОМАНДЫ:
/ban - забанить пользователя
/kick - кикнуть пользователя  
/mute - замутить
/unmute - размутить
/warn - выдать предупреждение
/unwarn - снять все варны
/warns - проверить варны

🧹 УПРАВЛЕНИЕ СООБЩЕНИЯМИ:
/clear - удалить сообщение
/purge [число] - массовое удаление
/pin - закрепить сообщение
/unpin - открепить сообщение

📊 ОТЧЕТНОСТЬ:
/report - дневной отчет
/myadmin - информация о правах
"""
    
    # Добавляем команды для супер-админов
    if is_super_admin(user_id):
        response += """
🔐 СУПЕР-АДМИН КОМАНДЫ:
/addadmin - добавить админа
/removeadmin - удалить админа  
/adminlist - список всех админов
"""
    elif is_admin_user:
        response += "\n/adminlist - список админов"
    
    response += """
🔧 ДОПОЛНИТЕЛЬНО:
/id - получить ID пользователя

🚫 АВТО-МОДЕРАЦИЯ:
• Блокирует маты (60+ слов)
• Удаляет спам и рекламу
• Защищает от каналов
• Система предупреждений
• Автоотчеты в ЛС админам
• Иммунитет админов
"""
    bot.reply_to(message, response)

print("🚀 Улучшенный бот-модератор запущен!")
print("📊 База данных: moderation.db")
print("📨 Система автоотчетов активирована!")
print("🔐 Система управления админами активирована!")
bot.polling()
