#!/bin/sh

# KDW Bot Installer (Bootstrap)
# https://github.com/xxsokolov/KDW
#
# Этот скрипт скачивает репозиторий и запускает основной установщик (postinst),
# передавая ему все полученные аргументы.

# --- Functions ---
echo_step() {
  echo "➡️  $1"
}
echo_error() {
  echo "❌ $1"
  exit 1
}

# --- Start ---
echo_step "Запуск bootstrap-установщика KDW Bot..."
sleep 1

# --- Installation ---
echo_step "Проверка и установка зависимостей (git, jq, curl)..."
opkg update > /dev/null
if ! command -v git > /dev/null; then opkg install git; fi
if ! command -v jq > /dev/null; then opkg install jq; fi
if ! command -v curl > /dev/null; then opkg install curl; fi

echo_step "Клонирование репозитория KDW Bot в /opt/etc/kdw..."
rm -rf /opt/etc/kdw
git clone https://github.com/xxsokolov/KDW.git /opt/etc/kdw

POSTINST_SCRIPT="/opt/etc/kdw/opkg/postinst"

if [ ! -f "$POSTINST_SCRIPT" ]; then
    echo_error "Не удалось найти основной скрипт установки $POSTINST_SCRIPT"
fi

# --- Run Post-Install Script ---
echo_step "Запуск основного скрипта установки..."
chmod +x "$POSTINST_SCRIPT"

# Передаем все аргументы, полученные bootstrap.sh, в postinst
sh "$POSTINST_SCRIPT" "$@"

exit 0
