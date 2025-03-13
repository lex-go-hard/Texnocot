import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import os
#qwertyuiui
# Загрузка переменных окружения
load_dotenv("keys.env")
GROUP_TOKEN = os.getenv('GROUP_TOKEN')
GROUP_ID = int(os.getenv('GROUP_ID'))
ADMIN_ID = int(os.getenv('ADMIN_ID'))

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


# 🛠️ Основной цикл обработки событий
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        message = event.object.message
        msg_text = message['text'].lower()
        user_id = message['from_id']
        peer_id = message['peer_id']


        print(f"📩 Сообщение: '{msg_text}' от user_id: {user_id} | peer_id: {peer_id}")

        # 👨‍💻 Обработка команды админа
        if msg_text == "/stats" and user_id == ADMIN_ID:
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
