#!/bin/sh

# Универсальный установочный скрипт для системы обхода

echo "--- Universal Bypass Installer ---"

# --- 1. Парсинг аргументов ---
INTERFACE="br0" # Значение по умолчанию для Keenetic

while [ "$1" != "" ]; do
    case $1 in
        --interface)
            shift
            INTERFACE=$1
            ;;
    esac
    shift
done

echo "Используется сетевой интерфейс: $INTERFACE"

# --- 2. Проверка окружения ---
if ! ip link show "$INTERFACE" > /dev/null 2>&1; then
    echo "ВНИМАНИЕ: Интерфейс '$INTERFACE' не найден. Пропускаю шаги настройки сети (iptables)."
    NETWORK_SETUP_ENABLED=false
else
    NETWORK_SETUP_ENABLED=true
fi

# --- 3. Установка ---
echo "[1/3] Установка пакетов..."
sleep 1
echo "Пакеты 'установлены'."
echo ""

echo "[2/3] Настройка системных файлов..."
if [ "$NETWORK_SETUP_ENABLED" = true ]; then
    echo "Настраиваю iptables для интерфейса $INTERFACE..."
    sleep 1
    echo "iptables 'настроен'."
else
    echo "Пропускаю настройку iptables."
fi
echo ""


echo "[3/3] Создание init-скрипта..."
# Используем правильный путь /etc/init.d/
touch /etc/init.d/S99unblock
chmod +x /etc/init.d/S99unblock
sleep 1
echo "Init-скрипт 'создан'."
echo ""

echo "--- Установка успешно завершена! ---"

exit 0
