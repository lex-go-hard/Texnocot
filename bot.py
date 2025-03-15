<<<<<<< HEAD
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import sqlite3
from dotenv import load_dotenv
import os
import json

# Загрузка переменных окружения
load_dotenv("keys.env")
GROUP_TOKEN = os.getenv('GROUP_TOKEN')
GROUP_ID = int(os.getenv('GROUP_ID'))  # Положительный ID группы
ADMIN_ID = int(os.getenv('ADMIN_ID'))
ADMIN_ID2 = int(os.getenv('ADMIN_ID2'))
USER_TOKEN = os.getenv('USER_TOKEN')  # Токен пользователя

# Подключение к базе данных
conn = sqlite3.connect('bot_db.sqlite')
cursor = conn.cursor()


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
    conn.commit()
    print("✅ Таблицы проверены/созданы.")


# 📄 Создание таблиц при запуске
create_tables()

# Инициализация VK API
vk_session = vk_api.VkApi(token=GROUP_TOKEN)
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
vk = vk_session.get_api()

# Инициализация пользовательского VK API для создания чата и опроса
try:
    user_vk_session = vk_api.VkApi(token=USER_TOKEN)
    user_vk = user_vk_session.get_api()
except vk_api.exceptions.ApiError as e:
    print(f"Ошибка инициализации USER_TOKEN: {e}")
    raise SystemExit("Проверьте USER_TOKEN в keys.env и убедитесь, что он действителен.")


# 📩 Функция для отправки сообщений
def send_message(peer_id, text):
    vk.messages.send(
        peer_id=peer_id,
        message=text,
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


# 📨 Функция для получения списка подписчиков
def get_group_members():
    members = vk.groups.getMembers(group_id=GROUP_ID)['items']
    return members


# 🆕 Функция для получения списка администраторов группы
def get_group_admins():
    try:
        admins = vk.groups.getMembers(group_id=GROUP_ID, filter='managers')['items']
        print(f"Полученные администраторы: {admins}")  # Отладка
        return [admin['id'] for admin in admins]
    except Exception as e:
        print(f"Ошибка в get_group_admins: {e}")
        return None


# 🆕 Функция для создания чата сообщества с администраторами
def create_admin_chat(chat_title):
    try:
        # Получаем список администраторов
        admins = get_group_admins()
        if admins is None or not admins:
            return None, "Не удалось получить список администраторов или список пуст."

        # Получаем ID бота через USER_TOKEN
        bot_info = user_vk_session.method('users.get')
        if not bot_info or len(bot_info) == 0:
            return None, "Не удалось определить ID бота через USER_TOKEN."
        bot_id = bot_info[0]['id']
        print(f"ID бота: {bot_id}")  # Отладка

        # Исключаем бота из списка администраторов
        admin_ids = [admin_id for admin_id in admins if admin_id != bot_id]
        print(f"Администраторы после фильтрации: {admin_ids}")  # Отладка

        if not admin_ids:
            return None, "Нет администраторов для добавления в чат (бот исключён)."

        # Создаём чат с администраторами через пользовательский токен
        chat_id = user_vk.messages.createChat(
            user_ids=admin_ids[:10],  # Ограничение метода — до 10 участников при создании
            title=chat_title
        )

        # Если администраторов больше 10, добавляем оставшихся
        if len(admin_ids) > 10:
            remaining_admins = admin_ids[10:50]  # Ограничение до 50 за раз
            vk.messages.addChatUsers(
                chat_id=chat_id,
                user_ids=remaining_admins
            )

        return chat_id, admin_ids
    except vk_api.exceptions.ApiError as e:
        return None, f"Ошибка VK API: {e}"
    except Exception as e:
        return None, f"Неизвестная ошибка: {e}"


# Флаг для ожидания сообщения для рассылки
awaiting_news_message = False

# Флаги для создания опроса
awaiting_poll_question = False
awaiting_poll_options = False
awaiting_poll_settings = False
poll_question = ""
poll_options = []

# Флаги для команды /group
awaiting_chat_title = False

# 🛠️ Основной цикл обработки событий
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        message = event.object.message
        msg_text = message['text'].lower()
        user_id = message['from_id']
        peer_id = message['peer_id']

        print(f"📩 Сообщение: '{msg_text}' от user_id: {user_id} | peer_id: {peer_id}")

        # 👨‍💻 Обработка команды админа /stats
        if msg_text == "/stats" and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            stats = get_admin_stats()
            response = "📊 Статистика вопросов:\n"
            for keyword, count, percent in stats:
                response += f"- {keyword}: {count} ({round(percent, 2)}%)\n"
            send_message(peer_id, response)
            continue

        # 👨‍💻 Обработка команды админа /group
        if msg_text == "/group" and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            send_message(peer_id, "Введите название нового:")
            awaiting_chat_title = True
            continue

        # Если бот ожидает название чата для /group
        if awaiting_chat_title and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            chat_title = message['text']
            chat_id, result = create_admin_chat(chat_title)
            if chat_id:
                admin_ids = result
                admin_list = "\n".join([f"- {aid}" for aid in admin_ids])
                send_message(peer_id, f"✅ Чат '{chat_title}' создан (ID: {chat_id + 2000000000}).\n"
                                      f"А:\n{admin_list}")
            else:
                send_message(peer_id, f"❌ Ошибка при создании чата: {result}")
            awaiting_chat_title = False
            continue

        # 👨‍💻 Обработка команды админа /poll
        if msg_text == "/poll" and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            send_message(peer_id, "Введите вопрос для опроса:")
            awaiting_poll_question = True
            continue

        # Если бот ожидает вопрос для опроса
        if awaiting_poll_question and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            poll_question = msg_text
            send_message(peer_id, "Введите варианты ответа в формате '1. ответ; 2. ответ':")
            awaiting_poll_question = False
            awaiting_poll_options = True
            continue

        # Если бот ожидает варианты ответа
        if awaiting_poll_options and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            poll_options = [option.strip() for option in msg_text.split(';')]
            send_message(peer_id, "Введите характеристики опроса (цифры через пробел):\n"
                                  "1. Анонимный опрос\n"
                                  "2. Выбор нескольких вариантов\n"
                                  "3. Запретить отмену голоса\n"
                                  "Если таких характеристик нет, напишите 0 0 0.")
            awaiting_poll_options = False
            awaiting_poll_settings = True
            continue

        # Если бот ожидает характеристики опроса
        if awaiting_poll_settings and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            settings = msg_text.split(" ")
            is_anonymous = '1' in settings
            is_multiple = '2' in settings
            disable_unvote = '3' in settings

            try:
                # Создание JSON-строки для вариантов ответов
                answers_json = json.dumps([option for option in poll_options], ensure_ascii=False)

                # Создание опроса через user-token
                if settings and settings != ["0", "0", "0"]:
                    poll = user_vk.polls.create(
                        question=poll_question,
                        add_answers=answers_json,
                        owner_id=ADMIN_ID,
                        is_anonymous=is_anonymous,
                        is_multiple=is_multiple,
                        disable_unvote=disable_unvote
                    )
                else:
                    poll = user_vk.polls.create(
                        question=poll_question,
                        add_answers=answers_json,
                        owner_id=ADMIN_ID
                    )

                # Создание поста с опросом в группе
                post = vk.wall.post(
                    owner_id=-GROUP_ID,
                    message="Пожалуйста, пройдите опрос!",
                    attachments=f"poll{poll['owner_id']}_{poll['id']}"
                )

                send_message(peer_id, "✅ Опрос создан и опубликован на стене сообщества.")
            except Exception as e:
                send_message(peer_id, f"❌ Ошибка при создании опроса: {e}")
                print(f"Ошибка при создании опроса: {e}")

            awaiting_poll_settings = False
            poll_question, poll_options = "", []
            continue

        # 🔍 Поиск ключевых слов
        cursor.execute("SELECT keyword, response FROM keywords")
        keywords = cursor.fetchall()
        response = None
        matched_keyword = None

        for keyword, resp in keywords:
            if keyword in msg_text:
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
=======
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
>>>>>>> origin/master
