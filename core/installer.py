import os
from .shell_utils import run_command_streamed

class Installer:
    """
    Класс для управления установкой, обновлением и удалением KDW Bot.
    Все операции делегируются главному скрипту bootstrap.sh.
    """
    def __init__(self, config_file=None):
        # Путь к главному скрипту, который мы будем скачивать
        self.bootstrap_script_url = "https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh"
        self.bootstrap_script_path = "/tmp/bootstrap.sh"

    async def run_update(self, update, context):
        """
        Выполняет обновление системы через bootstrap.sh.
        """
        message = await update.message.reply_text("🚀 Начинаю обновление...")
        
        download_command = f"curl -sL -o {self.bootstrap_script_path} {self.bootstrap_script_url}"
        run_command = f"sh {self.bootstrap_script_path} --update"
        full_command = f"{download_command} && {run_command}"
        
        await run_command_streamed(full_command, update, context, message)
        # Сообщение об успехе не требуется, так как скрипт bootstrap.sh сам все выведет
        # и бот перезапустится.

    async def run_uninstallation(self, update, context):
        """
        Выполняет полное удаление системы через bootstrap.sh.
        """
        message = await update.message.reply_text("🚀 Начинаю полное удаление...")
        
        download_command = f"curl -sL -o {self.bootstrap_script_path} {self.bootstrap_script_url}"
        run_command = f"sh {self.bootstrap_script_path} --uninstall"
        full_command = f"{download_command} && {run_command}"
        
        return_code, full_log = await run_command_streamed(full_command, update, context, message)

        if return_code == 0:
            await message.edit_text(f"✅ Система полностью удалена.\n\n<pre>{full_log}</pre>\n\nБот больше не будет работать. Чтобы установить его заново, используйте bootstrap.sh.", parse_mode='HTML')
        else:
            await message.edit_text(f"❌ Удаление завершилось с ошибкой.\n\n<pre>{full_log}</pre>", parse_mode='HTML')

    # Старые методы, связанные с установкой через `install.sh`, больше не нужны
    # и могут быть удалены. Оставляем их пока для обратной совместимости,
    # но они больше не вызываются из основного кода.
    async def is_installed(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw_bot.py")

    async def is_configured(self) -> bool:
        return os.path.exists("/opt/etc/kdw/kdw.cfg")
