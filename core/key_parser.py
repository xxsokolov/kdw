import base64
from urllib.parse import urlparse, unquote
from typing import Union

def parse_shadowsocks_key(key_string: str) -> Union[dict, None]:
    """
    Парсит ключ в формате ss:// и возвращает словарь для JSON-конфига.
    Формат ключа: ss://<base64(method:password)>@<hostname>:<port>#<tag>
    """
    try:
        # Парсим URL
        parsed_url = urlparse(key_string)
        if parsed_url.scheme != 'ss':
            print(f"Ошибка парсинга Shadowsocks: Неверная схема URL. Ожидается 'ss://', получено '{parsed_url.scheme}://'.")
            return None

        # Декодируем userinfo (method:password)
        userinfo_b64 = parsed_url.username
        if not userinfo_b64:
            print("Ошибка парсинга Shadowsocks: Отсутствует информация о методе и пароле (base64-строка).")
            return None

        # Добиваем base64 до длины, кратной 4, если нужно
        userinfo_b64_padded = userinfo_b64 + '=' * (-len(userinfo_b64) % 4)
        try:
            decoded_userinfo = base64.b64decode(userinfo_b64_padded).decode('utf-8')
        except (base64.binascii.Error, UnicodeDecodeError):
            print(f"Ошибка парсинга Shadowsocks: Некорректная Base64-строка в информации о пользователе: '{userinfo_b64}'.")
            return None
        
        if ':' not in decoded_userinfo:
            print(f"Ошибка парсинга Shadowsocks: Неверный формат информации о пользователе. Ожидается 'метод:пароль', получено '{decoded_userinfo}'.")
            return None

        method, password = decoded_userinfo.split(':', 1)

        # Проверяем наличие хоста и порта
        if not parsed_url.hostname or not parsed_url.port:
            print(f"Ошибка парсинга Shadowsocks: Отсутствует хост или порт в URL: '{key_string}'.")
            return None

        # Собираем результат
        config = {
            "server": parsed_url.hostname,
            "server_port": parsed_url.port,
            "method": method,
            "password": password,
            "tag": unquote(parsed_url.fragment) if parsed_url.fragment else parsed_url.hostname
        }
        return config

    except Exception as e:
        # Общая ошибка, если что-то пошло не так, что не было поймано выше
        print(f"Неизвестная ошибка при парсинге Shadowsocks ключа: {e}. Ключ: '{key_string}'.")
        return None

# --- Заглушки для будущих парсеров ---

def parse_vmess_key(key_string: str) -> Union[dict, None]:
    """Парсит ключ в формате vmess://."""
    print("Парсинг Vmess еще не реализован.")
    return None

def parse_trojan_key(key_string: str) -> Union[dict, None]:
    """Парсинг Trojan еще не реализован."""
    print("Парсинг Trojan еще не реализован.")
    return None
