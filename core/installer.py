import os
from configparser import ConfigParser
from .shell_utils import run_command, run_command_streamed

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
        
        # Путь к главному скрипту, который мы будем скачивать
        self.bootstrap_script_url = "https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh"
        self.bootstrap_script_path = "/tmp/bootstrap.sh"

    async def is_installed(self) -> bool:
        """
        Проверяет, установлена ли система, по наличию файла-маркера.
        """
        return os.path.exists(self.install_marker)

    async def is_configured(self) -> bool:
        """
        Проверяет, настроена ли система (файл-маркер не пустой).
        """
        if not await self.is_installed():
            return False
        return os.path.getsize(self.install_marker) > 0

    async def run_installation(self, update, context):
        """
        Выполняет установку базовых компонентов.
        """
        message = await update.message.reply_text("🚀 Начинаю установку...")

        if not os.path.exists(self.install_script_path):
            await message.edit_text(f"❌ Ошибка: Установочный скрипт не найден по пути {self.install_script_path}")
            return

        command = f"sh {self.install_script_path}"

        await message.edit_text(f"⏳ Запускаю {command}... Это может занять несколько минут.\n\n<pre></pre>", parse_mode='HTML')
        
        return_code, full_log = await run_command_streamed(command, update, context, message)

        if return_code == 0:
            if await self.is_installed():
                await message.edit_text(f"✅ Базовая установка завершена!\n\n<pre>{full_log}</pre>\n\nТеперь нужно настроить iptables. Пожалуйста, перезапустите бота командой /start.", parse_mode='HTML')
            else:
                await message.edit_text(f"⚠️ Установка завершилась, но маркер установки не был найден.\n\n<pre>{full_log}</pre>", parse_mode='HTML')
        else:
            await message.edit_text(f"❌ Установка завершилась с ошибкой.\n\n<pre>{full_log}</pre>", parse_mode='HTML')

    async def configure_iptables(self, ss_port: int):
        """
        Создает S99unblock с правилами iptables.
        """
        script_content = f"""#!/bin/sh

# Восстанавливаем ipset
ipset create unblock hash:ip

# Восстанавливаем правило iptables
iptables -t nat -A PREROUTING -i {self.network_interface} -m set --match-set unblock dst -p tcp -j REDIRECT --to-port {ss_port}
"""
        try:
            with open(self.install_marker, 'w') as f:
                f.write(script_content)
            
            await run_command(f"chmod +x {self.install_marker}")
            return True, "✅ Правила iptables успешно созданы."
        except Exception as e:
            return False, f"❌ Не удалось создать файл {self.install_marker}: {e}"

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

    async def run_reinstallation(self, update, context):
        """
        Выполняет переустановку системы через bootstrap.sh.
        """
        message = await update.message.reply_text("🚀 Начинаю переустановку...")

        download_command = f"curl -sL -o {self.bootstrap_script_path} {self.bootstrap_script_url}"
        run_command = f"sh {self.bootstrap_script_path} --reinstall"
        
        full_command = f"{download_command} && {run_command}"
        
        await run_command_streamed(full_command, update, context, message)
        # Сообщение об успехе не требуется, так как скрипт bootstrap.sh сам все выведет
        # и бот перезапустится.
