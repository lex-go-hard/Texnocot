import datetime
import os
import sqlite3
from datetime import datetime

import pandas as pd
import vk_api
from dotenv import load_dotenv
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

# Загрузка переменных окружения
load_dotenv("keys.env")
GROUP_TOKEN = os.getenv('GROUP_TOKEN')
GROUP_ID = int(os.getenv('GROUP_ID'))
ADMIN_ID = list(map(int, os.getenv('ADMIN_ID').split(",")))

# Подключение к базе данных
conn = sqlite3.connect('bot_db.sqlite')
cursor = conn.cursor()


# 📨 Функция для получения списка подписчиков
def get_group_members():
    members = vk.groups.getMembers(group_id=GROUP_ID)['items']
    return members


# Флаг для ожидания сообщения для рассылки
awaiting_news_message = False


# ✅ Функция для создания таблиц, если их нет
def create_tables():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            keyword TEXT PRIMARY KEY,
            response TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            keyword TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            age INTEGER,
            city TEXT,
            status TEXT,
            last_seen DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity (
            user_id INTEGER PRIMARY KEY,
            message_count INTEGER DEFAULT 0,
            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    print("✅ Таблицы проверены/созданы.")


def get_user_stats():
    try:
        # Получаем статистику о пользователях
        cursor.execute('''
             SELECT u.user_id, u.first_name, u.last_name, u.age, u.city, u.status, 
                    a.message_count, a.last_activity
             FROM users u
             JOIN user_activity a ON u.user_id = a.user_id
             ORDER BY a.message_count DESC
         ''')
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка при получении статистики пользователей: {e}")
        return []


def update_user_activity(user_id):
    try:
        # Обновляем количество сообщений и время последней активности
        cursor.execute('''
            INSERT INTO user_activity (user_id, message_count, last_activity)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
            message_count = message_count + 1,
            last_activity = CURRENT_TIMESTAMP
        ''', (user_id,))
        conn.commit()
    except Exception as e:
        print(f"Ошибка при обновлении активности пользователя: {e}")


def update_user_info(user_id):
    try:
        # Получаем информацию о пользователе из VK API
        user_info = vk.users.get(user_ids=user_id, fields='first_name,last_name,city,bdate,status,last_seen')[0]

        # Извлекаем данные
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        city = user_info.get('city', {}).get('title', 'Не указан')
        bdate = user_info.get('bdate', '')
        status = user_info.get('status', '')
        last_seen = datetime.fromtimestamp(user_info.get('last_seen', {}).get('time', 0))

        # Вычисляем возраст (если дата рождения указана)
        age = None
        if bdate:
            try:
                birth_date = datetime.strptime(bdate, "%d.%m.%Y")
                age = datetime.now().year - birth_date.year
            except ValueError:
                pass

        # Обновляем или добавляем информацию о пользователе в базу данных
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, first_name, last_name, age, city, status, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, first_name, last_name, age, city, status, last_seen))

        conn.commit()
    except Exception as e:
        print(f"Ошибка при обновлении информации о пользователе: {e}")


# 📥 Обработчик загрузки файла
def handle_file_upload(file_url, peer_id):
    try:
        # Загружаем Excel-файл
        df = pd.read_excel(file_url)

        # Проверяем наличие нужных столбцов
        if 'keyword' not in df.columns or 'response' not in df.columns:
            send_message(peer_id, "❌ Ошибка! Таблица должна содержать столбцы: 'keyword' и 'response'.")
            return

        # Убираем дубликаты и подготавливаем данные
        df = df[['keyword', 'response']].drop_duplicates()

        # Удаляем строки, где хотя бы одно поле пустое
        df = df.dropna()

        # Загружаем существующие ключевые слова из базы
        cursor.execute("SELECT keyword FROM keywords")
        existing_keywords = {row[0] for row in cursor.fetchall()}

        # Фильтруем только новые ключевые слова
        new_data = df[~df['keyword'].isin(existing_keywords)]

        # Записываем в базу новые значения
        for _, row in new_data.iterrows():
            cursor.execute("INSERT INTO keywords (keyword, response) VALUES (?, ?)", (row['keyword'], row['response']))

        conn.commit()
        send_message(peer_id, "✅ Таблица успешно загружена!")

    except Exception as e:
        send_message(peer_id, f"❌ Ошибка при обработке файла: {str(e)}")


# 📩 Функция для отправки сообщений
def send_message(peer_id, text):
    vk.messages.send(
        peer_id=peer_id,
        message=str(text),
        random_id=0
    )


# 📊 Получение статистики
def get_admin_stats():
    cursor.execute('''
        SELECT keyword, COUNT(*) as count, 
               (COUNT(*) * 100.0 / (SELECT COUNT(*) FROM message_log)) as percent 
        FROM message_log 
        GROUP BY keyword 
        ORDER BY count DESC
    ''')
    return cursor.fetchall()


# Инициализация VK API
vk_session = vk_api.VkApi(token=GROUP_TOKEN)
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
vk = vk_session.get_api()
# Создание таблиц при запуске
create_tables()

# 🛠️ Основной цикл обработки событий
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        message = event.object.message
        msg_text = message['text'].lower()
        user_id = message['from_id']
        peer_id = message['peer_id']
        print(f"📩 Сообщение: '{msg_text}' от user_id: {user_id} | peer_id: {peer_id}")

        # Обновляем информацию о пользователе и его активности
        update_user_info(user_id)
        update_user_activity(user_id)

        if msg_text == "/stats_users" and user_id in ADMIN_ID:
            stats = get_user_stats()
            response = "📊 Статистика пользователей:\n"
            for user in stats:
                user_id, first_name, last_name, age, city, status, message_count, last_activity = user
                response += (
                    f"👤 {first_name} {last_name} (ID: {user_id})\n"
                    f"- Возраст: {age if age else 'Не указан'}\n"
                    f"- Город: {city}\n"
                    f"- Статус: {status}\n"
                    f"- Сообщений: {message_count}\n"
                    f"- Последняя активность: {last_activity}\n\n"
                )
            send_message(peer_id, response)
            continue

        # 📤 Обработка команды /upload (только для админа)
        if msg_text == "/upload" and user_id in ADMIN_ID:
            send_message(peer_id, "📂 Загрузите Excel-файл с двумя столбцами: 'keyword' и 'response'.")
            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    upload_message = event.object.message
                    if upload_message['from_id'] in ADMIN_ID and 'attachments' in upload_message:
                        for attachment in upload_message['attachments']:
                            if attachment['type'] == 'doc' and attachment['doc']['ext'] == 'xlsx':
                                file_url = attachment['doc']['url']
                                handle_file_upload(file_url, peer_id)
                                break
                        break
            continue

        # 👨‍💻 Обработка команды админа /news
        if msg_text == "/news" and (user_id in ADMIN_ID):
            send_message(peer_id, "Введите сообщение для рассылки:")
            awaiting_news_message = True
            continue
            # Если бот ожидает сообщение для рассылки
        if awaiting_news_message and (user_id in ADMIN_ID):
            news_message = msg_text
            members = get_group_members()
            for member in members:
                try:
                    send_message(member, news_message)
                except Exception as e:
                    print(f"Ошибка при отправке сообщения пользователю {member}: {e}")
            send_message(peer_id, "✅ Рассылка завершена.")
            awaiting_news_message = False
            continue

        # 👨‍💻 Обработка команды админа
        if msg_text == "/stats" and user_id in ADMIN_ID:
            stats = get_admin_stats()
            response = "📊 Статистика вопросов:\n"
            for keyword, count, percent in stats:
                response += f"- {keyword}: {count} ({round(percent, 2)}%)\n"
            send_message(peer_id, response)
            continue

        # 🔍 Поиск ключевых слов
        cursor.execute("SELECT keyword, response FROM keywords")
        keywords = cursor.fetchall()
        response = None
        matched_keyword = None
        for keyword, resp in keywords:
            if str(keyword) in msg_text:
                response = resp
                matched_keyword = keyword
                break

        # 📝 Ответ пользователю
        if response:
            send_message(peer_id, response)
            cursor.execute('''
                INSERT INTO message_log (user_id, keyword) 
                VALUES (?, ?)
            ''', (user_id, matched_keyword))
        else:
            send_message(peer_id, "❌ Не понимаю ваш вопрос. Опишите его подробнее.")
        conn.commit()
