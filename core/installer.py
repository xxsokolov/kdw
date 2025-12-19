import os
from configparser import ConfigParser
from .shell_utils import run_command_streamed

class Installer:
    """
    Класс для управления установкой и удалением системы обхода блокировок.
    """
    def __init__(self, config_file="kdw.cfg"):
        config = ConfigParser()
        config.read(config_file, encoding='utf-8')
        
        self.install_marker = "/opt/etc/init.d/S99unblock"
        self.install_script_path = config.get('installer', 'script_path', fallback='/bin/false')
        self.network_interface = config.get('installer', 'network_interface', fallback='br0')

    async def is_installed(self) -> bool:
        """
        Проверяет, установлена ли система, по наличию файла-маркера.
        """
        return os.path.exists(self.install_marker)

    async def run_installation(self, update, context):
        """
        Выполняет установку системы обхода, используя скрипт и параметры из kdw.cfg.
        """
        message = await update.message.reply_text("🚀 Начинаю установку...")

        if not os.path.exists(self.install_script_path):
            await message.edit_text(f"❌ Ошибка: Установочный скрипт не найден по пути {self.install_script_path}")
            return

        # Собираем команду с параметрами из конфига
        command = f"{self.install_script_path} --interface {self.network_interface}"

        # Запускаем установку и стримим вывод
        await message.edit_text(f"⏳ Запускаю {command}... Это может занять несколько минут.\n\n<pre></pre>", parse_mode='HTML')
        
        return_code, full_log = await run_command_streamed(command, update, context, message)

        if return_code == 0:
            if await self.is_installed():
                await message.edit_text(f"✅ Установка завершена!\n\n<pre>{full_log}</pre>\n\nПожалуйста, перезапустите бота командой /start.", parse_mode='HTML')
            else:
                await message.edit_text(f"⚠️ Установка завершилась, но маркер установки не был найден.\n\n<pre>{full_log}</pre>", parse_mode='HTML')
        else:
            await message.edit_text(f"❌ Установка завершилась с ошибкой.\n\n<pre>{full_log}</pre>", parse_mode='HTML')
