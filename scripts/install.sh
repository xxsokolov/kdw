#!/bin/sh

# KDW Installer
# Устанавливает и настраивает компоненты для системы обхода блокировок.

echo "--- KDW Installer ---"

# --- 0. Проверка системы ---
if ! command -v opkg > /dev/null; then
    echo "❌ Ошибка: команда 'opkg' не найдена. Убедитесь, что Entware установлена."
    exit 1
fi

# --- 1. Установка пакетов ---
echo "[1/5] Обновление списка пакетов opkg..."
opkg update

echo "[2/5] Установка минимально необходимых пакетов..."
# dnsmasq-full - для поддержки ipset
# ipset - для управления списками IP
# shadowsocks-libev-ss-redir - для "прозрачного" проксирования
opkg install dnsmasq-full ipset shadowsocks-libev-ss-redir

# --- 2. Создание структуры директорий и файлов ---
echo "[3/5] Создание структуры директорий и файлов..."
mkdir -p /opt/etc/unblock
mkdir -p /opt/etc/dnsmasq.d
mkdir -p /opt/etc/shadowsocks

# Создаем пустые файлы списков, если их нет
touch /opt/etc/unblock/unblocksh.txt
touch /opt/etc/unblock/unblocktor.txt

echo "Структура директорий создана."

# --- 3. Настройка dnsmasq ---
echo "[4/5] Настройка dnsmasq..."

# Убеждаемся, что dnsmasq будет читать конфиги из dnsmasq.d
if ! grep -q "conf-dir=/opt/etc/dnsmasq.d" /opt/etc/dnsmasq.conf; then
    echo "Добавляем conf-dir в dnsmasq.conf..."
    echo "conf-dir=/opt/etc/dnsmasq.d" >> /opt/etc/dnsmasq.conf
fi

# Создаем конфиг, который связывает домены из unblocksh.txt с ipset'ом 'unblock'
cat > /opt/etc/dnsmasq.d/unblock.conf << EOF
# Отправлять домены из unblocksh.txt в ipset 'unblock'
ipset=/unblocksh.txt/unblock
EOF

echo "Конфигурация dnsmasq создана."

# --- 4. Настройка Shadowsocks ---
echo "[5/5] Настройка Shadowsocks..."

# Заменяем ss-local на ss-redir в init-скрипте
# Это ключевой шаг для включения "прозрачного" проксирования
sed -i 's/ss-local/ss-redir/g' /etc/init.d/S22shadowsocks

echo "Shadowsocks настроен для работы в режиме редиректа."

# --- 5. Создание init-скрипта для iptables ---
# Мы не создаем S99unblock напрямую, так как он будет создан ботом
# при первом запуске. Вместо этого, мы создаем файл-маркер,
# который говорит боту, что установка завершена.
touch /etc/init.d/S99unblock

echo ""
echo "--- Установка базовых компонентов успешно завершена! ---"
echo "Финальная настройка (iptables) будет выполнена ботом."

exit 0
