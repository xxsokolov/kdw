#!/bin/sh

# KDW Bot Installer (Bootstrap)
# https://github.com/xxsokolov/KDW

# --- Functions ---
echo_step() {
  echo "-> $1"
}
echo_success() {
  echo "[OK] $1"
}
echo_error() {
  echo "[ERROR] $1"
  exit 1
}

# --- Argument Parsing ---
ACTION="install"
POSTINST_ARGS=""
while [ "$1" != "" ]; do
    case $1 in
        --install) ACTION="install" ;;
        --reinstall) ACTION="reinstall" ;;
        --uninstall) ACTION="uninstall" ;;
        *) POSTINST_ARGS="$POSTINST_ARGS $1" ;;
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
if ! command -v curl > /dev/null; then opkg install curl; fi
if ! command -v jq > /dev/null; then opkg install jq; fi
if ! command -v tar > /dev/null; then opkg install tar; fi

INSTALL_DIR="/opt/etc/kdw"
REPO_URL="https://github.com/xxsokolov/KDW/archive/refs/heads/main.tar.gz"
TMP_FILE="/tmp/kdw_main.tar.gz"

echo_step "Скачивание последней версии..."
curl -sL "$REPO_URL" -o "$TMP_FILE"
if [ $? -ne 0 ]; then echo_error "Не удалось скачать архив с GitHub. Убедитесь, что curl установлен и есть доступ в интернет."; fi

echo_step "Распаковка и установка файлов в $INSTALL_DIR..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Распаковываем архив во временную директорию
tar -xzf "$TMP_FILE" -C /tmp
if [ $? -ne 0 ]; then echo_error "Не удалось распаковать архив."; fi

# Находим имя распакованной папки (оно может меняться)
EXTRACTED_DIR=$(tar -tzf "$TMP_FILE" | head -1 | cut -f1 -d"/")
if [ -z "$EXTRACTED_DIR" ]; then echo_error "Не удалось определить имя директории в архиве."; fi

# Перемещаем содержимое распакованной папки в целевую директорию
mv /tmp/${EXTRACTED_DIR}/* "$INSTALL_DIR/"

# Очистка временных файлов
rm "$TMP_FILE"
rm -rf "/tmp/$EXTRACTED_DIR"

echo_success "Файлы проекта успешно установлены."

# --- Run Post-Install Script ---
POSTINST_SCRIPT="${INSTALL_DIR}/opkg/postinst"
if [ ! -f "$POSTINST_SCRIPT" ]; then
    echo_error "Не удалось найти основной скрипт установки."
fi

echo_step "Запуск основного скрипта настройки..."
chmod +x "$POSTINST_SCRIPT"
sh "$POSTINST_SCRIPT" $POSTINST_ARGS

exit 0
