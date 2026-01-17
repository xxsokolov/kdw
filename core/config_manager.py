import os
import glob
import json
import base64
from urllib.parse import urlparse, unquote, parse_qs
from configparser import ConfigParser

from core.log_utils import log

class ConfigManager:
    """
    Управляет конфигурационными файлами служб (Shadowsocks, Trojan и т.д.).
    """
    def __init__(self, service_name: str):
        self.service_name = service_name
        
        # Читаем основной конфиг для получения путей
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(script_dir, '..', 'kdw.cfg')
        self.config = ConfigParser()
        self.config.read(config_file)

        # Путь к директории с конфигами конкретного сервиса
        self.path = self.config.get(service_name, 'path', fallback=f'/opt/etc/{service_name}')
        
        # Путь к нашей централизованной символической ссылке
        link_prefix = 'ss' if self.service_name == 'shadowsocks' else self.service_name[:2]
        self.active_config_link = f"/opt/etc/kdw/{link_prefix}.active.json"
        
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def get_configs(self) -> list:
        """Возвращает список всех .json файлов конфигурации."""
        return glob.glob(os.path.join(self.path, '*.json'))

    def get_active_config(self) -> str | None:
        """
        Возвращает реальный путь к активному конфигу, читая символическую ссылку.
        """
        if os.path.islink(self.active_config_link):
            try:
                return os.path.realpath(self.active_config_link)
            except Exception as e:
                log.error(f"Ошибка чтения символической ссылки {self.active_config_link}: {e}")
        return None

    def set_active_config(self, config_path: str) -> bool:
        """
        Устанавливает выбранный конфиг как активный.
        В боте эта логика выполняется напрямую через shell_utils.run_shell_command,
        но этот метод оставлен для консистентности и возможного использования в будущем.
        """
        if not os.path.exists(config_path):
            log.error(f"Конфиг {config_path} не найден.")
            return False
        try:
            # Удаляем старую ссылку, если она есть
            if os.path.lexists(self.active_config_link):
                os.remove(self.active_config_link)
            
            os.symlink(config_path, self.active_config_link)
            log.info(f"Активным установлен конфиг: {config_path}")
            return True
        except Exception as e:
            log.error(f"Ошибка создания символической ссылки: {e}")
            return False

    def read_config(self, config_path: str) -> dict | None:
        """Читает и возвращает содержимое JSON-конфига."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Ошибка чтения конфига {config_path}: {e}")
            return None

    def delete_config(self, config_path: str) -> bool:
        """Удаляет файл конфигурации."""
        try:
            # Если удаляемый конфиг был активным, удаляем и ссылку
            if os.path.islink(self.active_config_link) and os.path.realpath(self.active_config_link) == config_path:
                os.remove(self.active_config_link)
            
            os.remove(config_path)
            log.info(f"Удален конфиг: {config_path}")
            return True
        except Exception as e:
            log.error(f"Ошибка удаления конфига {config_path}: {e}")
            return False

    def create_from_url(self, url: str) -> str | None:
        """
        Парсит URL, создает или обновляет конфиг.
        Возвращает статус: "created", "updated", "skipped" или None.
        """
        if url.startswith('ss://'):
            return self._create_shadowsocks_from_url(url)
        if url.startswith('trojan://'):
            return self._create_trojan_from_url(url)
        log.error(f"Неподдерживаемый формат URL: {url}")
        return None

    def _create_shadowsocks_from_url(self, url: str) -> str | None:
        """Парсит ss:// URL и создает/обновляет конфиг."""
        try:
            main_part = url[5:].split('#', 1)[0]
            
            try:
                user_info_encoded, server_info = main_part.split('@', 1)
            except ValueError:
                log.error(f"Неверный формат URL: отсутствует символ '@'. URL: {url}")
                return None

            try:
                padding = '=' * (4 - len(user_info_encoded) % 4)
                user_info_decoded = base64.urlsafe_b64decode(user_info_encoded + padding).decode('utf-8')
                method, password = user_info_decoded.split(':', 1)
            except Exception as e:
                log.error(f"Ошибка декодирования Base64 или разделения method:password: {e}")
                return None

            try:
                server, port = server_info.split(':', 1)
            except ValueError:
                log.error(f"Неверный формат server:port: {server_info}")
                return None

            filename = f"{server}_{port}.json"
            filepath = os.path.join(self.path, filename)
            
            local_port = self.config.getint('shadowsocks', 'local_port', fallback=1080)

            new_config = {
                "server": server,
                "server_port": int(port),
                "local_port": local_port,
                "method": method,
                "password": password,
                "timeout": 600,
                "fast_open": True,
                "mode": "tcp_and_udp"
            }
            
            if os.path.exists(filepath):
                existing_config = self.read_config(filepath)
                if existing_config == new_config:
                    return "skipped"
                
                with open(filepath, 'w') as f:
                    json.dump(new_config, f, indent=4)
                log.info(f"Обновлен конфиг Shadowsocks: {filepath}")
                return "updated"
            else:
                with open(filepath, 'w') as f:
                    json.dump(new_config, f, indent=4)
                log.info(f"Создан новый конфиг Shadowsocks: {filepath}")
                return "created"

        except Exception as e:
            log.error(f"Общая ошибка парсинга Shadowsocks URL: {e}")
            return None

    def _create_trojan_from_url(self, url: str) -> str | None:
        """Парсит trojan:// URL и создает/обновляет конфиг."""
        try:
            # Ручной парсинг вместо urlparse
            main_part = url[9:]
            
            # Отделяем якорь
            if '#' in main_part:
                main_part = main_part.split('#', 1)[0]

            # Отделяем параметры
            if '?' in main_part:
                main_part, query_part = main_part.split('?', 1)
                params = parse_qs(query_part)
            else:
                params = {}

            # Разбираем основную часть
            password, server_info = main_part.split('@', 1)
            server, port = server_info.split(':', 1)

            sni = params.get('sni', [server])[0]
            
            filename = f"{server}_{port}.json"
            filepath = os.path.join(self.path, filename)

            local_port = self.config.getint('trojan', 'local_port', fallback=1081)

            new_config = {
                "run_type": "client",
                "local_addr": "127.0.0.1",
                "local_port": local_port,
                "remote_addr": server,
                "remote_port": int(port),
                "password": [password],
                "ssl": {
                    "sni": sni
                }
            }

            if os.path.exists(filepath):
                existing_config = self.read_config(filepath)
                if existing_config == new_config:
                    return "skipped"
                
                with open(filepath, 'w') as f:
                    json.dump(new_config, f, indent=4)
                log.info(f"Обновлен конфиг Trojan: {filepath}")
                return "updated"
            else:
                with open(filepath, 'w') as f:
                    json.dump(new_config, f, indent=4)
                log.info(f"Создан новый конфиг Trojan: {filepath}")
                return "created"

        except Exception as e:
            log.error(f"Ошибка парсинга Trojan URL: {e}")
            return None
