import os
import asyncio
from .shell_utils import run_shell_command
from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

class Installer:
    """
    Класс для управления установкой, обновлением и удалением KDW Bot.
    Все операции делегируются главному скрипту bootstrap.sh.
    """
    def __init__(self, config_file=None):
        self.bootstrap_script_url = "https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh"
        self.bootstrap_script_path = "/tmp/bootstrap.sh"

    async def _run_command_streamed(self, command: str, update: Update, context: ContextTypes.DEFAULT_TYPE, message, stdin_input: bytes = None):
        """
        Выполняет команду и стримит ее вывод в сообщение Telegram.
        """
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE if stdin_input else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        if stdin_input:
            proc.stdin.write(stdin_input)
            await proc.stdin.drain()
            proc.stdin.close()

        full_log = ""
        last_sent_text = ""
        
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            
            decoded_line = line.decode('utf-8', errors='ignore')
            full_log += decoded_line
            
            # Чтобы избежать спама, обновляем сообщение только если оно изменилось
            if full_log != last_sent_text:
                try:
                    await message.edit_text(f"<pre>{full_log}</pre>", parse_mode=ParseMode.HTML)
                    last_sent_text = full_log
                except Exception:
                    # Игнорируем ошибки, если сообщение не изменилось (например, из-за лимитов Telegram)
                    pass
        
        await proc.wait()
        return proc.returncode, full_log

    async def _prepare_bootstrap_script(self, message) -> bool:
        """Скачивает и делает исполняемым скрипт bootstrap.sh."""
        # 1. Скачиваем скрипт
        success, output = await run_shell_command(f"curl -sL -o {self.bootstrap_script_path} {self.bootstrap_script_url}")
        if not success:
            await message.edit_text(f"❌ Не удалось скачать скрипт обновления:\n<pre>{output}</pre>", parse_mode='HTML')
            return False

        # 2. Делаем исполняемым
        success, output = await run_shell_command(f"chmod +x {self.bootstrap_script_path}")
        if not success:
            await message.edit_text(f"❌ Не удалось сделать скрипт исполняемым:\n<pre>{output}</pre>", parse_mode='HTML')
            return False
        
        return True

    async def run_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message: Message):
        """
        Выполняет обновление системы через bootstrap.sh, стримя вывод в предоставленное сообщение.
        """
        if not await self._prepare_bootstrap_script(message):
            return

        # Запускаем обновление, передавая 'y' в stdin
        run_command = f"sh {self.bootstrap_script_path} --update"
        await self._run_command_streamed(run_command, update, context, message, stdin_input=b'y\n')
        # Сообщение об успехе не требуется, так как скрипт bootstrap.sh сам все выведет
        # и бот перезапустится.

    async def run_uninstallation(self, update, context):
        """
        Выполняет полное удаление системы через bootstrap.sh, автоматически подтверждая запрос.
        """
        message = await update.callback_query.message.reply_text("🚀 Начинаю полное удаление...")
        
        if not await self._prepare_bootstrap_script(message):
            return

        # 3. Запускаем удаление, передавая 'y' в stdin
        run_command = f"sh {self.bootstrap_script_path} --uninstall"
        return_code, full_log = await self._run_command_streamed(run_command, update, context, message, stdin_input=b'y\n')

        if return_code == 0:
            await message.edit_text(f"✅ Система полностью удалена.\n\n<pre>{full_log}</pre>\n\nБот больше не будет работать. Чтобы установить его заново, используйте bootstrap.sh.", parse_mode='HTML')
        else:
            await message.edit_text(f"❌ Удаление завершилось с ошибкой.\n\n<pre>{full_log}</pre>", parse_mode='HTML')

    async def is_installed(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw_bot.py")

    async def is_configured(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw.cfg")
