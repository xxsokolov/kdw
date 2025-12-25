import asyncio
import glob
import os

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

        # Пытаемся найти процесс, связанный со скриптом.
        # Это более надежно, чем проверять PID-файл.
        # Ищем процесс по имени, которое обычно совпадает с названием скрипта без префикса S##.
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
