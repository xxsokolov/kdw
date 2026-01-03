import os
import glob
import json
import base64
from urllib.parse import urlparse
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
        config = ConfigParser()
        config.read(config_file)

        # Путь к директории с конфигами конкретного сервиса
        self.path = config.get(service_name, 'path', fallback=f'/opt/etc/{service_name}')
        
        # Путь к нашей централизованной символической ссылке
        # Имя сервиса используется для формирования уникального имени ссылки, например, ss.active.json
        self.active_config_link = f"/opt/etc/kdw/{service_name[:2]}.active.json"
        
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
        Парсит URL, создает и сохраняет новый конфиг.
        Возвращает путь к созданному файлу или None в случае ошибки.
        """
        if self.service_name == 'shadowsocks':
            return self._create_shadowsocks_from_url(url)
        # Здесь можно будет добавить поддержку других типов
        log.error(f"Создание из URL для '{self.service_name}' не поддерживается.")
        return None

    def _create_shadowsocks_from_url(self, url: str) -> str | None:
        """Парсит ss:// URL и создает конфиг."""
        try:
            # Базовая валидация
            if not url.startswith('ss://'):
                return None

            parts = urlparse(url)
            
            # Имя файла будет основано на имени хоста и порта
            filename = f"{parts.hostname}_{parts.port}.json"
            filepath = os.path.join(self.path, filename)
            
            # Декодирование информации из URL
            user_info = base64.urlsafe_b64decode(parts.username + '==').decode('utf-8')
            method, password = user_info.split(':', 1)
            
            sh_config = {
                "server": parts.hostname,
                "server_port": parts.port,
                "method": method,
                "password": password,
                "timeout": 600,
                "fast_open": True,
                "mode": "tcp_and_udp"
            }
            
            with open(filepath, 'w') as f:
                json.dump(sh_config, f, indent=4)
            
            log.info(f"Создан новый конфиг Shadowsocks: {filepath}")
            return filepath
        except Exception as e:
            log.error(f"Ошибка парсинга Shadowsocks URL: {e}")
            return None
