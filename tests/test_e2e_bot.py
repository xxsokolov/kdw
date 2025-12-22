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
            # Игнорируем свои же сообщения, ждем только ответ от бота
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
        # --- 1. Сценарий "чистой" установки ---
        bot_container.exec_run("rm -f /etc/init.d/S99unblock")
        bot_container.restart()
        await asyncio.sleep(5)

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, '/start')
        response = await wait_for_bot_response(client, bot_username, last_id, "Система обхода еще не установлена")
        assert isinstance(response.reply_markup, ReplyKeyboardMarkup)
        assert any(b.text == "🚀 Установить систему обхода" for row in response.reply_markup.rows for b in row.buttons)

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "🚀 Установить систему обхода")
        response = await wait_for_bot_response(client, bot_username, last_id, "Установка завершена!", timeout=60)
        assert "Пожалуйста, перезапустите бота командой /start." in response.text
        exec_result = bot_container.exec_run("test -f /etc/init.d/S99unblock")
        assert exec_result.exit_code == 0, "Файл-маркер установки не был создан."

        # --- 2. Сценарий обновления ключа Shadowsocks ---
        bot_container.restart()
        await asyncio.sleep(5)
        
        script_content = '#!/bin/sh\\necho "Restarting Shadowsocks..."'
        create_script_cmd = f"sh -c 'printf \"{script_content}\" > /etc/init.d/S22shadowsocks'"
        bot_container.exec_run(create_script_cmd)
        bot_container.exec_run("chmod +x /etc/init.d/S22shadowsocks")

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, '/start')
        await wait_for_bot_response(client, bot_username, last_id, "Система обхода уже установлена")

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "Система обхода")
        await wait_for_bot_response(client, bot_username, last_id, "Меню управления системой обхода.")

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "Ключи")
        await wait_for_bot_response(client, bot_username, last_id, "Меню управления ключами.")

        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "Shadowsocks")
        await wait_for_bot_response(client, bot_username, last_id, "Пожалуйста, отправьте ключ в формате ss://...")

        ss_key = "ss://YWVzLTI1Ni1nY206dGVzdDEyMzRA@example.com:8443#Test-Server"
        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, ss_key)
        response = await wait_for_bot_response(client, bot_username, last_id, "успешно обновлена и служба перезапущена", timeout=20)
        assert "Test-Server.json" in response.text

        file_path = "/opt/etc/shadowsocks/Test-Server.json"
        exec_result = bot_container.exec_run(f"test -f {file_path}")
        assert exec_result.exit_code == 0, f"Файл конфига {file_path} не был создан."

        # --- 3. Сценарий проверки статуса служб ---
        # ВОЗВРАЩАЕМСЯ в предыдущее меню
        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "🔙 Назад")
        await wait_for_bot_response(client, bot_username, last_id, "Меню управления системой обхода.")

        # Теперь нажимаем "Статус служб"
        last_messages = await client.get_messages(bot_username, limit=1)
        last_id = last_messages[0].id if last_messages else 0
        await client.send_message(bot_username, "Статус служб")
        response = await wait_for_bot_response(client, bot_username, last_id, "Статус служб:")
        
        assert "Shadowsocks: Неясный статус" in response.text
        assert "Trojan: не найден" in response.text

    finally:
        await client.disconnect()
