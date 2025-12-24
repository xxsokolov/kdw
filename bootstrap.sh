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

# --- 1. Установка ключевых зависимостей ---
echo_step "Установка системных зависимостей..."
opkg update > /dev/null
opkg install python3 python3-pip curl jq git
if [ $? -ne 0 ]; then echo_error "Не удалось установить базовые пакеты. Проверьте работу opkg."; fi
echo_success "Системные зависимости установлены."

# --- 2. Клонирование и выборочное копирование ---
INSTALL_DIR="/opt/etc/kdw"
REPO_URL="https://github.com/xxsokolov/KDW.git"
TMP_REPO_DIR="/tmp/kdw_repo"

echo_step "Клонирование репозитория из GitHub..."
rm -rf "$TMP_REPO_DIR"
git clone --depth 1 "$REPO_URL" "$TMP_REPO_DIR"
if [ $? -ne 0 ]; then echo_error "Не удалось клонировать репозиторий."; fi

echo_step "Копирование рабочих файлов в $INSTALL_DIR..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Копируем только необходимые для работы файлы и директории
cp -r ${TMP_REPO_DIR}/core "$INSTALL_DIR/"
cp -r ${TMP_REPO_DIR}/scripts "$INSTALL_DIR/"
cp -r ${TMP_REPO_DIR}/opkg "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/kdw_bot.py "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/kdw.cfg.example "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/requirements.txt "$INSTALL_DIR/"

# Очистка
rm -rf "$TMP_REPO_DIR"

echo_success "Файлы проекта успешно установлены."

# --- 3. Установка Python зависимостей ---
echo_step "Установка Python-библиотек..."
pip3 install -r ${INSTALL_DIR}/requirements.txt
if [ $? -ne 0 ]; then echo_error "Не удалось установить Python-библиотеки."; fi
echo_success "Python-библиотеки установлены."

# --- 4. Запуск скрипта настройки ---
POSTINST_SCRIPT="${INSTALL_DIR}/opkg/postinst"
if [ ! -f "$POSTINST_SCRIPT" ]; then
    echo_error "Не удалось найти основной скрипт установки."
fi

echo_step "Запуск основного скрипта настройки..."
chmod +x "$POSTINST_SCRIPT"
sh "$POSTINST_SCRIPT" $POSTINST_ARGS

exit 0
