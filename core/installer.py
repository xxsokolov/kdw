import os
import asyncio
import re
import html
from .shell_utils import run_shell_command
from .log_utils import log
from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

def _clean_ansi_codes(text: str) -> str:
    """Удаляет ANSI-коды (цветовые коды терминала) из строки."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class Installer:
    """
    Класс для управления установкой, обновлением и удалением KDW Bot.
    Все операции делегируются главному скрипту bootstrap.sh.
    """
    def __init__(self, config_file=None):
        self.bootstrap_script_url = "https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh"
        self.bootstrap_script_path = "/tmp/bootstrap.sh"

    async def _run_command_streamed(self, command: str, update: Update, context: ContextTypes.DEFAULT_TYPE, message: Message):
        """
        Выполняет команду, стримит ее очищенный вывод в Telegram,
        а также дублирует в лог бота и системный журнал Keenetic.
        """
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        full_log_telegram = ""
        last_sent_text = ""
        
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            
            decoded_line = line.decode('utf-8', errors='ignore')
            # Сразу очищаем строку от ANSI кодов
            cleaned_line = _clean_ansi_codes(decoded_line).strip()

            if not cleaned_line:
                continue

            # 1. Логируем ОЧИЩЕННУЮ строку в консоль бота и системный журнал Keenetic
            log.info(f"[Update] {cleaned_line}")
            escaped_for_shell = cleaned_line.replace('"', '\\"')
            await run_shell_command(f'logger -t "KDW-Update" "{escaped_for_shell}"')

            # 2. Готовим чистый лог для Telegram
            full_log_telegram += cleaned_line + "\n"
            
            # 3. Стримим в Telegram, избегая спама
            if full_log_telegram.strip() != last_sent_text.strip():
                try:
                    # Используем html.escape для безопасности
                    await message.edit_text(f"<pre>{html.escape(full_log_telegram)}</pre>", parse_mode=ParseMode.HTML)
                    last_sent_text = full_log_telegram
                except Exception:
                    # Игнорируем ошибки, если сообщение не изменилось
                    pass
        
        await proc.wait()
        return proc.returncode, full_log_telegram

    async def _prepare_bootstrap_script(self, message) -> bool:
        """Скачивает и делает исполняемым скрипт bootstrap.sh."""
        await message.edit_text("Загружаю скрипт обновления...")
        # Добавляем Cache-Control, чтобы всегда скачивать свежую версию
        curl_command = f"curl -H \"Cache-Control: no-cache\" -sL -o {self.bootstrap_script_path} \"{self.bootstrap_script_url}?$(date +%s)\""
        success, output = await run_shell_command(curl_command)
        if not success:
            error_text = f"❌ Не удалось скачать скрипт обновления:\n<pre>{output}</pre>"
            log.error(f"Update failed: Cannot download bootstrap script. Output: {output}")
            await message.edit_text(error_text, parse_mode='HTML')
            return False

        await message.edit_text("Устанавливаю права на выполнение...")
        success, output = await run_shell_command(f"chmod +x {self.bootstrap_script_path}")
        if not success:
            error_text = f"❌ Не удалось сделать скрипт исполняемым:\n<pre>{output}</pre>"
            log.error(f"Update failed: Cannot chmod bootstrap script. Output: {output}")
            await message.edit_text(error_text, parse_mode='HTML')
            return False
        
        return True

    async def run_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message: Message):
        """
        Выполняет обновление системы через bootstrap.sh с флагом -y, стримя вывод.
        """
        if not await self._prepare_bootstrap_script(message):
            return

        await message.edit_text("🚀 Обновление началось...", parse_mode=ParseMode.HTML)
        # Запускаем обновление с флагом -y для автоматического подтверждения
        run_command = f"sh {self.bootstrap_script_path} --update -y"
        await self._run_command_streamed(run_command, update, context, message)

    async def run_uninstallation(self, update, context):
        """
        Выполняет полное удаление системы через bootstrap.sh, автоматически подтверждая запрос.
        """
        message = await update.callback_query.message.reply_text("🚀 Начинаю полное удаление...")
        
        if not await self._prepare_bootstrap_script(message):
            return

        # Запускаем удаление с флагом -y
        run_command = f"sh {self.bootstrap_script_path} --uninstall -y"
        return_code, full_log = await self._run_command_streamed(run_command, update, context, message)

        if return_code == 0:
            await message.edit_text(f"✅ Система полностью удалена.\n\n<pre>{full_log}</pre>\n\nБот больше не будет работать. Чтобы установить его заново, используйте bootstrap.sh.", parse_mode='HTML')
        else:
            await message.edit_text(f"❌ Удаление завершилось с ошибкой.\n\n<pre>{full_log}</pre>", parse_mode='HTML')

    async def is_installed(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw_bot.py")

    async def is_configured(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw.cfg")
