#!/bin/sh

# =================================================================
# KDW Firewall Rule Applier (Lists-Only Mode)
#
# Описание:
#   Применяет правила iptables для перенаправления трафика
#   через прокси только для доменов из списков.
# =================================================================

# Директория со скриптами
SCRIPT_DIR=$(dirname "$0")

# Директория со списками доменов
LISTS_DIR="/opt/etc/kdw/lists"

# Список всех возможных типов прокси
PROXY_TYPES="shadowsocks trojan vmess"

# Ассоциативный массив "тип_прокси -> порт"
declare -A PROXY_PORTS=(
    ["shadowsocks"]="1080" # Пример, ss-redir обычно слушает этот порт
    ["trojan"]="10829"
    ["vmess"]="10810"
)

echo "--- Применение правил Firewall для списков KDW ---"
echo ""

# --- Шаг 1: Полная очистка старых правил ---
echo "1. Выполняю полную очистку предыдущих правил KDW..."
sh "${SCRIPT_DIR}/kdw_flush_proxy_rules.sh"
echo ""

# --- Шаг 2: Создание и наполнение ipset-списков ---
echo "2. Создаю и наполняю ipset-списки..."
for PROXY in $PROXY_TYPES; do
    IPSET_NAME="kdw_${PROXY}"
    LIST_FILE="${LISTS_DIR}/${PROXY}.list"

    echo " - Обработка для '$PROXY' (ipset: $IPSET_NAME)..."

    # Создаем ipset
    ipset create "$IPSET_NAME" hash:net -exist

    # Наполняем его, если файл списка существует
    if [ -f "$LIST_FILE" ]; then
        if [ -s "$LIST_FILE" ]; then # Проверяем, что файл не пустой
            # Используем `grep` для удаления пустых строк и комментариев
            grep -v -e '^$' -e '^#' "$LIST_FILE" | while IFS= read -r domain; do
                ipset add "$IPSET_NAME" "$domain"
            done
            echo "   - ipset '$IPSET_NAME' наполнен из '$LIST_FILE'."
        else
            echo "   - Файл списка '$LIST_FILE' пуст. ipset создан, но оставлен пустым."
        fi
    else
        echo "   - Файл списка '$LIST_FILE' не найден. ipset создан, но оставлен пустым."
    fi
done
echo ""

# --- Шаг 3: Создание правил iptables ---
echo "3. Создаю правила iptables для перенаправления..."
for PROXY in $PROXY_TYPES; do
    IPSET_NAME="kdw_${PROXY}"
    PORT=${PROXY_PORTS[$PROXY]}

    # Проверяем, есть ли хоть одна запись в ipset. Если нет, правило создавать бессмысленно.
    if ipset -L "$IPSET_NAME" | grep -q 'Number of entries: 0'; then
        echo " - ipset '$IPSET_NAME' пуст, правило для порта $PORT не создается."
        continue
    fi

    echo " - Создаю правило: трафик из '$IPSET_NAME' -> порт $PORT"

    # Формируем правило
    RULE_SPEC="-t nat -p tcp -m set --match-set $IPSET_NAME dst -j REDIRECT --to-port $PORT"

    # Добавляем правило, если его еще нет (хотя после flush его быть не должно)
    if ! iptables -C PREROUTING $RULE_SPEC >/dev/null 2>&1; then
        iptables -I PREROUTING 1 $RULE_SPEC
    fi
done
echo ""

echo "✅ Применение правил для списков завершено."
exit 0
