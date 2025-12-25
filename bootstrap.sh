#!/bin/sh

# =================================================================
# KDW Bot Installer (Bootstrap)
#
# Описание:
#   Единый скрипт для установки, обновления и удаления
#   Telegram-бота для управления роутером Keenetic.
#
# Автор: xxsokolov
# GitHub: https://github.com/xxsokolov/KDW
# =================================================================

# --- 1. Конфигурация ---
INSTALL_DIR="/opt/etc/kdw"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/xxsokolov/KDW.git"
TMP_REPO_DIR="/opt/tmp/kdw_repo"
OPKG_DEPENDENCIES="python3 python3-pip jq git git-http dnsmasq-full ipset shadowsocks-libev-ss-redir"
MANIFEST_FILE="${INSTALL_DIR}/install.manifest"

# --- 2. Вспомогательные функции ---
echo_step() { printf "-> %s\n" "$1"; }
echo_success() { printf "\033[0;32m[OK] %s\033[0m\n" "$1"; }
echo_error() { printf "\033[0;31m[ERROR] %s\033[0m\n" "$1"; exit 1; }
add_to_manifest() { echo "$1" >> "$MANIFEST_FILE"; }

# Функция для отображения спиннера во время выполнения команды
run_with_spinner() {
    local text="$1"
    shift
    local cmd="$@"

    spinner() {
        local chars="/-\|"
        while :; do
            for i in $(seq 0 3); do
                printf "\r\033[0;36m[%c]\033[0m %s..." "${chars:$i:1}" "$text"
                sleep 1
            done
        done
    }

    spinner &
    SPINNER_PID=$!
    trap 'kill $SPINNER_PID 2>/dev/null' EXIT

    OUTPUT=$($cmd 2>&1)
    EXIT_CODE=$?

    kill $SPINNER_PID 2>/dev/null
    trap - EXIT

    printf "\r%80s\r" " "

    if [ $EXIT_CODE -ne 0 ]; then
        echo_error "$text"
        echo "--- Подробности ошибки ---"
        echo "$OUTPUT"
        echo "--------------------------"
        exit 1
    else
        echo_success "$text"
    fi
}

show_help() {
    echo "KDW Bot Installer & Manager"
    echo ""
    echo "Использование: bootstrap.sh <команда> [опции]"
    echo ""
    echo "Команды:"
    echo "  --install      Установить бота. Если будет найдена существующая установка, скрипт завершится с ошибкой."
    echo "  --update       Обновить бота до последней версии. Сохраняет ваш конфиг, полностью удаляет старую версию и устанавливает новую."
    echo "  --uninstall    Полностью удалить бота, его файлы и все связанные системные пакеты."
    echo "  -h, --help     Показать это справочное сообщение."
    echo ""
    echo "Опции (для --install):"
    echo "  --token <TOKEN>      Ваш токен Telegram бота."
    echo "  --user-id <USER_ID>  Ваш Telegram User ID."
    echo ""
}

# --- 3. Парсинг аргументов командной строки ---
if [ -z "$1" ]; then
    show_help
    exit 0
fi

ACTION=""
POSTINST_ARGS=""
case $1 in
    --install|--update|--uninstall)
        ACTION=${1#--}
        shift
        POSTINST_ARGS="$@"
        ;;
    -h|--help)
        show_help
        exit 0
        ;;
    *)
        echo "Неверная команда: $1"
        show_help
        exit 1
        ;;
esac

# --- 4. Логика выполнения команд ---

# --- Команда: Удаление ---
if [ "$ACTION" = "uninstall" ]; then
    echo_step "Запуск полного удаления KDW Bot..."
    if [ ! -f "$MANIFEST_FILE" ]; then
        echo "Манифест установки не найден. Попытка стандартного удаления..."
        [ -f /opt/etc/init.d/S99kdwbot ] && sh /opt/etc/init.d/S99kdwbot stop
        rm -rf "$INSTALL_DIR" /opt/etc/init.d/S99kdwbot /opt/etc/init.d/S99unblock
        opkg remove $OPKG_DEPENDENCIES --force-remove --force-depends
        rm -f /opt/etc/dnsmasq.conf /opt/etc/dnsmasq.conf-opkg
        echo_success "Стандартное удаление завершено."
        exit 0
    fi

    echo_step "Остановка служб..."
    if [ -f /opt/etc/init.d/S99kdwbot ]; then sh /opt/etc/init.d/S99kdwbot stop; fi

    PACKAGES_TO_REMOVE=$(grep '^pkg:' "$MANIFEST_FILE" | cut -d':' -f2- | tr '\n' ' ')

    echo_step "Удаление файлов и директорий из манифеста..."
    awk '{a[i++]=$0} END {for (j=i-1; j>=0;) print a[j--] }' "$MANIFEST_FILE" | while read -r line; do
        type=$(echo "$line" | cut -d':' -f1)
        path=$(echo "$line" | cut -d':' -f2-)
        if [ "$type" = "file" ] || [ "$type" = "dir" ]; then
            if [ -e "$path" ]; then
                rm -rf "$path"
                echo "  - $path"
            fi
        fi
    done
    echo_success "Файлы и директории удалены."

    if [ -n "$PACKAGES_TO_REMOVE" ]; then
        run_with_spinner "Удаление системных пакетов..." opkg remove $PACKAGES_TO_REMOVE --force-remove --force-depends
    fi
    rm -f /opt/etc/dnsmasq.conf /opt/etc/dnsmasq.conf-opkg

    echo_success "KDW Bot полностью удален."
    exit 0
fi

# --- Команда: Обновление ---
if [ "$ACTION" = "update" ]; then
    echo_step "Запуск обновления KDW Bot..."
    CONFIG_BACKUP="/tmp/kdw.cfg.bak"
    if [ -f "${INSTALL_DIR}/kdw.cfg" ]; then
        echo_step "Создание резервной копии конфигурации..."
        cp "${INSTALL_DIR}/kdw.cfg" "$CONFIG_BACKUP"
        EXISTING_TOKEN=$(grep -o 'token = .*' "$CONFIG_BACKUP" | cut -d' ' -f3)
        EXISTING_USER_ID=$(grep -o 'access_ids = \[.*\]' "$CONFIG_BACKUP" | sed 's/access_ids = \[\(.*\)\]/\1/')
        POSTINST_ARGS="--token $EXISTING_TOKEN --user-id $EXISTING_USER_ID"
        echo_success "Конфигурация сохранена."
    fi

    run_with_spinner "Скачивание последней версии установщика..." curl -sL -o /tmp/bootstrap_new.sh https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh

    echo_step "Удаление старой версии..."
    sh $0 --uninstall

    echo_step "Установка новой версии..."
    sh /tmp/bootstrap_new.sh --install $POSTINST_ARGS

    rm /tmp/bootstrap_new.sh
    [ -f "$CONFIG_BACKUP" ] && rm "$CONFIG_BACKUP"
    echo_success "Обновление завершено!"
    exit 0
fi

# --- Команда: Установка ---
if [ "$ACTION" = "install" ]; then
    echo_step "Запуск установки KDW Bot..."

    if [ -d "$INSTALL_DIR" ]; then
        echo_error "Обнаружена существующая установка KDW Bot."
        echo "Для обновления используйте флаг '--update'."
        echo "Для полного удаления используйте флаг '--uninstall'."
        exit 1
    fi

    # --- 4.1. Установка системных зависимостей ---
    run_with_spinner "Обновление списка пакетов opkg..." opkg update
    run_with_spinner "Установка системных зависимостей..." opkg install $OPKG_DEPENDENCIES

    # --- 4.2. Создание директории и манифеста ---
    mkdir -p "$INSTALL_DIR"
    rm -f "$MANIFEST_FILE"
    touch "$MANIFEST_FILE"
    add_to_manifest "dir:$INSTALL_DIR"

    # --- 4.3. Настройка базовых сервисов ---
    echo_step "Настройка базовых сервисов..."
    SHADOWSOCKS_INIT_SCRIPT="/opt/etc/init.d/S22shadowsocks"
    if [ -f "$SHADOWSOCKS_INIT_SCRIPT" ]; then
        sed -i 's/ss-local/ss-redir/g' "$SHADOWSOCKS_INIT_SCRIPT"
        chmod +x "$SHADOWSOCKS_INIT_SCRIPT"
        add_to_manifest "file:$SHADOWSOCKS_INIT_SCRIPT"
        echo_success "Shadowsocks настроен для работы в режиме редиректа."
    else
        echo_error "Скрипт инициализации Shadowsocks не найден!"
    fi
    if ! grep -q "conf-dir=/opt/etc/dnsmasq.d" /opt/etc/dnsmasq.conf; then
        echo "conf-dir=/opt/etc/dnsmasq.d" >> /opt/etc/dnsmasq.conf
    fi
    add_to_manifest "file:/opt/etc/dnsmasq.conf"
    echo_success "Dnsmasq настроен."

    # --- 4.4. Клонирование репозитория ---
    run_with_spinner "Клонирование репозитория KDW Bot..." git clone --depth 1 "$REPO_URL" "$TMP_REPO_DIR"

    # --- 4.5. Копирование файлов проекта ---
    echo_step "Копирование рабочих файлов..."
    copy_and_manifest() {
        src="$1"
        dest="$2"
        cp -r "$src" "$dest"
        find "$dest" -mindepth 1 | while read -r item; do
            if [ -d "$item" ]; then
                add_to_manifest "dir:$item"
            else
                add_to_manifest "file:$item"
            fi
        done
    }
    copy_and_manifest "${TMP_REPO_DIR}/core" "${INSTALL_DIR}/"
    copy_and_manifest "${TMP_REPO_DIR}/kdw_bot.py" "${INSTALL_DIR}/"
    copy_and_manifest "${TMP_REPO_DIR}/kdw.cfg.example" "${INSTALL_DIR}/"
    copy_and_manifest "${TMP_REPO_DIR}/requirements.txt" "${INSTALL_DIR}/"
    rm -rf "$TMP_REPO_DIR"
    echo_success "Файлы проекта успешно установлены."

    # --- 4.6. Создание виртуального окружения ---
    for pkg in $OPKG_DEPENDENCIES; do add_to_manifest "pkg:$pkg"; done
    echo_success "Манифест пакетов создан."

    run_with_spinner "Создание виртуального окружения Python..." python3 -m venv "$VENV_DIR"
    add_to_manifest "dir:$VENV_DIR"

    run_with_spinner "Обновление pip..." ${VENV_DIR}/bin/python -m pip install --upgrade pip

    run_with_spinner "Установка Python-библиотек..." ${VENV_DIR}/bin/pip install --upgrade -r "${INSTALL_DIR}/requirements.txt"

    # --- 4.7. Финальная настройка и запуск ---
    echo_step "Финальная настройка..."
    for arg in $POSTINST_ARGS; do
        case $arg in
            --token=*) BOT_TOKEN="${arg#*=}" ;;
            --user-id=*) USER_ID="${arg#*=}" ;;
        esac
    done

    if [ -z "$BOT_TOKEN" ]; then
      echo "Пожалуйста, введите данные для настройки бота:"
      printf "1. Токен вашего Telegram бота: "
      read BOT_TOKEN
      if [ -z "$BOT_TOKEN" ]; then echo_error "Токен не может быть пустым."; fi
      printf "2. Ваш Telegram User ID: "
      read USER_ID
      if [ -z "$USER_ID" ]; then echo_error "User ID не может быть пустым."; fi
    fi

    API_URL="https://api.telegram.org/bot$BOT_TOKEN/getMe"
    RESPONSE=$(curl -s "$API_URL")
    if [ $? -ne 0 ] || [ -z "$RESPONSE" ]; then echo_error "Не удалось связаться с Telegram API."; fi
    OK_STATUS=$(echo $RESPONSE | jq -r '.ok')
    if [ "$OK_STATUS" != "true" ]; then echo_error "Неверный токен: $RESPONSE"; fi
    BOT_USERNAME=$(echo $RESPONSE | jq -r '.result.username')
    echo_success "Токен верный. Бот: @$BOT_USERNAME"

    CONFIG_FILE="${INSTALL_DIR}/kdw.cfg"
    cat > "$CONFIG_FILE" << EOF
[telegram]
token = $BOT_TOKEN
access_ids = [$USER_ID]
[keenetic]
host = 127.0.0.1
port = 80
user = admin
password =
EOF
    add_to_manifest "file:$CONFIG_FILE"
    echo_success "Конфигурационный файл создан."

    SERVICE_FILE="/opt/etc/init.d/S99kdwbot"
    cat > "$SERVICE_FILE" << EOF
#!/bin/sh
# KDW Bot Service
BOT_PATH="${INSTALL_DIR}/kdw_bot.py"
PYTHON_EXEC="${VENV_DIR}/bin/python"
PID_FILE="/var/run/kdw_bot.pid"
LOG_FILE="/opt/var/log/kdw_bot.log"

start() {
    if [ -f "\$PID_FILE" ] && ps | grep -q "^\s*\$(cat \$PID_FILE)\s"; then return; fi
    echo "Starting KDW Bot..."
    \$PYTHON_EXEC \$BOT_PATH >> \$LOG_FILE 2>&1 &
    echo \$! > \$PID_FILE
}
stop() {
    if [ ! -f "\$PID_FILE" ]; then return; fi
    PID=\$(cat \$PID_FILE)
    if ps | grep -q "^\s*\$PID\s"; then kill \$PID; fi
    rm -f \$PID_FILE
}
case "\$1" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 2; start ;;
    *) echo "Usage: \$0 {start|stop|restart}" ;;
esac
EOF
    chmod +x "$SERVICE_FILE"
    add_to_manifest "file:$SERVICE_FILE"
    echo_success "Служба автозапуска создана."

    sh "$SERVICE_FILE" start
    sleep 3
    if [ -f /var/run/kdw_bot.pid ] && ps | grep -q "^\s*$(cat /var/run/kdw_bot.pid)\s"; then
        echo_success "Процесс бота успешно запущен."
    else
        echo_error "Не удалось запустить процесс бота. См. /opt/var/log/kdw_bot.log"
    fi

    echo_success "Установка KDW Bot завершена!"
    exit 0
fi
