#!/bin/sh

# =================================================================
# KDW Firewall Rule Flusher
#
# Описание:
#   Этот скрипт находит и удаляет все правила iptables и
#   ipset-списки, созданные KDW ботом.
# =================================================================

# Список всех возможных типов прокси, которые могут создавать ipset'ы
PROXY_TYPES="shadowsocks trojan vmess"

# Порты, на которые перенаправляется трафик для каждого типа прокси
# Важно, чтобы они совпадали с теми, что будут в apply-скриптах
declare -A PROXY_PORTS=(
    ["shadowsocks"]="1080" # Пример, замените на реальный, если нужно
    ["trojan"]="10829"
    ["vmess"]="10810"
)

echo "Начинаю сброс правил Firewall для KDW..."
echo ""

# --- Шаг 1: Удаление правил iptables ---
for PROXY in $PROXY_TYPES; do
    IPSET_NAME="kdw_${PROXY}"
    PORT=${PROXY_PORTS[$PROXY]}

    if ipset -L "$IPSET_NAME" >/dev/null 2>&1; then
        echo "Найден ipset '$IPSET_NAME'. Удаляю связанные правила iptables..."

        # Формируем правило для поиска и удаления
        RULE_SPEC="-t nat -p tcp -m set --match-set $IPSET_NAME dst -j REDIRECT --to-port $PORT"

        # Удаляем правило, пока оно находится
        while iptables -C PREROUTING $RULE_SPEC >/dev/null 2>&1; do
            iptables -D PREROUTING $RULE_SPEC
            echo "  - Удалено правило для порта $PORT"
        done
    else
        echo "Ipset '$IPSET_NAME' не найден, пропуск."
    fi
    echo ""
done

# --- Шаг 2: Уничтожение ipset-списков ---
for PROXY in $PROXY_TYPES; do
    IPSET_NAME="kdw_${PROXY}"
    if ipset -L "$IPSET_NAME" >/dev/null 2>&1; then
        echo "Уничтожаю ipset '$IPSET_NAME'..."
        ipset destroy "$IPSET_NAME"
    fi
done

echo ""
echo "✅ Сброс правил Firewall для KDW завершен."
exit 0
