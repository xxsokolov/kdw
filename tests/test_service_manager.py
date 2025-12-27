import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from core.service_manager import ServiceManager

@pytest.fixture
def service_manager():
    """Фикстура для создания экземпляра ServiceManager."""
    return ServiceManager()

@pytest.mark.asyncio
async def test_get_all_statuses(service_manager):
    """
    Тестирует сбор статусов всех служб.
    Мокаем _get_service_status, чтобы изолировать тесты.
    """
    with patch.object(service_manager, '_get_service_status', new_callable=AsyncMock) as mock_get_status:
        # Настраиваем, чтобы мок возвращал разные статусы для разных служб
        async def side_effect(service_name):
            if service_name == "Shadowsocks":
                return "✅ активен"
            elif service_name == "Tor":
                return "❌ неактивен"
            else:
                return "❓ не найден"
        
        mock_get_status.side_effect = side_effect

        report = await service_manager.get_all_statuses()

        assert "Shadowsocks: ✅ активен" in report
        assert "Tor: ❌ неактивен" in report
        assert "Vmess: ❓ не найден" in report
        assert "Trojan: ❓ не найден" in report

@pytest.mark.asyncio
async def test_get_service_status_active(service_manager):
    """
    Тест: служба найдена и активна (pgrep нашел процесс).
    """
    with patch('core.service_manager.os.path.isdir', return_value=True), \
         patch('core.service_manager.glob.glob', return_value=['/opt/etc/init.d/S80shadowsocks']), \
         patch('asyncio.create_subprocess_shell') as mock_subprocess:
        
        # Мокаем успешный вызов pgrep
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b'12345', b'')
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        status = await service_manager._get_service_status("Shadowsocks")
        
        assert status == "✅ активен"
        mock_subprocess.assert_called_with("pgrep -f shadowsocks", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

@pytest.mark.asyncio
async def test_get_service_status_inactive(service_manager):
    """
    Тест: служба найдена, но неактивна (pgrep не нашел процесс).
    """
    with patch('core.service_manager.os.path.isdir', return_value=True), \
         patch('core.service_manager.glob.glob', return_value=['/opt/etc/init.d/S80shadowsocks']), \
         patch('asyncio.create_subprocess_shell') as mock_subprocess:
        
        # Мокаем неуспешный вызов pgrep
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b'', b'')
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        status = await service_manager._get_service_status("Shadowsocks")
        
        assert status == "❌ неактивен"

@pytest.mark.asyncio
async def test_get_service_status_not_found(service_manager):
    """
    Тест: скрипт службы не найден в init.d.
    """
    with patch('core.service_manager.os.path.isdir', return_value=True), \
         patch('core.service_manager.glob.glob', return_value=[]): # glob ничего не нашел
        
        status = await service_manager._get_service_status("Shadowsocks")
        
        assert status == "❓ не найден"

@pytest.mark.asyncio
async def test_get_service_status_dir_not_found(service_manager):
    """
    Тест: директория init.d не существует.
    """
    with patch('core.service_manager.os.path.isdir', return_value=False):
        status = await service_manager._get_service_status("Shadowsocks")
        assert status == "❓ не найден"
