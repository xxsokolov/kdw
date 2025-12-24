#!/bin/sh

# KDW Bot Installer (Bootstrap)
# https://github.com/xxsokolov/KDW

# --- Configuration ---
INSTALL_DIR="/opt/etc/kdw"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/xxsokolov/KDW.git"
TMP_REPO_DIR="/tmp/kdw_repo"

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
    if [ -f "${INSTALL_DIR}/opkg/prerm" ]; then sh "${INSTALL_DIR}/opkg/prerm"; fi
    if [ -f "${INSTALL_DIR}/opkg/postrm" ]; then sh "${INSTALL_DIR}/opkg/postrm"; fi
    rm -rf "$INSTALL_DIR"
    echo_success "KDW Bot полностью удален."
    exit 0
fi

# --- Action: Install / Reinstall ---
if [ "$ACTION" = "reinstall" ]; then
    echo_step "Запуск переустановки KDW Bot..."
    if [ -f "${INSTALL_DIR}/kdw.cfg" ]; then
        printf "Найден существующий файл конфигурации. Использовать его для новой установки? (y/n): "
        read -r use_existing_config
        if [ "$use_existing_config" = "y" ] || [ "$use_existing_config" = "Y" ]; then
            echo_step "Сохранение существующей конфигурации..."
            EXISTING_TOKEN=$(grep -o 'token = .*' "${INSTALL_DIR}/kdw.cfg" | cut -d' ' -f3)
            EXISTING_USER_ID=$(grep -o 'access_ids = \[.*\]' "${INSTALL_DIR}/kdw.cfg" | sed 's/access_ids = \[\(.*\)\]/\1/')

            if [ -n "$EXISTING_TOKEN" ] && [ -n "$EXISTING_USER_ID" ]; then
                POSTINST_ARGS="--token $EXISTING_TOKEN --user-id $EXISTING_USER_ID"
                echo_success "Конфигурация сохранена."
            else
                echo "Не удалось прочитать старый конфиг. Установка будет интерактивной."
            fi
        fi
    fi

    if [ -f "${INSTALL_DIR}/opkg/prerm" ]; then sh "${INSTALL_DIR}/opkg/prerm"; fi
    if [ -f "${INSTALL_DIR}/opkg/postrm" ]; then sh "${INSTALL_DIR}/opkg/postrm"; fi
    rm -rf "$INSTALL_DIR"
    echo_success "Старая версия удалена."
fi

echo_step "Запуск установки KDW Bot..."

# --- 1. Установка ключевых зависимостей ---
echo_step "Установка системных зависимостей..."
opkg update > /dev/null
# Добавляем python3-venv для создания виртуальных окружений
opkg install python3 python3-pip python3-venv curl jq git git-http
if [ $? -ne 0 ]; then echo_error "Не удалось установить базовые пакеты. Проверьте работу opkg."; fi
echo_success "Системные зависимости установлены."

# --- 2. Клонирование и выборочное копирование ---
echo_step "Клонирование репозитория из GitHub..."
rm -rf "$TMP_REPO_DIR"
git clone --depth 1 "$REPO_URL" "$TMP_REPO_DIR"
if [ $? -ne 0 ]; then echo_error "Не удалось клонировать репозиторий."; fi

echo_step "Копирование рабочих файлов в $INSTALL_DIR..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

cp -r ${TMP_REPO_DIR}/core "$INSTALL_DIR/"
cp -r ${TMP_REPO_DIR}/scripts "$INSTALL_DIR/"
cp -r ${TMP_REPO_DIR}/opkg "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/kdw_bot.py "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/kdw.cfg.example "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/requirements.txt "$INSTALL_DIR/"

rm -rf "$TMP_REPO_DIR"
echo_success "Файлы проекта успешно установлены."

# --- 3. Создание и установка зависимостей в VENV ---
echo_step "Создание виртуального окружения Python..."
python3 -m venv "$VENV_DIR"
if [ $? -ne 0 ]; then echo_error "Не удалось создать виртуальное окружение."; fi
echo_success "Виртуальное окружение создано в $VENV_DIR"

echo_step "Установка Python-библиотек в виртуальное окружение..."
${VENV_DIR}/bin/pip install --upgrade -r ${INSTALL_DIR}/requirements.txt --break-system-packages
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
