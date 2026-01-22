#!/bin/sh

# =================================================================
# KDW Firewall Rule Flusher
#
# Описание:
#   Полностью удаляет все правила iptables и ipset,
#   созданные KDW.
#   Совместим с BusyBox ash.
# =================================================================

# --- Функции ---
log() {
    echo "$1"
}

check_utils() {
    for util in iptables ipset; do
        if ! command -v "$util" >/dev/null 2>&1; then
            log "ИНФО: Утилита '$util' не найдена. Пропускаю очистку для нее."
            # Не выходим с ошибкой, так как при удалении это нормально
        fi
    done
}

# --- Основной код ---
check_utils

log "--- Очистка правил Firewall KDW ---"

# --- Шаг 1: Удаление правил из PREROUTING ---
if command -v "iptables" >/dev/null 2>&1; then
    log "1. Удаляю ссылки на KDW_PROXY из цепочки PREROUTING..."
    # Получаем список номеров правил, которые ссылаются на KDW_PROXY
    while true; do
        RULE_NUM=$(iptables -t nat -L PREROUTING --line-numbers | grep 'KDW_PROXY' | awk '{print $1}' | head -n 1)
        if [ -z "$RULE_NUM" ]; then
            break
        fi
        log " - Удаляю правило номер $RULE_NUM..."
        iptables -t nat -D PREROUTING "$RULE_NUM"
    done
fi

# --- Шаг 2: Очистка и удаление цепочки KDW_PROXY ---
if command -v "iptables" >/dev/null 2>&1; then
    if iptables -t nat -L KDW_PROXY >/dev/null 2>&1; then
        log "2. Очищаю и удаляю цепочку KDW_PROXY..."
        iptables -t nat -F KDW_PROXY
        iptables -t nat -X KDW_PROXY
    else
        log "2. Цепочка KDW_PROXY не найдена, пропускаю."
    fi
fi

# --- Шаг 3: Удаление ipset-списков ---
if command -v "ipset" >/dev/null 2>&1; then
    log "3. Удаляю все ipset-списки KDW..."
    # Находим все списки, начинающиеся с "kdw_"
    ipset list -n | grep '^kdw_' | while read -r set_name; do
        log " - Удаляю ipset '$set_name'..."
        ipset destroy "$set_name"
    done
fi

log ""
log "✅ Очистка завершена."
exit 0
