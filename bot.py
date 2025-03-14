import datetime
import os
import sqlite3
from datetime import datetime as time
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
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
            last_seen DATETIME
        )
    ''')
    # Добавляем новые столбцы, если их еще нет
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN unanswered_count INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Столбец уже существует
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN waiting_for_help INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Столбец уже существует
    conn.commit()
    print("✅ Таблицы проверены/созданы.")


# 📊 Функция для получения статистики пользователей
def get_user_stats():
    try:
        # Получаем общее количество пользователей
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        # Получаем статистику по возрасту
        cursor.execute('''
            SELECT age, COUNT(*) as count 
            FROM users 
            WHERE age IS NOT NULL 
            GROUP BY age 
            ORDER BY count DESC
        ''')
        age_stats = cursor.fetchall()
        age_percentages = {age: (count / total_users * 100) for age, count in age_stats}

        # Получаем статистику по полу
        cursor.execute('''
            SELECT gender, COUNT(*) as count 
            FROM users 
            WHERE gender IS NOT NULL 
            GROUP BY gender 
            ORDER BY count DESC
        ''')
        gender_stats = cursor.fetchall()
        gender_percentages = {gender: (count / total_users * 100) for gender, count in gender_stats}

        # Получаем последнюю активность пользователей
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
        # Получаем информацию о пользователе из VK API
        user_info = vk.users.get(user_ids=user_id, fields='first_name,last_name,sex,city,bdate,status,last_seen')[0]

        # Извлекаем данные
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        gender = "Мужской" if user_info.get("sex", 0) == 2 else "Женский" if user_info.get("sex",
                                                                                           0) == 1 else "Не указан"
        city = user_info.get('city', {}).get('title', 'Не указан')
        bdate = user_info.get('bdate', '')
        status = user_info.get('status', '')
        last_seen = time.fromtimestamp(user_info.get('last_seen', {}).get('time', 0))

        # Вычисляем возраст (если дата рождения указана)
        age = None
        if bdate:
            try:
                birth_date = time.strptime(bdate, "%d.%m.%Y")
                age = time.now().year - birth_date.year
            except ValueError:
                pass

        # Обновляем или добавляем информацию о пользователе в базу данных
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, first_name, last_name, age, gender, city, status, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, first_name, last_name, age, gender, city, status, last_seen))

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
def send_message(peer_id, text, **kwargs):
    vk.messages.send(
        peer_id=peer_id,
        message=str(text),
        random_id=0,
        **kwargs
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
# 📬 Увеличение счетчика неотвеченных сообщений
def increment_unanswered_count(n,user_id):
    cursor.execute("UPDATE users SET unanswered_count = ? WHERE user_id = ?", (n, user_id,))
    conn.commit()

# 📉 Проверка количества неотвеченных сообщений
def get_unanswered_count(user_id):
    cursor.execute("SELECT unanswered_count FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

# 🚨 Уведомление администраторов и отправка кнопки пользователю
def notify_admins_and_request_help(user_id, peer_id):
    # Устанавливаем флаг ожидания помощи
    cursor.execute("UPDATE users SET waiting_for_help = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

    # Уведомляем администраторов
    cursor.execute("SELECT first_name, last_name FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    if user_info:
        first_name, last_name = user_info
        admin_message = f"Пользователю [id{user_id}|{first_name} {last_name}] нужна помощь."
    else:
        admin_message = f"Пользователю ID: {user_id} нужна помощь."
    for admin in ADMIN_ID:
        send_message(admin, admin_message)

    # Отправляем пользователю сообщение с кнопкой
    keyboard = VkKeyboard(inline=True)
    keyboard.add_callback_button(label="Мне помогли", color=VkKeyboardColor.POSITIVE, payload={"command": "helped"})
    send_message(peer_id, "Администратор скоро вам поможет.", keyboard=keyboard.get_keyboard())

# ✅ Сброс счетчика и флага после помощи
def reset_help_status(user_id):
    cursor.execute("UPDATE users SET unanswered_count = 0, waiting_for_help = 0 WHERE user_id = ?", (user_id,))
    conn.commit()


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

        # Обработка команды /stats_users
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

        # Обработка команды /upload
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

        # Обработка команды /news
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

        # Обработка команды /stats
        if msg_text == "/stats" and user_id in ADMIN_ID:
            stats = get_admin_stats()
            response = "📊 Статистика вопросов:\n"
            for keyword, count, percent in stats:
                response += f"- {keyword}: {count} ({round(percent, 2)}%)\n"
            send_message(peer_id, response)
            continue

        # Поиск ключевых слов
        cursor.execute("SELECT keyword, response FROM keywords")
        keywords = cursor.fetchall()
        response = None
        for keyword, resp in keywords:
            if str(keyword) in msg_text:
                response = resp
                break

        # Ответ пользователю
        if response:
            send_message(peer_id, response)
        else:
            # Проверяем, ожидает ли пользователь помощи
            cursor.execute("SELECT waiting_for_help FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            waiting_for_help = result[0] if result else 0  # Если пользователя нет в базе, считаем 0

            if not waiting_for_help:
                # Увеличиваем счетчик только если бот не ответил
                unanswered_count = get_unanswered_count(user_id) + 1
                increment_unanswered_count(unanswered_count, user_id)
                print(f"Неотвеченных сообщений от {user_id}: {unanswered_count}")

                if unanswered_count >= 5:
                    notify_admins_and_request_help(user_id, peer_id)

            send_message(peer_id, "❌ Не понимаю ваш вопрос. Опишите его подробнее.")

        conn.commit()

    elif event.type == VkBotEventType.MESSAGE_EVENT:
        # Обработка нажатия кнопки "Мне помогли"
        if event.object.payload.get("command") == "helped":
            user_id = event.object.user_id
            cursor.execute("SELECT waiting_for_help FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            if result and result[0] == 1:
                # Сбрасываем счетчик и флаг
                reset_help_status(user_id)
                vk.messages.sendMessageEventAnswer(
                    event_id=event.object.event_id,
                    user_id=event.object.user_id,
                    peer_id=event.object.peer_id,
                    event_data='{"type": "show_snackbar", "text": "Счетчик обнулен"}'
                )
            else:
                vk.messages.sendMessageEventAnswer(
                    event_id=event.object.event_id,
                    user_id=event.object.user_id,
                    peer_id=event.object.peer_id,
                    event_data='{"type": "show_snackbar", "text": "Вы уже получили помощь"}'
                )
            conn.commit()