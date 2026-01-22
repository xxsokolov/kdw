#!/bin/sh

# =================================================================
# KDW Firewall Rule Applier (All-Traffic Mode)
#
# Описание:
#   Применяет правила iptables для перенаправления всего
#   трафика роутера через указанный прокси.
#   Совместим с BusyBox ash.
# =================================================================

# --- Переменные ---
SCRIPT_DIR=$(dirname "$0")

# --- Функции ---
log() {
    echo "$1"
}

check_utils() {
    if ! command -v "iptables" >/dev/null 2>&1; then
        log "ОШИБКА: Утилита 'iptables' не найдена. Установите ее (opkg install iptables)."
        exit 1
    fi
}

# --- Проверка аргументов ---
if [ -z "$1" ] || [ -z "$2" ]; then
    log "ОШИБКА: Недостаточно аргументов."
    log "Использование: $0 <proxy_type> <port>"
    exit 1
fi

PROXY_TYPE=$1
PROXY_PORT=$2

# --- Основной код ---
check_utils

log "--- Применение правил Firewall для всего трафика через $PROXY_TYPE ---"
log ""

# --- Шаг 1: Полная очистка старых правил ---
log "1. Выполняю полную очистку предыдущих правил KDW..."
if [ -f "${SCRIPT_DIR}/kdw_flush_proxy_rules.sh" ]; then
    sh "${SCRIPT_DIR}/kdw_flush_proxy_rules.sh"
else
    log "ОШИБКА: Скрипт очистки kdw_flush_proxy_rules.sh не найден!"
    exit 1
fi
log ""

# --- Шаг 2: Создание общей цепочки KDW ---
log "2. Создаю общую цепочку KDW_PROXY..."
iptables -t nat -N KDW_PROXY 2>/dev/null
iptables -t nat -C PREROUTING -j KDW_PROXY >/dev/null 2>&1 || iptables -t nat -I PREROUTING 1 -j KDW_PROXY
log ""

# --- Шаг 3: Создание правил для перенаправления всего трафика ---
log "3. Создаю правила для перенаправления всего трафика на порт $PROXY_PORT..."

# Исключаем локальные сети, чтобы не было зацикливания
EXCLUDE_NETS="0.0.0.0/8 10.0.0.0/8 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 224.0.0.0/4 240.0.0.0/4"

for net in $EXCLUDE_NETS; do
    log " - Исключаю сеть $net"
    iptables -t nat -A KDW_PROXY -d "$net" -j RETURN
done

log " - Перенаправляю остальной TCP трафик на порт $PROXY_PORT"
iptables -t nat -A KDW_PROXY -p tcp -j REDIRECT --to-port "$PROXY_PORT"
log ""

log "✅ Применение правил для всего трафика завершено."
exit 0
