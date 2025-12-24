#!/bin/sh

# KDW Bot Installer (Bootstrap)
# https://github.com/xxsokolov/KDW

# --- Configuration ---
INSTALL_DIR="/opt/etc/kdw"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/xxsokolov/KDW.git"
TMP_REPO_DIR="/opt/tmp/kdw_repo"
CPYTHON_SRC_DIR="/opt/tmp/cpython_src"
OPKG_DEPENDENCIES="python3 python3-pip jq git git-http"
REQUIREMENTS_FILE="${INSTALL_DIR}/requirements.txt"

# --- Functions ---
echo_step() {
  echo "-> $1"
}
echo_success() {
  # Green color
  printf "\033[0;32m[OK] %s\033[0m\n" "$1"
}
echo_error() {
  # Red color
  printf "\033[0;31m[ERROR] %s\033[0m\n" "$1"
  rm -rf "$TMP_REPO_DIR"
  rm -rf "$CPYTHON_SRC_DIR"
  exit 1
}

# --- Argument Parsing ---
ACTION="install"
RECREATE_VENV="true"
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

    echo "Удаление файлов и директорий..."
    [ -f /opt/etc/init.d/S99kdwbot ] && rm -f /opt/etc/init.d/S99kdwbot && echo "  - /opt/etc/init.d/S99kdwbot"
    [ -f /opt/etc/init.d/S99unblock ] && rm -f /opt/etc/init.d/S99unblock && echo "  - /opt/etc/init.d/S99unblock"
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR" && echo "  - $INSTALL_DIR (директория проекта)"

    echo_success "KDW Bot полностью удален."
    exit 0
fi

# --- Action: Install / Reinstall ---
if [ "$ACTION" = "reinstall" ]; then
    echo_step "Запуск переустановки KDW Bot..."

    if [ -f "${INSTALL_DIR}/kdw.cfg" ]; then
        printf "Найден существующий файл конфигурации. Использовать его? (Y/n): "
        read -r use_existing_config
        if [ "$use_existing_config" != "n" ] && [ "$use_existing_config" != "N" ]; then
            echo_step "Сохранение существующей конфигурации..."
            EXISTING_TOKEN=$(grep -o 'token = .*' "${INSTALL_DIR}/kdw.cfg" | cut -d' ' -f3)
            EXISTING_USER_ID=$(grep -o 'access_ids = \[.*\]' "${INSTALL_DIR}/kdw.cfg" | sed 's/access_ids = \[\(.*\)\]/\1/')

            if [ -n "$EXISTING_TOKEN" ] && [ -n "$EXISTING_USER_ID" ]; then
                POSTINST_ARGS="--token $EXISTING_TOKEN --user-id $EXISTING_USER_ID"
                echo_success "Конфигурация сохранена."
            fi
        fi
    fi

    if [ -d "$VENV_DIR" ]; then
        printf "Сохранить существующее виртуальное окружение? (Y/n): "
        read -r save_venv_choice
        if [ "$save_venv_choice" = "n" ] || [ "$save_venv_choice" = "N" ]; then
            RECREATE_VENV="true"
        else
            RECREATE_VENV="false"
        fi
    fi

    if [ -f "${INSTALL_DIR}/opkg/prerm" ]; then sh "${INSTALL_DIR}/opkg/prerm"; fi

    VENV_BACKUP_FILE="/tmp/kdw_venv.tar.gz"
    if [ "$RECREATE_VENV" = "false" ] && [ -d "$VENV_DIR" ]; then
        echo_step "Создание резервной копии виртуального окружения..."
        tar -czf "$VENV_BACKUP_FILE" -C "$INSTALL_DIR" venv
        if [ $? -ne 0 ]; then echo_error "Не удалось создать архив venv."; fi
    fi

    echo_step "Удаляеме старую версию KDW Bot..."
    rm -rf "$INSTALL_DIR"
    echo_success "Старая версия удалена."
    echo_step "Создаем новую рабочую директорию..."
    mkdir -p "$INSTALL_DIR"

    if [ -f "$VENV_BACKUP_FILE" ]; then
        echo_step "Восстановление виртуального окружения из резервной копии..."
        tar -xzf "$VENV_BACKUP_FILE" -C "$INSTALL_DIR"
        rm "$VENV_BACKUP_FILE"
        echo_success "Виртуальное окружение восстановлено."
    fi

fi

echo_step "Запуск установки KDW Bot..."

# --- 1. Установка системных зависимостей ---
echo_step "Установка системных зависимостей..."
opkg update > /dev/null
opkg install $OPKG_DEPENDENCIES
if [ $? -ne 0 ]; then echo_error "Не удалось установить базовые пакеты. Проверьте работу opkg."; fi
echo_success "Системные зависимости установлены."

# --- 2. Проверка и установка модуля VENV ---
if [ "$RECREATE_VENV" = "true" ]; then
    echo_step "Проверка модуля venv..."
    if ! python3 -m venv --help > /dev/null 2>&1; then
        echo "  -> Модуль venv не найден. Попытка ручной установки..."

        PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        PY_LIB_PATH=$(python3 -c "import site, os; print(os.path.dirname(site.getsitepackages()[0]))")

        if [ -z "$PY_LIB_PATH" ]; then echo_error "Не удалось определить путь к библиотекам Python."; fi

        echo "  -> Клонирование исходного кода CPython v${PY_VER} в $CPYTHON_SRC_DIR..."
        rm -rf "$CPYTHON_SRC_DIR"
        git clone --depth=1 --branch="${PY_VER}" --single-branch https://github.com/python/cpython.git "$CPYTHON_SRC_DIR"
        if [ $? -ne 0 ]; then echo_error "Не удалось клонировать репозиторий CPython."; fi

        echo "  -> Копирование модулей 'venv' и 'ensurepip' в ${PY_LIB_PATH}..."
        cp -r "${CPYTHON_SRC_DIR}/Lib/venv" "$PY_LIB_PATH/"
        cp -r "${CPYTHON_SRC_DIR}/Lib/ensurepip" "$PY_LIB_PATH/"

        rm -rf "$CPYTHON_SRC_DIR"
        echo_success "Модуль venv успешно установлен."
    else
        echo_success "Модуль venv уже доступен."
    fi
fi

# --- 3. Клонирование и выборочное копирование ---
echo_step "Клонирование репозитория KDW Bot..."
rm -rf "$TMP_REPO_DIR"
git clone --depth 1 "$REPO_URL" "$TMP_REPO_DIR"
if [ $? -ne 0 ]; then echo_error "Не удалось клонировать репозиторий."; fi

echo_step "Копирование рабочих файлов в $INSTALL_DIR..."
cp -r ${TMP_REPO_DIR}/core "$INSTALL_DIR/"
cp -r ${TMP_REPO_DIR}/scripts "$INSTALL_DIR/"
cp -r ${TMP_REPO_DIR}/opkg "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/kdw_bot.py "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/kdw.cfg.example "$INSTALL_DIR/"
cp ${TMP_REPO_DIR}/requirements.txt "$INSTALL_DIR/"

rm -rf "$TMP_REPO_DIR"
echo_success "Файлы проекта успешно установлены."

# --- 4. Создание и установка зависимостей в VENV ---
if [ "$RECREATE_VENV" = "true" ]; then
    echo_step "Создание виртуального окружения Python..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then echo_error "Не удалось создать виртуальное окружение."; fi
    echo_success "Виртуальное окружение создано в $VENV_DIR"

    echo_step "Обновление pip в виртуальном окружении..."
    ${VENV_DIR}/bin/python -m pip install --upgrade pip
    if [ $? -ne 0 ]; then echo_error "Не удалось обновить pip."; fi

    echo_step "Установка Python-библиотек в виртуальное окружение..."
    ${VENV_DIR}/bin/pip install --upgrade -r "$REQUIREMENTS_FILE" --break-system-packages
    if [ $? -ne 0 ]; then echo_error "Не удалось установить Python-библиотеки."; fi
    echo_success "Python-библиотеки установлены."
else
    echo_step "Пропуск создания/обновления виртуального окружения."
fi

# --- 5. Запуск скрипта настройки ---
POSTINST_SCRIPT="${INSTALL_DIR}/opkg/postinst"
if [ ! -f "$POSTINST_SCRIPT" ]; then
    echo_error "Не удалось найти основной скрипт установки."
fi

echo_step "Запуск основного скрипта настройки..."
chmod +x "$POSTINST_SCRIPT"
sh "$POSTINST_SCRIPT" $POSTINST_ARGS --python-exec "${VENV_DIR}/bin/python"

exit 0
