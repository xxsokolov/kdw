import pytest
import asyncio
import os
from unittest.mock import AsyncMock, patch, mock_open
from core.list_manager import ListManager, LISTS_DIR, UPDATE_SCRIPT

@pytest.fixture
def list_manager():
    """Фикстура для создания экземпляра ListManager."""
    return ListManager()

@pytest.fixture
def mock_lists_dir(tmp_path):
    """Фикстура для создания временной директории списков."""
    # Переопределяем LISTS_DIR на временную директорию для тестов
    with patch('core.list_manager.LISTS_DIR', str(tmp_path)):
        yield tmp_path

@pytest.mark.asyncio
async def test_get_list_files(list_manager, mock_lists_dir):
    """Тест: получение списка файлов."""
    (mock_lists_dir / "list1.txt").touch()
    (mock_lists_dir / "list2.txt").touch()
    (mock_lists_dir / "other.log").touch()
    (mock_lists_dir / "subdir").mkdir()

    files = list_manager.get_list_files()
    assert sorted(files) == ["list1", "list2"]

@pytest.mark.asyncio
async def test_read_list(list_manager, mock_lists_dir):
    """Тест: чтение содержимого списка."""
    (mock_lists_dir / "test_list.txt").write_text("domain1.com\ndomain2.com")
    content = list_manager.read_list("test_list")
    assert content == "domain1.com\ndomain2.com"

    content_empty = list_manager.read_list("non_existent_list")
    assert content_empty == "Файл списка не найден."

    (mock_lists_dir / "empty_list.txt").touch()
    content_empty_file = list_manager.read_list("empty_list")
    assert content_empty_file == "Список пуст."

@pytest.mark.asyncio
async def test_add_to_list(list_manager, mock_lists_dir):
    """Тест: добавление доменов в список."""
    file_path = mock_lists_dir / "add_list.txt"
    file_path.write_text("existing.com\n")

    added = await list_manager.add_to_list("add_list", ["new.com", "another.com"])
    assert added is True
    assert file_path.read_text() == "another.com\nexisting.com\nnew.com\n"

    # Повторное добавление существующих доменов
    added_again = await list_manager.add_to_list("add_list", ["new.com"])
    assert added_again is False # Ничего нового не добавлено

@pytest.mark.asyncio
async def test_remove_from_list(list_manager, mock_lists_dir):
    """Тест: удаление доменов из списка."""
    file_path = mock_lists_dir / "remove_list.txt"
    file_path.write_text("domain1.com\ndomain2.com\ndomain3.com\n")

    removed = await list_manager.remove_from_list("remove_list", ["domain2.com"])
    assert removed is True
    assert file_path.read_text() == "domain1.com\ndomain3.com\n"

    # Попытка удалить несуществующие домены
    removed_again = await list_manager.remove_from_list("remove_list", ["nonexistent.com"])
    assert removed_again is False

@pytest.mark.asyncio
async def test_apply_changes_success(list_manager):
    """Тест: успешное применение изменений."""
    with patch('core.list_manager.UPDATE_SCRIPT', '/tmp/mock_update.sh'), \
         patch('os.path.exists', return_value=True), \
         patch('core.list_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        
        mock_run_command.return_value = (0, "Update successful", "")
        success, message = await list_manager.apply_changes()
        
        assert success is True
        assert "успешно обновлены" in message
        mock_run_command.assert_called_once_with('/tmp/mock_update.sh')

@pytest.mark.asyncio
async def test_apply_changes_failure(list_manager):
    """Тест: ошибка при применении изменений."""
    with patch('core.list_manager.UPDATE_SCRIPT', '/tmp/mock_update.sh'), \
         patch('os.path.exists', return_value=True), \
         patch('core.list_manager.run_command', new_callable=AsyncMock) as mock_run_command:
        
        mock_run_command.return_value = (1, "Error output", "Error message")
        success, message = await list_manager.apply_changes()
        
        assert success is False
        assert "Ошибка обновления списков" in message
        assert "Error output" in message
        assert "Error message" in message
