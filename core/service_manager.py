import asyncio
import glob
import os
import re
import statistics
from typing import Dict, Any, List

from core.log_utils import log as logger
from core.shell_utils import run_shell_command
from core.config_manager import ConfigManager

class ServiceManager:
    """
    Управляет службами в /opt/etc/init.d, а также выполняет их диагностику.
    """
    def __init__(self):
        self.init_dir = "/opt/etc/init.d"
        self.service_map = {
            "Shadowsocks": "S*shadowsocks*",
            "Trojan": "S*trojan*",
            "Vmess": "S*vmess*",
            "Tor": "S*tor*",
        }

    def _find_script(self, pattern: str) -> str | None:
        """Находит первый скрипт в init.d, соответствующий шаблону."""
        if not os.path.isdir(self.init_dir):
            logger.warning(f"Директория {self.init_dir} не найдена.")
            return None
        
        scripts = glob.glob(os.path.join(self.init_dir, pattern))
        return scripts[0] if scripts else None

    async def _get_service_status(self, service_name: str) -> str:
        """Получает статус одной службы, вызывая ее собственный status-метод."""
        pattern = self.service_map.get(service_name)
        if not pattern:
            return "не поддерживается"

        script_path = self._find_script(pattern)
        if not script_path:
            return "❓ не найден"

        success, output = await run_shell_command(f"sh {script_path} status")
        if success and ("alive" in output or "running" in output):
            return "✅ активен"
        
        return "❌ неактивен"

    async def get_all_statuses(self) -> str:
        """Собирает статусы всех известных служб в один отчет."""
        tasks = [self._get_service_status(name) for name in self.service_map.keys()]
        statuses = await asyncio.gather(*tasks)
        
        report = [f"{name}: {status}" for name, status in zip(self.service_map.keys(), statuses)]
        return "\n".join(report)

    async def _control_service(self, service_name: str, command: str) -> (bool, str):
        """Внутренняя функция для вызова start/stop/restart."""
        service_key = service_name.lower()
        pattern = None
        for key, p in self.service_map.items():
            if key.lower() == service_key:
                pattern = p
                break
        
        if not pattern:
            return False, f"{service_name}: не поддерживается"

        script_path = self._find_script(pattern)
        if not script_path:
            return True, f"{service_name}: ❓ не найден"

        logger.info(f"Выполнение '{command}' для службы: {script_path}")
        success, output = await run_shell_command(f'sh -c "{script_path} {command}"')

        if success:
            logger.info(f"Служба {service_name} успешно {command}.")
            return True, f"{service_name}: ✅ {command}"
        else:
            logger.error(f"Ошибка при {command} {service_name}: {output}")
            return False, f"{service_name}: ❌ ошибка\n`{output}`"

    async def start_service(self, service_name: str) -> (bool, str):
        return await self._control_service(service_name, "start")

    async def stop_service(self, service_name: str) -> (bool, str):
        return await self._control_service(service_name, "stop")

    async def restart_service(self, service_name: str) -> (bool, str):
        return await self._control_service(service_name, "restart")

    async def restart_all_services(self) -> str:
        """Перезапускает все известные службы и возвращает отчет."""
        tasks = [self.restart_service(name) for name in self.service_map.keys()]
        results = await asyncio.gather(*tasks)
        
        report = [message for _, message in results if "не найден" not in message]
        return "\n".join(report) if report else "Не найдено активных служб для перезапуска."

    async def get_direct_ping(self, host: str) -> str:
        """Выполняет быстрый пинг до хоста и возвращает среднее время."""
        if not host: return "⚠️"
        success, output = await run_shell_command(f"ping -c 3 -W 2 {host}")
        if not success:
            return "❌"
        
        match = re.search(r"round-trip min/avg/max(?:/stddev)? = [\d.]+/([\d.]+)/", output)
        if match:
            return f"{float(match.group(1)):.0f} мс"
        
        match = re.search(r"min/avg/max = [\d.]+/([\d.]+)/", output)
        if match:
            return f"{float(match.group(1)):.0f} мс"
            
        return "⚠️"

    async def diagnose_full_proxy(self, service_name: str, config_path: str) -> Dict[str, Any]:
        """Выполняет полную диагностику одного прокси-конфига."""
        manager = ConfigManager(service_name)
        config = manager.read_config(config_path)
        if not config:
            return {"error": f"Не удалось прочитать конфиг: {os.path.basename(config_path)}"}

        server_host = config.get("server") or config.get("remote_addr")
        
        ping_result, jitter_result, _ = await self._test_direct_ping(server_host)
        
        details = "не поддерживается"
        latency_result, proxy_jitter_result, speed_result = "🤷‍♂️", "🤷‍♂️", "🤷‍♂️"

        if service_name == 'shadowsocks':
            latency_result, proxy_jitter_result, speed_result, details = await self._test_shadowsocks_proxy(config_path)
        elif service_name == 'trojan':
            await self.stop_service('trojan')
            try:
                latency_result, proxy_jitter_result, speed_result, details = await self._test_trojan_proxy(config_path)
            finally:
                await self.start_service('trojan')

        return {
            "ping": ping_result,
            "jitter": jitter_result,
            "latency": latency_result,
            "proxy_jitter": proxy_jitter_result,
            "speed": speed_result,
            "details": details,
            "server": server_host,
        }

    async def _test_direct_ping(self, host: str) -> (str, str, str):
        """Тест 1: Пинг до хоста прокси-сервера напрямую, измеряет avg и mdev (jitter)."""
        if not host: return "⚠️", "⚠️", "Хост не указан"
        success, output = await run_shell_command(f"ping -c 5 -W 2 {host}")
        if not success:
            return "❌", "❌", "Хост недоступен"
        
        match = re.search(r"round-trip min/avg/max(?:/stddev|/mdev)? = [\d.]+/([\d.]+)/[\d.]+(?:/([\d.]+))?", output)
        if match:
            avg = f"{float(match.group(1)):.0f} мс"
            mdev = f"{float(match.group(2)):.0f} мс" if match.group(2) else "N/A"
            return avg, mdev, "Успешно"
        
        logger.warning(f"Не удалось распарсить вывод ping для хоста {host}. Вывод:\n{output}")
        return "⚠️", "⚠️", "Не удалось определить время"

    async def _test_shadowsocks_proxy(self, config_path: str) -> (str, str, str, str):
        """Запускает временный ss-local и тестирует через него."""
        diag_port = 1099
        cmd = f"ss-local -c {config_path} -b 127.0.0.1 -l {diag_port}"
        return await self._run_proxy_tests(cmd, diag_port)

    async def _test_trojan_proxy(self, config_path: str) -> (str, str, str, str):
        """Запускает временный trojan и тестирует через него."""
        config = ConfigManager('trojan').read_config(config_path)
        if not config or 'local_port' not in config:
            return "❌", "N/A", "❌", "local_port не найден"
        
        diag_port = config['local_port']
        cmd = f"trojan -c {config_path}"
        return await self._run_proxy_tests(cmd, diag_port)

    async def _run_proxy_tests(self, cmd: str, port: int) -> (str, str, str, str):
        """Общая логика для запуска временного прокси и выполнения тестов."""
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        
        try:
            await asyncio.sleep(2)

            if proc.returncode is not None:
                 stderr = await proc.stderr.read()
                 error_msg = stderr.decode().strip()
                 logger.error(f"Прокси-клиент не запустился: {error_msg}")
                 return "❌", "N/A", "❌", "клиент не запустился"

            latency_result, proxy_jitter_result, details = await self._test_proxy_latency(port)
            if latency_result == "❌":
                return latency_result, "N/A", "❌", details

            speed_result, speed_details = await self._test_download_speed(port)

            return latency_result, proxy_jitter_result, speed_result, speed_details

        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    async def _test_proxy_latency(self, port: int) -> (str, str, str):
        """Тест 2: Задержка до google.com через прокси (3 замера для расчета джиттера)."""
        latencies = []
        for _ in range(3):
            cmd = f"curl --max-time 10 -o /dev/null -s -w '%{{time_starttransfer}}' --socks5-hostname 127.0.0.1:{port} https://www.google.com"
            success, output = await run_shell_command(cmd)
            if success and output:
                try:
                    latencies.append(float(output.replace(',', '.')) * 1000)
                except (ValueError, TypeError):
                    pass
        
        if len(latencies) >= 2: # Нужно хотя бы 2 замера для расчета
            avg_latency = f"{statistics.mean(latencies):.0f} мс"
            jitter = f"{statistics.stdev(latencies):.0f} мс"
            return avg_latency, jitter, "Успешно"
        elif len(latencies) == 1:
            return f"{latencies[0]:.0f} мс", "N/A", "Успешно"
        
        return "❌", "N/A", "Прокси не отвечает"

    async def _test_download_speed(self, port: int) -> (str, str):
        """Тест 3: Скорость скачивания тестового файла через прокси."""
        test_urls = [
            "http://speed.hetzner.de/10MB.bin",
            "http://ovh.net/files/10Mio.dat"
        ]
        
        for url in test_urls:
            cmd = f"curl --max-time 20 -o /dev/null -s -w '%{{speed_download}}' --socks5-hostname 127.0.0.1:{port} {url}"
            success, output = await run_shell_command(cmd)

            if success and output:
                try:
                    speed_bytes = float(output.replace(',', '.'))
                    if speed_bytes > 0:
                        if speed_bytes < 10240: # Если скорость меньше 10 КБ/с, показываем в КБ/с
                            speed_kb = speed_bytes / 1024
                            return f"{speed_kb:.0f} КБ/с", "Успешно"
                        else:
                            speed_mb = speed_bytes / 1024 / 1024
                            return f"{speed_mb:.2f} МБ/с", "Успешно"
                except (ValueError, TypeError):
                    continue
        
        return "❌", "Прокси не отвечает"
