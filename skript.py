import sqlite3

# Подключение к базе данных
conn = sqlite3.connect('bot_db.sqlite')
cursor = conn.cursor()
#qwert
# Данные для вставки
keywords_data = [
    ('привет', 'Привет! Чем могу помочь?'),
    ('как дела', 'У меня всё отлично, спасибо! А у вас?'),
    ('погода', 'Погоду можно узнать на сайте https://weather.com'),
    ('курс валют', 'Актуальный курс валют можно посмотреть здесь: https://www.cbr.ru/currency_base/daily/'),
    ('расписание', 'Расписание доступно на нашем сайте: https://example.com/schedule'),
    ('контакты', 'Наши контакты: +7 (XXX) XXX-XX-XX, email: example@example.com'),
    ('помощь', 'Я могу помочь с вопросами о погоде, курсе валют, расписании и контактах. Что вас интересует?'),
    ('спасибо', 'Пожалуйста! Обращайтесь, если будут ещё вопросы.'),
    ('цена', 'Цены на наши услуги можно узнать на сайте: https://example.com/prices'),
    ('доставка', 'Доставка осуществляется в течение 2-3 рабочих дней. Подробнее: https://example.com/delivery')
]

# Вставка данных в таблицу
cursor.executemany('INSERT INTO keywords (keyword, response) VALUES (?, ?)', keywords_data)

# Сохранение изменений
conn.commit()

# Закрытие соединения
conn.close()

print("✅ Данные успешно добавлены в таблицу keywords.")