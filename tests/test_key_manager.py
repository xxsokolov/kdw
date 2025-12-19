import pytest
import asyncio
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock
from configparser import ConfigParser
from core.key_manager import KeyManager

# Мокаем ConfigParser, чтобы не зависеть от kdw.cfg
@pytest.fixture
def mock_config():
    config = ConfigParser()
    config['shadowsocks'] = {
        'mode': 'tcp_and_udp',
        'timeout': '86400',
        'local_address': '::',
        'local_port': '1080',
        'fast_open': 'False',
        'ipv6_first': 'True',
        'path': '/tmp/shadowsocks_configs' # Используем временную директорию
    }
    return config

@pytest.fixture
def key_manager(mock_config):
    """Фикстура для создания экземпляра KeyManager с мокнутым конфигом."""
    with patch('core.key_manager.ConfigParser', return_value=mock_config):
        manager = KeyManager()
        # Мокаем service_manager
        manager.service_manager = AsyncMock()
        return manager

@pytest.fixture
def mock_key_parser():
    """Фикстура для мокирования key_parser."""
    with patch('core.key_manager.key_parser') as mock_parser:
        yield mock_parser

@pytest.mark.asyncio
async def test_update_shadowsocks_config_success(key_manager, mock_key_parser, mock_config, tmp_path):
    """Тест: успешное обновление конфига Shadowsocks."""
    mock_key_parser.parse_shadowsocks_key.return_value = {
        "server": "test.server.com",
        "server_port": 8443,
        "method": "aes-256-gcm",
        "password": "testpassword",
        "tag": "TestServer"
    }
    
    # Убедимся, что путь для конфигов существует
    config_path = tmp_path / "shadowsocks_configs"
    config_path.mkdir()
    mock_config['shadowsocks']['path'] = str(config_path)

    key_manager.service_manager.restart_service.return_value = (True, "Service restarted.")

    key_string = "ss://..."
    success, message = await key_manager.update_shadowsocks_config(key_string)

    assert success is True
    assert "успешно обновлена и служба перезапущена" in message

    # Проверяем, что файл конфига был создан с правильным содержимым
    expected_file_path = config_path / "TestServer.json"
    assert expected_file_path.exists()
    
    with open(expected_file_path, 'r') as f:
        content = json.load(f)
        assert content['server'] == "test.server.com"
        assert content['server_port'] == 8443
        assert content['method'] == "aes-256-gcm"
        assert content['password'] == "testpassword"
        assert content['mode'] == "tcp_and_udp" # Из мокнутого конфига
    
    key_manager.service_manager.restart_service.assert_called_once_with("shadowsocks")

@pytest.mark.asyncio
async def test_update_shadowsocks_config_invalid_key(key_manager, mock_key_parser):
    """Тест: обновление конфига Shadowsocks с невалидным ключом."""
    mock_key_parser.parse_shadowsocks_key.return_value = None
    
    key_string = "invalid_ss_key"
    success, message = await key_manager.update_shadowsocks_config(key_string)

    assert success is False
    assert "Не удалось распознать формат ключа Shadowsocks" in message
    key_manager.service_manager.restart_service.assert_not_called()

@pytest.mark.asyncio
async def test_update_shadowsocks_config_restart_failure(key_manager, mock_key_parser, mock_config, tmp_path):
    """Тест: обновление конфига Shadowsocks, но ошибка перезапуска службы."""
    mock_key_parser.parse_shadowsocks_key.return_value = {
        "server": "test.server.com",
        "server_port": 8443,
        "method": "aes-256-gcm",
        "password": "testpassword",
        "tag": "TestServer"
    }
    
    config_path = tmp_path / "shadowsocks_configs"
    config_path.mkdir()
    mock_config['shadowsocks']['path'] = str(config_path)

    key_manager.service_manager.restart_service.return_value = (False, "Failed to restart service.")

    key_string = "ss://..."
    success, message = await key_manager.update_shadowsocks_config(key_string)

    assert success is False
    assert "Конфиг обновлен, но службу перезапустить не удалось" in message
    assert (config_path / "TestServer.json").exists() # Файл все равно должен быть создан
    key_manager.service_manager.restart_service.assert_called_once_with("shadowsocks")
