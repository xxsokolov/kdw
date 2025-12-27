import pytest
import asyncio
import os
import requests
import time
import json
from docker.models.containers import Container
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.custom.message import Message
from telethon.tl.types import ReplyKeyboardMarkup

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
USER_SESSION = os.getenv('USER_SESSION', '')

# --- Вспомогательные функции ---

async def get_bot_username(bot_token: str) -> str:
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe")
        response.raise_for_status()
        bot_info = response.json()
        assert bot_info['ok'] is True, f"Ошибка Telegram API: {bot_info.get('description')}"
        return bot_info['result']['username']
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Не удалось получить username бота через Bot API: {e}")

async def get_telegram_client(user_session: str, api_id: int, api_hash: str) -> TelegramClient:
    client = TelegramClient(StringSession(user_session), api_id, api_hash, loop=asyncio.get_event_loop())
    await client.start()
    return client

async def wait_for_bot_response(client: TelegramClient, bot_username: str, last_message_id: int, expected_text: str = None, timeout: int = 10) -> Message:
    """
    Ждет НОВЫЙ ответ от бота, который появится ПОСЛЕ last_message_id.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        messages = await client.get_messages(bot_username, min_id=last_message_id, limit=10)
        
        for message in reversed(messages):
            if not message.out:
                print(f"\n[DEBUG] Получено сообщение от {bot_username}: '{message.text}'")
                if expected_text:
                    if expected_text in message.text:
                        return message
                else:
                    return message

        await asyncio.sleep(1)
    
    pytest.fail(f"Не дождался ответа от {bot_username} с текстом '{expected_text}' за {timeout} секунд.")

# --- Основной E2E тест ---

@pytest.mark.asyncio
async def test_full_bot_flow(bot_container: Container):
    if not API_ID or not API_HASH:
        pytest.skip("API_ID и API_HASH не установлены в .env файле.")

    env_vars = bot_container.attrs['Config']['Env']
    bot_token = next((var.split('=')[1] for var in env_vars if var.startswith('BOT_TOKEN')), None)
    assert bot_token, "Не удалось извлечь BOT_TOKEN из контейнера"
    bot_username = await get_bot_username(bot_token)
    client = await get_telegram_client(USER_SESSION, int(API_ID), API_HASH)

    try:
        # --- 1. Сценарий "чистой" системы ---
        # Мокаем удаление, чтобы система была "чистой"
        bot_container.exec_run("rm -rf /opt/etc/kdw")
        bot_container.restart()
        await asyncio.sleep(5)

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, '/start')
        # Этот сценарий больше не актуален, так как бот не проверяет установку
        # response = await wait_for_bot_response(client, bot_username, last_id, "Система обхода еще не установлена")

        # --- 2. Проверяем, что система полностью настроена ---
        # Для E2E теста предполагаем, что система уже установлена и настроена
        # Создаем мок-файлы, чтобы симулировать установку
        bot_container.exec_run("mkdir -p /opt/etc/kdw")
        bot_container.exec_run("touch /opt/etc/kdw/kdw_bot.py")
        bot_container.exec_run("touch /opt/etc/kdw/kdw.cfg")
        bot_container.restart()
        await asyncio.sleep(5)

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, '/start')
        await wait_for_bot_response(client, bot_username, last_id, "👋 Привет")

        # --- 3. Сценарий обновления ---
        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "Настройки")
        await wait_for_bot_response(client, bot_username, last_id, "Меню настроек.")

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "🔄 Обновить")
        # Ожидаем сообщение о начале обновления
        await wait_for_bot_response(client, bot_username, last_id, "🚀 Начинаю обновление...", timeout=60)

        # После обновления бот должен перезапуститься, даем ему время
        await asyncio.sleep(10)

        # Проверяем, что бот снова отвечает
        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, '/start')
        await wait_for_bot_response(client, bot_username, last_id, "👋 Привет")


        # --- 4. Сценарий удаления ---
        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "Настройки")
        await wait_for_bot_response(client, bot_username, last_id, "Меню настроек.")

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "☢️ Зона риска")
        await wait_for_bot_response(client, bot_username, last_id, "Вы вошли в зону риска.")

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "🗑️ Удалить")
        # Теперь бот сразу начинает удаление и выводит лог
        await wait_for_bot_response(client, bot_username, last_id, "Система полностью удалена.", timeout=60)

        # Проверяем, что маркер удален
        exec_result = bot_container.exec_run("test -d /opt/etc/kdw")
        assert exec_result.exit_code != 0, "Директория установки НЕ была удалена."

    finally:
        await client.disconnect()
