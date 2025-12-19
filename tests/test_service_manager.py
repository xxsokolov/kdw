import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from core.service_manager import ServiceManager, SERVICE_NAMES

@pytest.fixture
def service_manager():
    """Фикстура для создания экземпляра ServiceManager."""
    return ServiceManager()

@pytest.mark.asyncio
async def test_get_all_statuses_running(service_manager):
    """Тест: все службы запущены."""
    # Патчим run_command там, где она используется (в service_manager)
    with patch('core.service_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        # Мок должен возвращать строки, которые содержат "running"
        mock_run_command.return_value = (0, "Service is running.", "")
        status_report = await service_manager.get_all_statuses()

        expected_lines = []
        for name in SERVICE_NAMES.keys():
            expected_lines.append(f"✅ {name.capitalize()}: Запущен")

        assert status_report == "\n".join(expected_lines)
        assert mock_run_command.call_count == len(SERVICE_NAMES)

@pytest.mark.asyncio
async def test_get_all_statuses_stopped(service_manager):
    """Тест: все службы остановлены."""
    with patch('core.service_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        # Мок должен возвращать строки, которые содержат "stopped"
        mock_run_command.return_value = (0, "Service is stopped.", "")
        status_report = await service_manager.get_all_statuses()

        expected_lines = []
        for name in SERVICE_NAMES.keys():
            expected_lines.append(f"❌ {name.capitalize()}: Остановлен")

        assert status_report == "\n".join(expected_lines)

@pytest.mark.asyncio
async def test_get_all_statuses_error(service_manager):
    """Тест: ошибка при проверке статуса службы (не 0 код возврата)."""
    with patch('core.service_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        # Мок возвращает код ошибки
        mock_run_command.return_value = (1, "", "Error checking status.")
        status_report = await service_manager.get_all_statuses()

        expected_lines = []
        for name in SERVICE_NAMES.keys():
            expected_lines.append(f"❓ {name.capitalize()}: не найден")

        assert status_report == "\n".join(expected_lines)

@pytest.mark.asyncio
async def test_restart_service_success(service_manager):
    """Тест: успешный перезапуск службы."""
    with patch('core.service_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        mock_run_command.return_value = (0, "Service restarted.", "")
        success, message = await service_manager.restart_service("shadowsocks")

        assert success is True
        assert "успешно перезапущена" in message
        mock_run_command.assert_called_once_with(f"/opt/etc/init.d/{SERVICE_NAMES['shadowsocks']} restart")

@pytest.mark.asyncio
async def test_restart_service_failure(service_manager):
    """Тест: ошибка при перезапуске службы."""
    with patch('core.service_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        mock_run_command.return_value = (1, "", "Failed to restart.")
        success, message = await service_manager.restart_service("shadowsocks")

        assert success is False
        assert "Ошибка перезапуска службы" in message
        mock_run_command.assert_called_once_with(f"/opt/etc/init.d/{SERVICE_NAMES['shadowsocks']} restart")

@pytest.mark.asyncio
async def test_restart_service_not_found(service_manager):
    """Тест: попытка перезапустить несуществующую службу."""
    with patch('core.service_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        success, message = await service_manager.restart_service("nonexistent_service")

        assert success is False
        assert "не найдена" in message
        mock_run_command.assert_not_called()
