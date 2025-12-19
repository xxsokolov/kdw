import pytest
import asyncio
import os
import requests
from docker.models.containers import Container
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
USER_SESSION = os.getenv('USER_SESSION', '')

@pytest.mark.asyncio
async def test_bot_container_is_running(bot_container: Container):
    assert bot_container is not None
    assert bot_container.status == 'running'
    logs = bot_container.logs().decode('utf-8')
    assert "KDW Bot запущен" in logs

@pytest.mark.asyncio
async def test_start_command_for_new_install(bot_container: Container):
    if not API_ID or not API_HASH:
        pytest.skip("API_ID и API_HASH не установлены в .env файле. Пропускаю E2E тест.")

    env_vars = bot_container.attrs['Config']['Env']
    bot_token = next((var.split('=')[1] for var in env_vars if var.startswith('BOT_TOKEN')), None)
    assert bot_token, "Не удалось извлечь BOT_TOKEN из контейнера"

    # Получаем username бота через Telegram Bot API
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe")
        response.raise_for_status()
        bot_info = response.json()
        assert bot_info['ok'] is True, f"Ошибка Telegram API: {bot_info.get('description')}"
        bot_username = bot_info['result']['username']
        assert bot_username, "Не удалось получить username бота из getMe."
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Не удалось получить username бота через Bot API: {e}")

    client = TelegramClient(StringSession(USER_SESSION), int(API_ID), API_HASH, loop=asyncio.get_event_loop())

    try:
        await client.start()
        
        # Если мы зашли в первый раз (интерактивно), выводим сессионную строку
        if not USER_SESSION:
            session_string = client.session.save()
            print(f"\n\n\n!!! ВАЖНО !!!\n"
                  f"Вы успешно вошли. Чтобы автоматизировать вход в будущем,\n"
                  f"добавьте следующую строку в ваш docker/.env файл:\n\n"
                  f"USER_SESSION={session_string}\n\n")
            await asyncio.to_thread(input, "Нажмите Enter, чтобы продолжить тестирование...")

        # Отправляем команду /start нашему боту по его username
        await client.send_message(bot_username, '/start')

        await asyncio.sleep(2)
        
        last_message = await client.get_messages(bot_username, limit=1)
        assert last_message, "Бот не ответил на команду /start"

        response_text = last_message[0].text
        assert "Система обхода еще не установлена" in response_text
    finally:
        await client.disconnect()
