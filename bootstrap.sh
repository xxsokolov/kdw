#!/bin/sh

# KDW Bot Installer
# https://github.com/xxsokolov/KDW

# --- Functions ---
echo_step() {
  echo "➡️  $1"
}
echo_success() {
  echo "✅ $1"
}
echo_error() {
  echo "❌ $1"
  exit 1
}

# --- Start ---
echo_step "Запуск установщика KDW Bot..."
sleep 1

# --- Interactive Configuration ---
echo "Пожалуйста, введите данные для настройки бота:"
printf "1. Токен вашего Telegram бота (полученный от @BotFather): "
read BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
  echo_error "Токен не может быть пустым."
fi

printf "2. Ваш Telegram User ID (число, можно узнать у @userinfobot): "
read USER_ID
if [ -z "$USER_ID" ]; then
  echo_error "User ID не может быть пустым."
fi

# --- Validate Token ---
echo_step "Проверка токена бота..."
# Устанавливаем jq, если его нет
if ! command -v jq > /dev/null; then
  opkg update > /dev/null
  opkg install jq > /dev/null
fi
API_URL="https://api.telegram.org/bot$BOT_TOKEN/getMe"
RESPONSE=$(curl -s $API_URL)
OK_STATUS=$(echo $RESPONSE | jq -r '.ok')

if [ "$OK_STATUS" != "true" ]; then
  echo_error "Неверный токен. Telegram API вернул ошибку:"
  echo "$RESPONSE"
  exit 1
fi
BOT_NAME=$(echo $RESPONSE | jq -r '.result.first_name')
echo_success "Токен верный. Бот: $BOT_NAME"

# --- Installation ---
echo_step "Обновление списка пакетов opkg..."
opkg update > /dev/null
echo_step "Установка необходимых пакетов (python3, pip, git)..."
opkg install python3 python3-pip git > /dev/null

echo_step "Клонирование репозитория KDW Bot в /opt/etc/kdw..."
rm -rf /opt/etc/kdw
git clone https://github.com/xxsokolov/KDW.git /opt/etc/kdw > /dev/null

echo_step "Установка Python-библиотек из requirements.txt..."
pip3 install -r /opt/etc/kdw/requirements.txt > /dev/null

# --- Create Config File ---
echo_step "Создание конфигурационного файла kdw.cfg..."
CONFIG_FILE="/opt/etc/kdw/kdw.cfg"
cat > $CONFIG_FILE << EOF
[telegram]
token = $BOT_TOKEN
access_ids = [$USER_ID]

[installer]
# Указываем путь к универсальному скрипту
script_path = /opt/etc/kdw/scripts/install.sh
# Указываем сетевой интерфейс для Keenetic
network_interface = br0

[keenetic]
host = 127.0.0.1
port = 80
user = admin
password =

[shadowsocks]
path = /opt/etc/shadowsocks
file_mask = *.json
EOF
echo_success "Конфигурационный файл создан."

# --- Create Service ---
echo_step "Создание службы автозапуска S99kdwbot..."
SERVICE_FILE="/opt/etc/init.d/S99kdwbot"
cat > $SERVICE_FILE << EOF
#!/bin/sh
[ "\$1" != "start" ] && exit 0
cd /opt/etc/kdw
python3 kdw_bot.py &
EOF
chmod +x $SERVICE_FILE
echo_success "Служба создана."

# --- Final ---
echo_step "Запуск бота..."
$SERVICE_FILE start
echo_success "Установка и настройка завершены! Бот запущен."
echo "Можете начинать общение с ним в Telegram."
exit 0
