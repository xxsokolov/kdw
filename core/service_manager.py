import asyncio
import glob
import os
import re
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

    async def restart_service(self, service_name: str) -> (bool, str):
        """Перезапускает одну службу."""
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

        logger.info(f"Перезапуск службы: {script_path}")
        success, output = await run_shell_command(f'sh -c "{script_path} restart"')

        if success:
            logger.info(f"Служба {service_name} успешно перезапущена.")
            return True, f"{service_name}: ✅ перезапущена"
        else:
            logger.error(f"Ошибка при перезапуске {service_name}: {output}")
            return False, f"{service_name}: ❌ ошибка\n`{output}`"

    async def restart_all_services(self) -> str:
        """Перезапускает все известные службы и возвращает отчет."""
        tasks = [self.restart_service(name) for name in self.service_map.keys()]
        results = await asyncio.gather(*tasks)
        
        report = [message for _, message in results if "не найден" not in message]
        return "\n".join(report) if report else "Не найдено активных служб для перезапуска."

    async def diagnose_all_proxies(self, service_name: str) -> List[Dict[str, Any]]:
        """
        Выполняет диагностику всех конфигов для указанного сервиса.
        """
        manager = ConfigManager(service_name)
        all_configs = manager.get_configs()
        active_config_path = manager.get_active_config()

        if not all_configs:
            return [{"error": f"Конфигурации для {service_name} не найдены."}]

        results = []
        for config_path in all_configs:
            result = await self._diagnose_single_proxy(service_name, config_path, active_config_path)
            results.append(result)
        
        return results

    async def _diagnose_single_proxy(self, service_name: str, config_path: str, active_config_path: str) -> Dict[str, Any]:
        """Выполняет полную диагностику одного прокси-конфига."""
        manager = ConfigManager(service_name)
        config = manager.read_config(config_path)
        if not config:
            return {"error": f"Не удалось прочитать конфиг: {os.path.basename(config_path)}"}

        server_host = config.get("remote_addr") if service_name == 'trojan' else config.get("server")
        is_active = (config_path == active_config_path)

        ping_result, ping_details = await self._test_direct_ping(server_host)
        
        if service_name == 'shadowsocks':
            latency_result, latency_details, speed_result, speed_details = await self._test_shadowsocks_proxy(config_path)
        elif service_name == 'trojan':
            latency_result, latency_details, speed_result, speed_details = await self._test_trojan_proxy(config_path)
        else:
            latency_result, latency_details, speed_result, speed_details = "🤷‍♂️", "не поддерживается", "🤷‍♂️", "не поддерживается"

        return {
            "name": os.path.basename(config_path),
            "server": server_host,
            "is_active": is_active,
            "ping": ping_result,
            "ping_details": ping_details,
            "latency": latency_result,
            "latency_details": latency_details,
            "speed": speed_result,
            "speed_details": speed_details,
        }

    async def _test_direct_ping(self, host: str) -> (str, str):
        """Тест 1: Пинг до хоста прокси-сервера напрямую."""
        if not host: return "⚠️", "Хост не указан"
        success, output = await run_shell_command(f"ping -c 3 -W 2 {host}")
        if not success:
            return "❌", "Хост недоступен"
        
        match = re.search(r"min/avg/max = [\d.]+/([\d.]+)/[\d.]+", output)
        if match:
            return f"{float(match.group(1)):.0f} мс", "Успешно"
        return "⚠️", "Не удалось определить время"

    async def _test_shadowsocks_proxy(self, config_path: str) -> (str, str, str, str):
        """Запускает временный ss-local и тестирует через него."""
        diag_port = 1099
        cmd = f"ss-local -c {config_path} -b 127.0.0.1 -l {diag_port}"
        return await self._run_proxy_tests(cmd, diag_port)

    async def _test_trojan_proxy(self, config_path: str) -> (str, str, str, str):
        """Тестирует конфиг Trojan с помощью встроенного теста."""
        cmd = f"trojan -t -c {config_path}"
        success, output = await run_shell_command(cmd)
        
        if success:
            return "✅", "Успешно", "N/A", "N/A"
        else:
            # Ищем причину ошибки в выводе
            if "authentication failed" in output:
                details = "ошибка аутентификации"
            elif "certificate expired" in output:
                details = "сертификат истек"
            else:
                details = "неизвестная ошибка"
            return "❌", details, "❌", details

    async def _run_proxy_tests(self, cmd: str, port: int) -> (str, str, str, str):
        """Общая логика для запуска временного прокси и выполнения тестов."""
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        
        try:
            await asyncio.sleep(2)

            if proc.returncode is not None:
                 stderr = await proc.stderr.read()
                 error_msg = stderr.decode().strip()
                 logger.error(f"Прокси-клиент не запустился: {error_msg}")
                 return "❌", "клиент не запустился", "❌", "клиент не запустился"

            latency_result, latency_details = await self._test_proxy_latency(port)
            speed_result, speed_details = await self._test_download_speed(port)

            return latency_result, latency_details, speed_result, speed_details

        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    async def _test_proxy_latency(self, port: int) -> (str, str):
        """Тест 2: Задержка до google.com через прокси."""
        cmd = f"curl --max-time 10 -o /dev/null -s -w '%{{time_starttransfer}}' --socks5-hostname 127.0.0.1:{port} https://www.google.com"
        success, output = await run_shell_command(cmd)
        
        if success and output:
            try:
                latency_ms = float(output.replace(',', '.')) * 1000
                if latency_ms > 0:
                    return f"{latency_ms:.0f} мс", "Успешно"
            except (ValueError, TypeError):
                return "⚠️", "Неверный формат ответа"
        return "❌", "Прокси не отвечает"

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
