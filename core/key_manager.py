import json
import os
from configparser import ConfigParser
from typing import Tuple
from . import key_parser
from .service_manager import ServiceManager

class KeyManager:
    def __init__(self, config_file="kdw.cfg"):
        self.config = ConfigParser()
        self.config.read(config_file, encoding='utf-8')
        self.service_manager = ServiceManager()

    async def update_shadowsocks_config(self, key_string: str) -> Tuple[bool, str]:
        """
        Обновляет конфигурацию Shadowsocks на основе ss:// ключа.
        Возвращает (True, "Успех") или (False, "Текст ошибки").
        """
        # 1. Парсим ключ
        parsed_data = key_parser.parse_shadowsocks_key(key_string)
        if not parsed_data:
            return False, "Не удалось распознать формат ключа Shadowsocks."

        # 2. Дополняем данными по умолчанию из kdw.cfg
        try:
            full_config = {
                "server": parsed_data["server"],
                "server_port": parsed_data["server_port"],
                "method": parsed_data["method"],
                "password": parsed_data["password"],
                "mode": self.config.get('shadowsocks', 'mode', fallback='tcp_and_udp'),
                "timeout": self.config.getint('shadowsocks', 'timeout', fallback=86400),
                "local_address": self.config.get('shadowsocks', 'local_address', fallback='::'),
                "local_port": self.config.getint('shadowsocks', 'local_port', fallback=1080),
                "fast_open": self.config.getboolean('shadowsocks', 'fast_open', fallback=False),
                "ipv6_first": self.config.getboolean('shadowsocks', 'ipv6_first', fallback=True),
            }
            
            config_dir = self.config.get('shadowsocks', 'path', fallback='/opt/etc/shadowsocks')
            os.makedirs(config_dir, exist_ok=True)
            file_name = f"{parsed_data['tag']}.json"
            file_path = os.path.join(config_dir, file_name)

        except Exception as e:
            return False, f"Ошибка чтения конфигурации: {e}"

        # 3. Сохраняем JSON файл
        try:
            with open(file_path, 'w') as f:
                json.dump(full_config, f, indent=4)
        except Exception as e:
            return False, f"Не удалось записать файл конфигурации: {e}"

        # 4. Перезапускаем службу
        success, message = await self.service_manager.restart_service("shadowsocks")
        if not success:
            return False, f"Конфиг обновлен, но службу перезапустить не удалось: {message}"

        return True, f"Конфигурация Shadowsocks '{file_name}' успешно обновлена и служба перезапущена."

    # --- Заглушки для других типов ключей ---
    async def update_vmess_config(self, key_string: str) -> Tuple[bool, str]:
        return False, "Управление ключами Vmess еще не реализовано."

    async def update_trojan_config(self, key_string: str) -> Tuple[bool, str]:
        return False, "Управление ключами Trojan еще не реализовано."
