import pytest
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock
from configparser import ConfigParser
from core.installer import Installer

@pytest.fixture
def mock_installer_config():
    config = ConfigParser()
    config['installer'] = {
        'script_path': '/tmp/mock_install.sh',
        'network_interface': 'eth0'
    }
    return config

@pytest.fixture
def installer(mock_installer_config):
    with patch('core.installer.ConfigParser', return_value=mock_installer_config):
        return Installer()

@pytest.mark.asyncio
async def test_is_installed_true(installer):
    with patch('os.path.exists', return_value=True):
        assert await installer.is_installed() is True

@pytest.mark.asyncio
async def test_is_installed_false(installer):
    with patch('os.path.exists', return_value=False):
        assert await installer.is_installed() is False

@pytest.mark.asyncio
async def test_run_installation_script_not_found(installer):
    mock_update = AsyncMock()
    mock_message = AsyncMock()
    mock_update.message.reply_text.return_value = mock_message

    with patch('os.path.exists', return_value=False), \
         patch('core.installer.run_command', new_callable=AsyncMock) as mock_run_command, \
         patch('core.installer.run_command_streamed', new_callable=AsyncMock) as mock_run_command_streamed:
        
        await installer.run_installation(mock_update, {})
        
        mock_message.edit_text.assert_called_with(
            f"❌ Ошибка: Установочный скрипт не найден по пути {installer.install_script_path}"
        )
        mock_run_command.assert_not_called()
        mock_run_command_streamed.assert_not_called()

@pytest.mark.asyncio
async def test_run_installation_success(installer):
    mock_update = AsyncMock()
    mock_message = AsyncMock()
    mock_update.message.reply_text.return_value = mock_message

    with patch('os.path.exists', return_value=True), \
         patch('core.installer.run_command', new_callable=AsyncMock) as mock_run_command, \
         patch('core.installer.run_command_streamed', new_callable=AsyncMock) as mock_run_command_streamed:
        
        mock_run_command.return_value = (0, "", "") # chmod
        mock_run_command_streamed.return_value = (0, "Installation log...") # install.sh
        
        await installer.run_installation(mock_update, {})
        
        # Проверяем финальное сообщение
        mock_message.edit_text.assert_called_with(
            f"✅ Базовая установка завершена!\n\n<pre>Installation log...</pre>\n\nТеперь нужно настроить iptables. Пожалуйста, перезапустите бота командой /start.",
            parse_mode='HTML'
        )

@pytest.mark.asyncio
async def test_run_installation_failure(installer):
    mock_update = AsyncMock()
    mock_message = AsyncMock()
    mock_update.message.reply_text.return_value = mock_message

    with patch('os.path.exists', return_value=True), \
         patch('core.installer.run_command', new_callable=AsyncMock) as mock_run_command, \
         patch('core.installer.run_command_streamed', new_callable=AsyncMock) as mock_run_command_streamed:
        
        mock_run_command.return_value = (0, "", "") # chmod
        # run_command_streamed возвращает 2 значения
        mock_run_command_streamed.return_value = (1, "Error log...")
        
        await installer.run_installation(mock_update, {})
        
        mock_message.edit_text.assert_called_with(
            f"❌ Установка завершилась с ошибкой.\n\n<pre>Error log...</pre>",
            parse_mode='HTML'
        )
