#!/bin/sh

# =================================================================
# KDW Firewall Rule Applier (Lists-Only Mode)
#
# Описание:
#   Применяет правила iptables для перенаправления трафика
#   через прокси только для доменов из списков.
#   Совместим с BusyBox ash.
# =================================================================

# --- Переменные ---
SCRIPT_DIR=$(dirname "$0")
LISTS_DIR="/opt/etc/kdw/lists"
PROXY_TYPES="shadowsocks trojan vmess"

# --- Функции ---
log() {
    echo "$1"
}

check_utils() {
    for util in iptables ipset; do
        if ! command -v "$util" >/dev/null 2>&1; then
            log "ОШИБКА: Утилита '$util' не найдена. Установите ее (opkg install $util)."
            exit 1
        fi
    done
}

# --- Основной код ---
check_utils

log "--- Применение правил Firewall для списков KDW ---"
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

# --- Шаг 3: Создание и наполнение ipset-списков ---
log "3. Создаю и наполняю ipset-списки..."
for PROXY in $PROXY_TYPES; do
    IPSET_NAME="kdw_${PROXY}_list"
    LIST_FILE="${LISTS_DIR}/${PROXY}.list"

    log " - Обработка для '$PROXY' (ipset: $IPSET_NAME)..."

    ipset create "$IPSET_NAME" hash:net -exist
    ipset flush "$IPSET_NAME"

    if [ -s "$LIST_FILE" ]; then
        grep -v -e '^$' -e '^#' "$LIST_FILE" | while IFS= read -r domain; do
            ipset add "$IPSET_NAME" "$domain"
        done
        log "   - ipset '$IPSET_NAME' наполнен из '$LIST_FILE'."
    else
        log "   - Файл списка '$LIST_FILE' не найден или пуст. ipset '$IPSET_NAME' оставлен пустым."
    fi
done
log ""

# --- Шаг 4: Создание правил iptables ---
log "4. Создаю правила iptables для перенаправления..."
for PROXY in $PROXY_TYPES; do
    IPSET_NAME="kdw_${PROXY}_list"

    PORT=""
    case "$PROXY" in
        "shadowsocks") PORT="1080" ;;
        "trojan")      PORT="10829" ;;
        "vmess")       PORT="10810" ;;
    esac

    if [ -z "$PORT" ]; then
        log " - Пропускаю '$PROXY': порт не определен."
        continue
    fi

    if ipset -L "$IPSET_NAME" | grep -q 'Number of entries: 0'; then
        log " - ipset '$IPSET_NAME' пуст, правило для порта $PORT не создается."
        continue
    fi

    log " - Создаю правило: трафик для доменов из '$IPSET_NAME' -> порт $PORT"
    iptables -t nat -A KDW_PROXY -p tcp -m set --match-set "$IPSET_NAME" dst -j REDIRECT --to-port "$PORT"
done
log ""

log "✅ Применение правил для списков завершено."
exit 0
