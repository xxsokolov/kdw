import asyncio
import glob
import os
from core.log_utils import log as logger

class ServiceManager:
    """
    Управляет службами в /opt/etc/init.d, такими как Shadowsocks, Tor и т.д.
    """
    def __init__(self):
        self.init_dir = "/opt/etc/init.d"
        # Сопоставление имени службы с шаблоном файла в init.d
        self.service_map = {
            "Shadowsocks": "S*shadowsocks*",
            "Trojan": "S*trojan*",
            "Vmess": "S*vmess*",
            "Tor": "S*tor*",
        }

    def _find_script(self, pattern: str) -> str | None:
        """
        Находит первый скрипт в init.d, соответствующий шаблону.
        """
        if not os.path.isdir(self.init_dir):
            logger.warning(f"Директория {self.init_dir} не найдена.")
            return None
        
        scripts = glob.glob(os.path.join(self.init_dir, pattern))
        return scripts[0] if scripts else None

    async def _get_service_status(self, service_name: str) -> str:
        """
        Получает статус одной службы: активна, неактивна, не найдена.
        """
        pattern = self.service_map.get(service_name)
        if not pattern:
            return "не поддерживается"

        script_path = self._find_script(pattern)
        if not script_path:
            return "❓ не найден"

        proc_name = os.path.basename(script_path)[3:] # Убираем 'S##'
        
        proc = await asyncio.create_subprocess_shell(
            f"pgrep -f {proc_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0 and stdout:
            return "✅ активен"
        else:
            return "❌ неактивен"

    async def get_all_statuses(self) -> str:
        """
        Собирает статусы всех известных служб в один отчет.
        """
        tasks = [self._get_service_status(name) for name in self.service_map.keys()]
        statuses = await asyncio.gather(*tasks)
        
        report = []
        for name, status in zip(self.service_map.keys(), statuses):
            report.append(f"{name}: {status}")
            
        return "\n".join(report)

    async def _restart_service(self, service_name: str) -> (bool, str):
        """
        Перезапускает одну службу.
        Возвращает кортеж (успех, сообщение).
        """
        pattern = self.service_map.get(service_name)
        if not pattern:
            return False, f"{service_name}: не поддерживается"

        script_path = self._find_script(pattern)
        if not script_path:
            # Это не ошибка, просто службы нет
            return True, f"{service_name}: ❓ не найден"

        logger.info(f"Перезапуск службы: {script_path}")
        proc = await asyncio.create_subprocess_shell(
            f'sh -c "{script_path} restart"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info(f"Служба {service_name} успешно перезапущена.")
            return True, f"{service_name}: ✅ перезапущена"
        else:
            error_message = stderr.decode('utf-8', errors='ignore').strip() if stderr else "Неизвестная ошибка"
            logger.error(f"Ошибка при перезапуске {service_name}: {error_message}")
            return False, f"{service_name}: ❌ ошибка\n`{error_message}`"

    async def restart_all_services(self) -> str:
        """
        Перезапускает все известные службы и возвращает отчет.
        """
        tasks = [self._restart_service(name) for name in self.service_map.keys()]
        results = await asyncio.gather(*tasks)
        
        report = [message for _, message in results if "не найден" not in message]
            
        return "\n".join(report) if report else "Не найдено активных служб для перезапуска."
