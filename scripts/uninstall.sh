#!/bin/sh

# KDW Uninstaller (Safe Version)
# Удаляет компоненты, установленные ботом, НЕ затрагивая исходный код.

echo "--- KDW Uninstaller ---"

# --- 1. Остановка служб ---
echo "[1/4] Остановка всех служб..."
# Используем `if -f` для безопасного вызова, если файл не существует
if [ -f /opt/etc/init.d/S22shadowsocks ]; then /opt/etc/init.d/S22shadowsocks stop >/dev/null 2>&1; fi
if [ -f /opt/etc/init.d/S22trojan ]; then /opt/etc/init.d/S22trojan stop >/dev/null 2>&1; fi
if [ -f /opt/etc/init.d/S24v2ray ]; then /opt/etc/init.d/S24v2ray stop >/dev/null 2>&1; fi
if [ -f /opt/etc/init.d/S35tor ]; then /opt/etc/init.d/S35tor stop >/dev/null 2>&1; fi
if [ -f /opt/etc/init.d/S56dnsmasq ]; then /opt/etc/init.d/S56dnsmasq stop >/dev/null 2>&1; fi
echo "Службы остановлены."

# --- 2. Удаление файлов и директорий ---
echo "[2/4] Удаление конфигурационных файлов и скриптов..."
rm -f /opt/etc/init.d/S22shadowsocks
rm -f /opt/etc/init.d/S22trojan
rm -f /opt/etc/init.d/S24v2ray
rm -f /opt/etc/init.d/S35tor
rm -f /opt/etc/init.d/S56dnsmasq
rm -f /opt/etc/init.d/S99unblock
rm -f /opt/etc/init.d/S99kdwbot

# Удаляем только созданные конфиги и списки, а не всю папку /opt/etc/kdw
rm -rf /opt/etc/shadowsocks
rm -rf /opt/etc/trojan
rm -rf /opt/etc/v2ray
rm -rf /opt/etc/tor
rm -rf /opt/etc/unblock
rm -rf /opt/etc/dnsmasq.d
rm -f /opt/etc/kdw/kdw.cfg

echo "Файлы и директории удалены."

# --- 3. Удаление пакетов ---
echo "[3/4] Удаление пакетов через opkg..."
opkg remove shadowsocks-libev-ss-redir ipset dnsmasq-full trojan v2ray-core

echo "Пакеты удалены."

# --- 4. Очистка iptables (попытка) ---
echo "[4/4] Очистка правил iptables..."
ipset destroy unblock >/dev/null 2>&1
iptables -t nat -D PREROUTING -i br0 -m set --match-set unblock dst -p tcp -j REDIRECT --to-port 1080 >/dev/null 2>&1

echo "Очистка завершена."
echo ""
echo "--- Удаление KDW Bot успешно завершено! ---"
echo "Исходный код бота НЕ был затронут."

exit 0
