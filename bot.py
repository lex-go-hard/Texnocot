import json
import os
import sqlite3
from datetime import datetime as time

import pandas as pd
import vk_api
from dotenv import load_dotenv
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# Загрузка переменных окружения
load_dotenv("keys.env")
GROUP_TOKEN = os.getenv('GROUP_TOKEN')
GROUP_ID = int(os.getenv('GROUP_ID'))
ADMIN_ID = list(map(int, os.getenv('ADMIN_ID').split(",")))

# Подключение к базе данных
conn = sqlite3.connect('bot_db1.sqlite')
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
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            age INTEGER,
            gender TEXT,
            city TEXT,
            status TEXT,
            last_seen DATETIME,
            message_count INTEGER DEFAULT 0,
            is_ignored INTEGER DEFAULT 0
        )
    ''')
    # Добавляем колонку is_ignored, если она еще не существует
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_ignored INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Колонка уже существует
    conn.commit()
    print("✅ Таблицы проверены/созданы.")


# 📊 Функция для получения статистики пользователей
def get_user_stats():
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute('''
            SELECT age, COUNT(*) as count 
            FROM users 
            WHERE age IS NOT NULL 
            GROUP BY age 
            ORDER BY count DESC
        ''')
        age_stats = cursor.fetchall()
        age_percentages = {age: (count / total_users * 100) for age, count in age_stats}
        cursor.execute('''
            SELECT gender, COUNT(*) as count 
            FROM users 
            WHERE gender IS NOT NULL 
            GROUP BY gender 
            ORDER BY count DESC
        ''')
        gender_stats = cursor.fetchall()
        gender_percentages = {gender: (count / total_users * 100) for gender, count in gender_stats}
        cursor.execute('''
            SELECT user_id, first_name, last_name, age, gender, city, status, last_seen 
            FROM users 
            ORDER BY last_seen DESC
        ''')
        user_activity_stats = cursor.fetchall()
        return {
            "total_users": total_users,
            "age_percentages": age_percentages,
            "gender_percentages": gender_percentages,
            "user_activity_stats": user_activity_stats
        }
    except Exception as e:
        print(f"Ошибка при получении статистики пользователей: {e}")
        return None


# Обновление информации о пользователе
def update_user_info(user_id):
    try:
        user_info = vk.users.get(user_ids=user_id, fields='first_name,last_name,sex,city,bdate,status,last_seen')[0]
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        gender = "Мужской" if user_info.get("sex", 0) == 2 else "Женский" if user_info.get("sex",
                                                                                           0) == 1 else "Не указан"
        city = user_info.get('city', {}).get('title', 'Не указан')
        bdate = user_info.get('bdate', '')
        status = user_info.get('status', '')
        last_seen = time.fromtimestamp(user_info.get('last_seen', {}).get('time', 0))
        age = None
        if bdate:
            try:
                birth_date = time.strptime(bdate, "%d.%m.%Y")
                age = time.now().year - birth_date.year
            except ValueError:
                pass
        cursor.execute('''
            UPDATE users SET first_name=?, last_name=?, age=?, gender=?, city=?, status=?, last_seen=?
            WHERE user_id=?
        ''', (first_name, last_name, age, gender, city, status, last_seen, user_id))
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO users (user_id, first_name, last_name, age, gender, city, status, last_seen, message_count, is_ignored)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''', (user_id, first_name, last_name, age, gender, city, status, last_seen))
        conn.commit()
    except Exception as e:
        print(f"Ошибка при обновлении информации о пользователе: {e}")


# 📥 Обработчик загрузки файла
def handle_file_upload(file_url, peer_id):
    try:
        df = pd.read_excel(file_url)
        if 'keyword' not in df.columns or 'response' not in df.columns:
            send_message(peer_id, "❌ Ошибка! Таблица должна содержать столбцы: 'keyword' и 'response'.")
            return
        df = df[['keyword', 'response']].drop_duplicates().dropna()
        cursor.execute("SELECT keyword FROM keywords")
        existing_keywords = {row[0] for row in cursor.fetchall()}
        new_data = df[~df['keyword'].isin(existing_keywords)]
        for _, row in new_data.iterrows():
            cursor.execute("INSERT INTO keywords (keyword, response) VALUES (?, ?)", (row['keyword'], row['response']))
        conn.commit()
        send_message(peer_id, "✅ Таблица успешно загружена!")
    except Exception as e:
        send_message(peer_id, f"❌ Ошибка при обработке файла: {str(e)}")


# 📩 Функция для отправки сообщений
def send_message(peer_id, text, keyboard=None):
    params = {
        'peer_id': peer_id,
        'message': str(text),
        'random_id': 0
    }
    if keyboard:
        params['keyboard'] = keyboard
    vk.messages.send(**params)


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


def can_send_message(user_id):
    try:
        response = vk.messages.isMessagesFromGroupAllowed(group_id=GROUP_ID, user_id=user_id)
        return response['is_allowed']
    except Exception as e:
        print(f"Ошибка при проверке разрешения для user_id {user_id}: {e}")
        return False


# Инициализация VK API
vk_session = vk_api.VkApi(token=GROUP_TOKEN)
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
vk = vk_session.get_api()
create_tables()

# 🛠️ Основной цикл обработки событий
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        message = event.object.message
        msg_text = message['text'].lower()
        user_id = message['from_id']
        peer_id = message['peer_id']
        print(f"📩 Сообщение: '{msg_text}' от user_id: {user_id} | peer_id: {peer_id}")

        # Обновляем информацию о пользователе
        update_user_info(user_id)

        # Проверяем payload ДО проверки игнора
        if 'payload' in message:
            try:
                payload = json.loads(message['payload'])
                if payload.get('action') == "reset_counter":
                    # Сбрасываем счетчик и статус игнора
                    cursor.execute("UPDATE users SET message_count = 0, is_ignored = 0 WHERE user_id = ?", (user_id,))
                    conn.commit()

                    # Получаем информацию о пользователе
                    cursor.execute("SELECT first_name, last_name FROM users WHERE user_id = ?", (user_id,))
                    user_info = cursor.fetchone()
                    if user_info:
                        first_name, last_name = user_info
                        # Уведомляем админов
                        for admin_id in ADMIN_ID:
                            if can_send_message(admin_id):
                                send_message(
                                    admin_id,
                                    f"Пользователю [id{user_id}|{first_name} {last_name}] уже помогли."
                                )
                        send_message(peer_id, "✅ Ваш счетчик сообщений был сброшен. Спасибо за обращение!")
                    continue

                elif payload.get('action') == "respond":
                    user_to_ignore = payload.get('user_id')
                    cursor.execute("UPDATE users SET is_ignored = 1 WHERE user_id = ?", (user_to_ignore,))
                    conn.commit()
                    send_message(peer_id,
                                 f"Вы откликнулись на запрос пользователя [id{user_to_ignore}|]. Бот будет игнорировать его сообщения.")
                    continue
            except json.JSONDecodeError:
                pass

        # Проверяем, находится ли пользователь в режиме игнора
        cursor.execute("SELECT is_ignored FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        is_ignored = result[0] if result else 0

        if is_ignored:
            print(f"Сообщение от user_id {user_id} игнорируется.")
            keyboard = VkKeyboard(one_time=True)
            keyboard.add_button('Я получил помощь', color=VkKeyboardColor.POSITIVE,
                                payload=json.dumps({"action": "reset_counter"}))
            send_message(
                peer_id,text="заготовленные ответы игнорируются",
                keyboard=keyboard.get_keyboard()
            )
            continue

        # Обработка существующих команд администратора
        if msg_text == "/stats_users" and user_id in ADMIN_ID:
            stats = get_user_stats()
            if stats:
                response = "📊 Статистика пользователей:\n"
                response += f"👥 Всего пользователей: {stats['total_users']}\n\n"
                response += "📈 Возрастные группы:\n"
                for age, percent in stats['age_percentages'].items():
                    response += f"- {age} лет: {round(percent, 2)}%\n"
                response += "\n👫 Пол:\n"
                for gender, percent in stats['gender_percentages'].items():
                    response += f"- {gender}: {round(percent, 2)}%\n"
                response += "\n🕒 Последняя активность пользователей:\n"
                for user in stats['user_activity_stats'][:10]:
                    user_id, first_name, last_name, age, gender, city, status, last_seen = user
                    response += (
                        f"👤 {first_name} {last_name} (ID: {user_id})\n"
                        f"- Последняя активность: {last_seen}\n\n"
                    )
                send_message(peer_id, response)
            else:
                send_message(peer_id, "❌ Не удалось получить статистику.")
            continue

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

        if msg_text == "/news" and user_id in ADMIN_ID:
            send_message(peer_id, "Введите сообщение для рассылки:")
            awaiting_news_message = True
            continue

        if awaiting_news_message and user_id in ADMIN_ID:
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

        if msg_text == "/stats" and user_id in ADMIN_ID:
            stats = get_admin_stats()
            response = "📊 Статистика вопросов:\n"
            for keyword, count, percent in stats:
                response += f"- {keyword}: {count} ({round(percent, 2)}%)\n"
            send_message(peer_id, response)
            continue

        # Поиск ключевых слов и отправка ответа
        cursor.execute("SELECT keyword, response FROM keywords")
        keywords = cursor.fetchall()
        response = None
        for keyword, resp in keywords:
            if str(keyword) in msg_text:
                response = resp
                break

        if response:
            send_message(peer_id, response)
        else:
            send_message(peer_id, "❌ Не понимаю ваш вопрос. Опишите его подробнее.")
            cursor.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id = ?", (user_id,))

        cursor.execute("SELECT message_count FROM users WHERE user_id = ?", (user_id,))
        message_count = cursor.fetchone()[0]

        # Если пользователь отправил 5 сообщений, уведомляем админов и отправляем кнопку
        if message_count == 5:
            for admin_id in ADMIN_ID:
                if can_send_message(admin_id):
                    cursor.execute("SELECT first_name, last_name FROM users WHERE user_id = ?", (user_id,))
                    first_name, last_name = cursor.fetchone()
                    mention = f"[id{user_id}|{first_name} {last_name}]"
                    message_text = f"Пользователь {mention} отправил 5 сообщений и возможно нуждается в помощи."
                    keyboard = VkKeyboard(one_time=True)
                    keyboard.add_button('Откликнуться', color=VkKeyboardColor.PRIMARY,
                                        payload={"action": "respond", "user_id": user_id})
                    send_message(admin_id, message_text, keyboard=keyboard.get_keyboard())
                else:
                    print(f"Невозможно отправить сообщение администратору {admin_id}: нет разрешения")
        if message_count >= 5:
            keyboard = VkKeyboard(one_time=True)
            keyboard.add_button('Я получил помощь', color=VkKeyboardColor.POSITIVE, payload={"action": "reset_counter"})
            send_message(peer_id,
                         "Администратор был уведомлен о вашей проблеме. Как только вы получите помощь, нажмите кнопку ниже.",
                         keyboard=keyboard.get_keyboard())

        conn.commit()
