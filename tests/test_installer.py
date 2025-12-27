import pytest
from unittest.mock import AsyncMock, patch, call
from core.installer import Installer

@pytest.fixture
def installer():
    return Installer()

@pytest.mark.asyncio
async def test_run_update_success(installer):
    """
    Тестирует успешный сценарий обновления с разделением команд.
    """
    mock_update = AsyncMock()
    mock_message = AsyncMock()
    mock_update.message.reply_text.return_value = mock_message

    with patch('core.installer.run_command', new_callable=AsyncMock) as mock_run_command, \
         patch('core.installer.run_command_streamed', new_callable=AsyncMock) as mock_run_command_streamed:
        
        # Мокаем успешное выполнение скачивания и chmod
        mock_run_command.side_effect = [(0, "", ""), (0, "", "")]
        mock_run_command_streamed.return_value = (0, "Update log...")
        
        await installer.run_update(mock_update, {})
        
        # Проверяем вызовы run_command
        expected_calls = [
            call(f"curl -sL -o {installer.bootstrap_script_path} {installer.bootstrap_script_url}"),
            call(f"chmod +x {installer.bootstrap_script_path}")
        ]
        mock_run_command.assert_has_calls(expected_calls)

        # Проверяем вызов run_command_streamed
        mock_run_command_streamed.assert_called_once_with(
            f"sh {installer.bootstrap_script_path} --update",
            mock_update, {}, mock_message, stdin_input=b'y\n'
        )

@pytest.mark.asyncio
async def test_run_uninstallation_success(installer):
    """
    Тестирует успешный сценарий удаления с разделением команд.
    """
    mock_update = AsyncMock()
    mock_message = AsyncMock()
    mock_update.message.reply_text.return_value = mock_message

    with patch('core.installer.run_command', new_callable=AsyncMock) as mock_run_command, \
         patch('core.installer.run_command_streamed', new_callable=AsyncMock) as mock_run_command_streamed:
        
        mock_run_command.side_effect = [(0, "", ""), (0, "", "")]
        mock_run_command_streamed.return_value = (0, "Uninstall log...")
        
        await installer.run_uninstallation(mock_update, {})

        # Проверяем вызовы run_command
        expected_calls = [
            call(f"curl -sL -o {installer.bootstrap_script_path} {installer.bootstrap_script_url}"),
            call(f"chmod +x {installer.bootstrap_script_path}")
        ]
        mock_run_command.assert_has_calls(expected_calls)

        # Проверяем вызов run_command_streamed
        mock_run_command_streamed.assert_called_once_with(
            f"sh {installer.bootstrap_script_path} --uninstall",
            mock_update, {}, mock_message, stdin_input=b'y\n'
        )
        
        mock_message.edit_text.assert_called_with(
            f"✅ Система полностью удалена.\n\n<pre>Uninstall log...</pre>\n\nБот больше не будет работать. Чтобы установить его заново, используйте bootstrap.sh.",
            parse_mode='HTML'
        )

@pytest.mark.asyncio
async def test_prepare_script_curl_failure(installer):
    """
    Тестирует ошибку на этапе скачивания скрипта.
    """
    mock_update = AsyncMock()
    mock_message = AsyncMock()
    mock_update.message.reply_text.return_value = mock_message

    with patch('core.installer.run_command', new_callable=AsyncMock) as mock_run_command:
        # Мокаем ошибку curl
        mock_run_command.return_value = (1, "", "curl error")
        
        await installer.run_update(mock_update, {})
        
        mock_message.edit_text.assert_called_with(
            "❌ Не удалось скачать скрипт обновления:\n<pre>curl error</pre>",
            parse_mode='HTML'
        )
