import time
import tensorflow as tf
from tensorflow.keras.preprocessing import image
import numpy as np
import os
import hashlib
import telebot
import flask

# Конфигурация
API_TOKEN = ''  # Укажите ваш токен бота
APP_HOST = '127.0.0.1'
APP_PORT = 8444  # Порт должен быть числом, а не строкой
WEB_HOOK_URL = 'https://your-ngrok-url.ngrok-free.app'  # Укажите ваш URL для вебхука

# Инициализация бота и Flask-приложения
bot = telebot.TeleBot(API_TOKEN)
app = flask.Flask(__name__)

# Проверка и создание директории для изображений
if not os.path.exists('content'):
    os.makedirs('content')


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Используй /register для регистрации или /login для входа.")


# Обработчик команды /register
@bot.message_handler(commands=['register'])
def register_user(message):
    chat_id = message.chat.id
    with open('users.txt', 'r') as f:
        for line in f:
            if str(chat_id) in line:
                bot.send_message(chat_id, "Ты уже зарегистрирован!")
                return
    bot.send_message(chat_id, "Введи пароль для регистрации:")
    bot.register_next_step_handler(message, reg_usr)


# Функция для завершения регистрации
def reg_usr(message):
    chat_id = message.chat.id
    password_hash = hashlib.md5(message.text.encode()).hexdigest()
    with open('users.txt', 'a') as f:
        f.write(f"[{chat_id}, 0, {password_hash}]\n")
    bot.send_message(chat_id, "Регистрация успешна! Теперь войди с помощью /login")


# Обработчик команды /login
@bot.message_handler(commands=['login'])
def login_user(message):
    chat_id = message.chat.id
    with open('users.txt', 'r') as f:
        for line in f:
            if str(chat_id) in line:
                if ', 1,' in line:
                    bot.send_message(chat_id, "Ты уже вошёл!")
                else:
                    bot.send_message(chat_id, "Введи пароль для входа:")
                    bot.register_next_step_handler(message, log_usr)
                return
    bot.send_message(chat_id, "Сначала зарегистрируйся с помощью /register")


# Функция для завершения входа
def log_usr(message):
    chat_id = message.chat.id
    password_hash = hashlib.md5(message.text.encode()).hexdigest()

    with open('users.txt', 'r') as f:
        content = f.read()

    with open('users.txt', 'r') as f:
        for line in f:
            if str(chat_id) in line:
                if password_hash in line:
                    new_content = content.replace(f"{chat_id}, 0", f"{chat_id}, 1")
                    with open('users.txt', 'w') as fw:
                        fw.write(new_content)
                    bot.send_message(chat_id, "Вход успешен! Теперь можешь использовать /predict")
                else:
                    bot.send_message(chat_id, "Неверный пароль!")
                return


# Обработчик команды /predict
@bot.message_handler(commands=['predict'])
def predict_image(message):
    chat_id = message.chat.id
    with open('users.txt', 'r') as f:
        for line in f:
            if str(chat_id) in line and ', 1,' in line:
                bot.send_message(chat_id, "Пришли фотку для классификации.")
                bot.register_next_step_handler(message, handle_image)
                return
    bot.send_message(chat_id, "Сначала войди с помощью /login")


# Обработчик изображений
# Обработчик изображений
@bot.message_handler(content_types=['photo'])
def handle_image(message):
    try:
        chat_id = message.chat.id
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Сохранение изображения
        file_path = f"content/{file_id}.jpg"
        with open(file_path, "wb") as user_image:
            user_image.write(downloaded_file)

        # Проверка наличия модели
        model_path = 'model.h5'
        if not os.path.exists(model_path):
            bot.send_message(chat_id, "Ошибка: Модель 'model.h5' не найдена!")
            return

        # Загрузка модели
        model = tf.keras.models.load_model(model_path)

        # Обработка изображения
        img = image.load_img(file_path, target_size=(300, 300))
        x = image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = x / 255.0  # Нормализация изображения

        # Предсказание
        classes = model.predict(x, batch_size=1)
        prediction = classes[0][0]

        # Отправка результата
        if prediction < 0.5:
            bot.send_message(chat_id, "Это, похоже, крокодил!")
        else:
            bot.send_message(chat_id, "Это, похоже, человек!")

        # Удаление временного файла
        os.remove(file_path)

    except Exception as e:
        bot.send_message(chat_id, f"Ошибка при обработке изображения: {str(e)}")

# Обработчик команды /logout
@bot.message_handler(commands=['logout'])
def logout_user(message):
    chat_id = message.chat.id
    with open('users.txt', 'r') as f:
        content = f.read()

    if str(chat_id) not in content:
        bot.send_message(chat_id, "Ты не зарегистрирован! Используй /register")
        return

    with open('users.txt', 'r') as f:
        for line in f:
            if str(chat_id) in line:
                if ", 1," in line:
                    new_content = content.replace(f"{chat_id}, 1", f"{chat_id}, 0")
                    with open('users.txt', 'w') as fw:
                        fw.write(new_content)
                    bot.send_message(chat_id, "Ты вышел из аккаунта!")
                else:
                    bot.send_message(chat_id, "Ты не вошёл в аккаунт! Используй /login")
                return


# Вебхук для Flask
@app.route('/', methods=['POST'])
def webhook():
    if flask.request.headers.get('content-type') == 'application/json':
        json_string = flask.request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        flask.abort(403)


# Запуск бота
if __name__ == '__main__':
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEB_HOOK_URL)
    app.run(host=APP_HOST, port=APP_PORT, debug=True)