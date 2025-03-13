import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv("keys.env")
GROUP_TOKEN = os.getenv('GROUP_TOKEN')
GROUP_ID = int((os.getenv('GROUP_ID')))
ADMIN_ID = int(os.getenv('ADMIN_ID'))
ADMIN_ID2 = int(os.getenv('ADMIN_ID2'))

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

# Подключение к базе данных
conn = sqlite3.connect('bot_db.sqlite')
cursor = conn.cursor()

# 📄 Создание таблиц при запуске
create_tables()

# Инициализация VK API
vk_session = vk_api.VkApi(token=GROUP_TOKEN)
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
vk = vk_session.get_api()

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

# Флаг для ожидания сообщения для рассылки
awaiting_news_message = False

# Флаги для создания опроса
awaiting_poll_question = False
awaiting_poll_options = False
awaiting_poll_settings = False
poll_question = ""
poll_options = []

# 🛠️ Основной цикл обработки событий
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        message = event.object.message
        msg_text = message['text'].lower()
        user_id = message['from_id']
        peer_id = message['peer_id']

        print(f"📩 Сообщение: '{msg_text}' от user_id: {user_id} | peer_id: {peer_id}")

        # 👨‍💻 Обработка команды админа /stats
        if msg_text == "/stats" and user_id == ADMIN_ID:
            stats = get_admin_stats()
            response = "📊 Статистика вопросов:\n"
            for keyword, count, percent in stats:
                response += f"- {keyword}: {count} ({round(percent, 2)}%)\n"
            send_message(peer_id, response)
            continue

        # 👨‍💻 Обработка команды админа /news
        if msg_text == "/news" and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            send_message(peer_id, "Введите сообщение для рассылки:")
            awaiting_news_message = True
            continue

        # Если бот ожидает сообщение для рассылки
        if awaiting_news_message and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
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
                                 "Если таких характеристик нет, напишите 0.")
            awaiting_poll_options = False
            awaiting_poll_settings = True
            continue

        # Если бот ожидает характеристики опроса
        if awaiting_poll_settings and (user_id == ADMIN_ID or user_id == ADMIN_ID2):
            settings = msg_text.split()
            is_anonymous = '1' in settings
            is_multiple = '2' in settings
            disable_unvote = '3' in settings

            try:
                # Создание опроса
                poll = vk.polls.create(
                    question=poll_question,
                    add_answers=poll_options,
                    owner_id=-GROUP_ID,  # Отрицательный ID для группы
                    is_anonymous=is_anonymous,
                    is_multiple=is_multiple,
                    disable_unvote=disable_unvote
                )

                # Создание поста с опросом
                post = vk.wall.post(
                    owner_id=-GROUP_ID,  # Отрицательный ID для группы
                    message="Пожалуйста пройдите опрос!",
                    attachments=f"poll{poll['owner_id']}_{poll['id']}"
                )

                send_message(peer_id, "✅ Опрос создан и опубликован на стене сообщества.")
            except Exception as e:
                send_message(peer_id, f"❌ Ошибка при создании опроса: {e}")

            awaiting_poll_settings = False
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