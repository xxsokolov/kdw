import unittest
from core.key_parser import parse_shadowsocks_key

class TestKeyParsing(unittest.TestCase):

    def test_parse_shadowsocks_valid_basic(self):
        """Тест на корректный парсинг простого валидного ss:// ключа."""
        ss_key = "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@example.com:8388#MyServer"
        expected = {
            "server": "example.com",
            "server_port": 8388,
            "method": "aes-256-gcm",
            "password": "password",
            "tag": "MyServer"
        }
        result = parse_shadowsocks_key(ss_key)
        self.assertEqual(result, expected)

    def test_parse_shadowsocks_valid_with_url_encoded_tag(self):
        """Тест на парсинг ключа с URL-кодированными символами в теге."""
        ss_key = "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@example.com:8388#My%20Server%20(DE)"
        expected = {
            "server": "example.com",
            "server_port": 8388,
            "method": "aes-256-gcm",
            "password": "password",
            "tag": "My Server (DE)"
        }
        result = parse_shadowsocks_key(ss_key)
        self.assertEqual(result, expected)

    def test_parse_shadowsocks_no_tag(self):
        """Тест на парсинг ключа без тега (используется hostname)."""
        ss_key = "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@example.com:8388"
        expected = {
            "server": "example.com",
            "server_port": 8388,
            "method": "aes-256-gcm",
            "password": "password",
            "tag": "example.com" # Тег должен быть равен хосту
        }
        result = parse_shadowsocks_key(ss_key)
        self.assertEqual(result, expected)

    def test_parse_shadowsocks_invalid_scheme(self):
        """Тест на обработку ключа с неверной схемой."""
        ss_key = "http://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@example.com:8388"
        result = parse_shadowsocks_key(ss_key)
        self.assertIsNone(result)

    def test_parse_shadowsocks_invalid_base64(self):
        """Тест на обработку ключа с некорректным base64."""
        ss_key = "ss://invalid-base64@example.com:8388"
        result = parse_shadowsocks_key(ss_key)
        self.assertIsNone(result)

    def test_parse_shadowsocks_malformed_userinfo(self):
        """Тест на обработку ключа с некорректным userinfo (без двоеточия)."""
        # base64('justmethod') -> anVzdG1ldGhvZA==
        ss_key = "ss://anVzdG1ldGhvZA==@example.com:8388"
        result = parse_shadowsocks_key(ss_key)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
