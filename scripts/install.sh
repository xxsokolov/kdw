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
# Проверяем, существует ли указанный интерфейс.
# Если нет, выводим предупреждение и пропускаем шаги, связанные с сетью.
if ! ip link show "$INTERFACE" > /dev/null 2>&1; then
    echo "ВНИМАНИЕ: Интерфейс '$INTERFACE' не найден. Пропускаю шаги настройки сети (iptables)."
    NETWORK_SETUP_ENABLED=false
else
    NETWORK_SETUP_ENABLED=true
fi

# --- 3. Установка ---
echo "[1/3] Установка пакетов..."
# Здесь будет логика установки пакетов (opkg/apk)
# opkg update
# opkg install ipset dnsmasq ...
sleep 2
echo "Пакеты 'установлены'."
echo ""

echo "[2/3] Настройка системных файлов..."
if [ "$NETWORK_SETUP_ENABLED" = true ]; then
    echo "Настраиваю iptables для интерфейса $INTERFACE..."
    # Здесь будет реальная логика настройки iptables
    # iptables -t nat -A PREROUTING -i $INTERFACE ...
    sleep 2
    echo "iptables 'настроен'."
else
    echo "Пропускаю настройку iptables."
fi
echo ""


echo "[3/3] Создание init-скрипта..."
# Создаем файл-маркер, по которому бот определяет, что система установлена.
touch /opt/etc/init.d/S99unblock
chmod +x /opt/etc/init.d/S99unblock
sleep 1
echo "Init-скрипт 'создан'."
echo ""

echo "--- Установка успешно завершена! ---"

exit 0
