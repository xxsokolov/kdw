import os
from .shell_utils import run_command_streamed, run_command

class Installer:
    """
    Класс для управления установкой, обновлением и удалением KDW Bot.
    Все операции делегируются главному скрипту bootstrap.sh.
    """
    def __init__(self, config_file=None):
        self.bootstrap_script_url = "https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh"
        self.bootstrap_script_path = "/tmp/bootstrap.sh"

    async def _prepare_bootstrap_script(self, message) -> bool:
        """Скачивает и делает исполняемым скрипт bootstrap.sh."""
        # 1. Скачиваем скрипт
        download_command = f"curl -sL -o {self.bootstrap_script_path} {self.bootstrap_script_url}"
        ret, _, stderr = await run_command(download_command)
        if ret != 0:
            await message.edit_text(f"❌ Не удалось скачать скрипт обновления:\n<pre>{stderr}</pre>", parse_mode='HTML')
            return False

        # 2. Делаем исполняемым
        chmod_command = f"chmod +x {self.bootstrap_script_path}"
        ret, _, stderr = await run_command(chmod_command)
        if ret != 0:
            await message.edit_text(f"❌ Не удалось сделать скрипт исполняемым:\n<pre>{stderr}</pre>", parse_mode='HTML')
            return False
        
        return True

    async def run_update(self, update, context):
        """
        Выполняет обновление системы через bootstrap.sh, автоматически подтверждая запрос.
        """
        message = await update.message.reply_text("🚀 Начинаю обновление...")
        
        if not await self._prepare_bootstrap_script(message):
            return

        # 3. Запускаем обновление, передавая 'y' в stdin
        run_command = f"sh {self.bootstrap_script_path} --update"
        await run_command_streamed(run_command, update, context, message, stdin_input=b'y\n')
        # Сообщение об успехе не требуется, так как скрипт bootstrap.sh сам все выведет
        # и бот перезапустится.

    async def run_uninstallation(self, update, context):
        """
        Выполняет полное удаление системы через bootstrap.sh, автоматически подтверждая запрос.
        """
        message = await update.message.reply_text("🚀 Начинаю полное удаление...")
        
        if not await self._prepare_bootstrap_script(message):
            return

        # 3. Запускаем удаление, передавая 'y' в stdin
        run_command = f"sh {self.bootstrap_script_path} --uninstall"
        return_code, full_log = await run_command_streamed(run_command, update, context, message, stdin_input=b'y\n')

        if return_code == 0:
            await message.edit_text(f"✅ Система полностью удалена.\n\n<pre>{full_log}</pre>\n\nБот больше не будет работать. Чтобы установить его заново, используйте bootstrap.sh.", parse_mode='HTML')
        else:
            await message.edit_text(f"❌ Удаление завершилось с ошибкой.\n\n<pre>{full_log}</pre>", parse_mode='HTML')

    async def is_installed(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw_bot.py")

    async def is_configured(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw.cfg")
