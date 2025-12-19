#!/bin/sh

# entrypoint.sh: Скрипт для автоматической настройки и запуска Docker-контейнера

echo "🚀 Запуск entrypoint.sh..."

# 1. Проверка наличия переменных окружения
if [ -z "$BOT_TOKEN" ] || [ -z "$USER_ID" ]; then
  echo "❌ Ошибка: Переменные окружения BOT_TOKEN и USER_ID должны быть установлены."
  exit 1
fi

echo "✅ Переменные окружения найдены."

# 2. Создание конфигурационного файла kdw.cfg для Docker-окружения
CONFIG_FILE="/opt/etc/kdw/kdw.cfg"
echo "⚙️  Создание файла конфигурации $CONFIG_FILE для Docker..."

cat > $CONFIG_FILE << EOF
[telegram]
token = $BOT_TOKEN
access_ids = [$USER_ID]

[installer]
# Указываем путь к универсальному скрипту
script_path = /opt/etc/kdw/scripts/install.sh
# Указываем сетевой интерфейс, который существует в Docker
network_interface = eth0

[keenetic]
host = 127.0.0.1
port = 80
user = admin
password =

[shadowsocks]
path = /opt/etc/shadowsocks
file_mask = *.json
EOF

echo "✅ Файл конфигурации успешно создан."

# 3. Запуск бота
echo "🤖 Запуск KDW Bot..."
exec python3 kdw_bot.py
