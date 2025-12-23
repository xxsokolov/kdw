#!/bin/sh

# KDW Bot Installer (Bootstrap)
# https://github.com/xxsokolov/KDW
#
# Этот скрипт скачивает архив с исходным кодом, распаковывает его
# и запускает основной установщик (postinst).

# --- Functions ---
echo_step() {
  echo "➡️  $1"
}
echo_error() {
  echo "❌ $1"
  exit 1
}

# --- Default values ---
ACTION="install" # Действие по умолчанию

# --- Argument Parsing ---
POSTINST_ARGS=""
while [ "$1" != "" ]; do
    case $1 in
        --install)
            ACTION="install"
            ;;
        --reinstall)
            ACTION="reinstall"
            ;;
        --uninstall)
            ACTION="uninstall"
            ;;
        *)
            POSTINST_ARGS="$POSTINST_ARGS $1"
            ;;
    esac
    shift
done

# --- Action: Uninstall ---
if [ "$ACTION" = "uninstall" ]; then
    echo_step "Запуск удаления KDW Bot..."
    if [ -f /opt/etc/kdw/opkg/prerm ]; then sh /opt/etc/kdw/opkg/prerm; fi
    if [ -f /opt/etc/kdw/opkg/postrm ]; then sh /opt/etc/kdw/opkg/postrm; fi
    rm -rf /opt/etc/kdw
    echo_success "KDW Bot полностью удален."
    exit 0
fi

# --- Action: Install / Reinstall ---
if [ "$ACTION" = "reinstall" ]; then
    echo_step "Запуск переустановки KDW Bot..."
    if [ -f /opt/etc/kdw/opkg/prerm ]; then sh /opt/etc/kdw/opkg/prerm; fi
    if [ -f /opt/etc/kdw/opkg/postrm ]; then sh /opt/etc/kdw/opkg/postrm; fi
    rm -rf /opt/etc/kdw
    echo_success "Старая версия удалена."
fi

echo_step "Запуск установки KDW Bot..."
opkg update > /dev/null
if ! command -v jq > /dev/null; then opkg install jq; fi
if ! command -v curl > /dev/null; then opkg install curl; fi
if ! command -v tar > /dev/null; then opkg install tar; fi

INSTALL_DIR="/opt/etc/kdw"
REPO_URL="https://github.com/xxsokolov/KDW/archive/refs/heads/main.tar.gz"
TMP_FILE="/tmp/kdw_main.tar.gz"
TMP_DIR="/tmp/KDW-main"

echo_step "Скачивание последней версии..."
curl -sL "$REPO_URL" -o "$TMP_FILE"
if [ $? -ne 0 ]; then echo_error "Не удалось скачать архив с GitHub."; fi

echo_step "Распаковка и установка файлов в $INSTALL_DIR..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
tar -xzf "$TMP_FILE" -C /tmp
if [ $? -ne 0 ]; then echo_error "Не удалось распаковать архив."; fi

cp -r ${TMP_DIR}/core ${INSTALL_DIR}/
cp -r ${TMP_DIR}/scripts ${INSTALL_DIR}/
cp -r ${TMP_DIR}/opkg ${INSTALL_DIR}/
cp ${TMP_DIR}/kdw_bot.py ${INSTALL_DIR}/
cp ${TMP_DIR}/kdw.cfg.example ${INSTALL_DIR}/
cp ${TMP_DIR}/requirements.txt ${INSTALL_DIR}/

rm "$TMP_FILE"
rm -rf "$TMP_DIR"
echo_success "Файлы проекта успешно установлены."

POSTINST_SCRIPT="${INSTALL_DIR}/opkg/postinst"
if [ ! -f "$POSTINST_SCRIPT" ]; then
    echo_error "Не удалось найти основной скрипт установки."
fi

echo_step "Запуск основного скрипта настройки..."
chmod +x "$POSTINST_SCRIPT"
sh "$POSTINST_SCRIPT" $POSTINST_ARGS

exit 0
