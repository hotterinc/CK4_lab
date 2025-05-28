import os
import json
import numpy as np
from io import BytesIO
import asyncio
import tensorflow as tf
from tensorflow.keras.preprocessing import image
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Router
from aiogram.filters import Command
from aiogram import F
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import ssl
from uuid import uuid4

# Load user data
try:
    with open('users.json', 'r') as f:
        user_data = json.load(f)
except FileNotFoundError:
    user_data = {}

# Load the model
model = tf.keras.models.load_model('model.h5')

# Bot setup
TOKEN = os.getenv('BOT_TOKEN')  # Use environment variable for token
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST')  # Replace with your domain
WEBHOOK_PATH = f'/webhook/{uuid4()}'  # Unique webhook path for security
WEBHOOK_URL = f'{WEBHOOK_HOST}{WEBHOOK_PATH}'
WEBAPP_HOST = '0.0.0.0'  # Listen on all interfaces
WEBAPP_PORT = int(os.getenv('PORT'))  # Default to 8443 for HTTPS

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Define states
class UserStates(StatesGroup):
    REGISTERING = State()
    LOGGING_IN = State()
    WAITING_FOR_IMAGE = State()

# /register command
@router.message(Command(commands=['register']))
async def register(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    if chat_id in user_data:
        await message.reply("You are already registered.")
    else:
        await state.set_state(UserStates.REGISTERING)
        await message.reply("Enter a password to register.")

@router.message(UserStates.REGISTERING)
async def set_password(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    password = message.text
    user_data[chat_id] = {'password': password, 'logged_in': False}
    with open('users.json', 'w') as f:
        json.dump(user_data, f)
    await state.clear()
    await message.reply("Registration successful. Use /login to log in.")

# /login command
@router.message(Command(commands=['login']))
async def login(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    if chat_id not in user_data:
        await message.reply("You are not registered. Use /register first.")
    else:
        await state.set_state(UserStates.LOGGING_IN)
        await message.reply("Enter your password to log in.")

@router.message(UserStates.LOGGING_IN)
async def check_password(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    password = message.text
    if user_data[chat_id]['password'] == password:
        user_data[chat_id]['logged_in'] = True
        with open('users.json', 'w') as f:
            json.dump(user_data, f)
        await state.clear()
        await message.reply("Login successful. You can now use /predict.")
    else:
        await message.reply("Incorrect password. Try again.")

# /logout command
@router.message(Command(commands=['logout']))
async def logout(message: types.Message):
    chat_id = message.chat.id
    if chat_id in user_data:
        user_data[chat_id]['logged_in'] = False
        with open('users.json', 'w') as f:
            json.dump(user_data, f)
        await message.reply("You have logged out.")
    else:
        await message.reply("You are not registered.")

# /predict command
@router.message(Command(commands=['predict']))
async def predict(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    if chat_id not in user_data or not user_data[chat_id]['logged_in']:
        await message.reply("Please log in first. Use /login.")
    else:
        await state.set_state(UserStates.WAITING_FOR_IMAGE)
        await message.reply("Send an image for classification.")

@router.message(F.photo)
async def classify_image(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file = await bot.download_file(file_info.file_path)
    img = image.load_img(BytesIO(file.read()), target_size=(200, 200))
    x = image.img_to_array(img)
    x = np.expand_dims(x, axis=0)
    x = x / 255.0
    prediction = model.predict(x)[0][0]
    result = "Human" if prediction < 0.5 else "Crocodile"
    await message.reply(f"The image is classified as: {result}")
    await state.clear()

@router.message(UserStates.WAITING_FOR_IMAGE)
async def invalid_input(message: types.Message):
    await message.reply("Please send an image.")

# Webhook setup
async def on_startup():
    # Set webhook
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    print(f"Webhook set to {WEBHOOK_URL}")

async def on_shutdown():
    # Remove webhook and close sessions
    await bot.delete_webhook()
    await bot.session.close()
    await storage.close()
    await dp.fsm.storage.close()
    print("Webhook removed and bot stopped")

# Main function to start the webhook server
def main():
    app = web.Application()
    webhook_request_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=str(uuid4()),  # Generate a secret token for security
    )
    webhook_request_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # SSL context for HTTPS
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_context.load_cert_chain(
        certfile='path/to/cert.pem',  # Replace with path to your SSL certificate
        keyfile='path/to/key.pem'     # Replace with path to your SSL private key
    )

    # Start the webhook server
    web.run_app(
        app,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
        ssl_context=ssl_context,
        handle_signals=True,
        loop=asyncio.get_event_loop()
    )

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")