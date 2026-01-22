#!/bin/sh
#
# =================================================================
# KDW Bot Installer (Bootstrap)
#
# Описание:
#   Единый скрипт для установки, обновления и удаления
#   Telegram-бота для управления роутером Keenetic.
#
# Использование:
#   sh bootstrap.sh --install [--token=TOKEN --user-id=ID] [-y]
#   sh bootstrap.sh --update [-y]
#   sh bootstrap.sh --uninstall [-y]
#
# Автор: xxsokolov
# GitHub: https://github.com/xxsokolov/KDW
# =================================================================
#
# --- 1. Конфигурация ---
INSTALL_DIR="/opt/etc/kdw"
LISTS_DIR="${INSTALL_DIR}/lists"
SCRIPTS_DIR="${INSTALL_DIR}/scripts"
VENV_DIR="${INSTALL_DIR}/venv"
NDM_DIR="/opt/etc/ndm/fs.d"
REPO_URL="https://github.com/xxsokolov/kdw.git"
CPYTHON_REPO_URL="https://github.com/python/cpython.git"
MANIFEST="${INSTALL_DIR}/install.manifest"

# Список системных пакетов для архитектуры mipselsf-k3.4
PKGS="python3 python3-pip jq git git-http ipset iptables dnsmasq-full shadowsocks-libev-ss-redir shadowsocks-libev-ss-local trojan v2ray-core tor tor-geoip"

# Карта соответствия пакетов и их скриптов инициализации для проверки установки
PKG_MAP="
    shadowsocks-libev-ss-redir:shadowsocks
    trojan:trojan
    v2ray-core:v2ray
    tor:tor
    dnsmasq-full:dnsmasq
"

# Список служб для автоматизированного управления (остановка/запуск/очистка)
MANAGED_SERVICES="shadowsocks trojan v2ray tor dnsmasq kdwbot"

# --- 2. Вспомогательные функции и парсинг аргументов ---

# Вывод этапов установки
echo_step() { printf "\033[0;36m->\033[0m %s\n" "$1"; }
# Вывод успешного завершения
echo_ok() { printf "\033[0;32m[OK] %s\033[0m\n" "$1"; }
# Вывод ошибки и выход
echo_err() { printf "\033[0;31m[ERROR] %s\033[0m\n" "$1"; exit 1; }

# Парсинг флага -y для автоматического подтверждения
AUTO_CONFIRM=false
for arg in "$@"; do
    if [ "$arg" = "-y" ]; then
        AUTO_CONFIRM=true
        break
    fi
done

# Регистрация созданных файлов в манифест для последующего чистого удаления
add_m() {
    [ ! -d "$INSTALL_DIR" ] && mkdir -p "$INSTALL_DIR"
    echo "$1" >> "$MANIFEST"
}

# Поиск файла службы в /opt/etc/init.d/ по маске (учитывает разные порядковые номера S??)
find_svc() {
    ls /opt/etc/init.d/S[0-9][0-9]$1* 2>/dev/null | head -n 1
}

# Визуальный спиннер для длительных операций
run_with_spinner() {
    local text="$1"; shift; local cmd="$@"
    spinner() {
        local chars="/-\|"
        while :; do
            for i in 0 1 2 3; do
                printf "\r\033[0;36m[%c]\033[0m %s..." "${chars:$i:1}" "$text"
                sleep 1
            done
        done
    }
    spinner & local pid=$!
    trap "kill $pid 2>/dev/null" EXIT
    OUTPUT=$($cmd 2>&1)
    local res=$?
    kill $pid 2>/dev/null
    trap - EXIT
    printf "\r%80s\r" " "
    if [ $res -ne 0 ]; then
        echo "$OUTPUT"
        echo_err "$text завершилось с ошибкой"
    else
        echo_ok "$text"
    fi
}

# --- 3. Управление службами ---

# Универсальная функция для массового управления сервисами
manage_services() {
    local action=$1
    echo_step "Действие '$action' для всех служб..."
    for name in $MANAGED_SERVICES; do
        local file=$(find_svc "$name")
        if [ -f "$file" ]; then
            if [ "$action" = "delete" ]; then
                rm -f "$file"
            else
                echo "  - $(basename "$file") $action"
                if [ "$name" = "kdwbot" ]; then
                    "$file" "$action" # Не перенаправляем вывод, чтобы видеть ошибки
                else
                    "$file" "$action" >/dev/null 2>&1
                fi
                [ "$action" = "start" ] && sleep 1
            fi
        fi
    done
}

# --- 4. Удаление ---

do_uninstall() {
    manage_services "stop"
    if [ -f "$MANIFEST" ]; then
        echo_step "Удаление компонентов по манифесту..."
        # Читаем манифест с конца, чтобы сначала удалять файлы, затем папки
        sed '1!G;h;$!d' "$MANIFEST" | while IFS=: read -r type path; do
            case $type in
                file|dir)
                    # Для файлов и папок проверяем, что они внутри /opt/
                    case "$path" in
                        /opt/*) [ -e "$path" ] && rm -rf "$path" ;;
                        *) echo "  ! Пропуск удаления небезопасного пути: $path" ;;
                    esac
                    ;;
                pkg)
                    # Пакеты удаляем без проверки пути
                    opkg remove "$path" --autoremove >/dev/null 2>&1
                    ;;
            esac
        done
    fi
    # Удаляем саму директорию установки в конце
    [ -d "$INSTALL_DIR" ] && rm -rf "$INSTALL_DIR"
    manage_services "delete"
    # Очистка временных файлов конфигурации Entware
    find /opt/etc/ -name "*-opkg" -delete
    echo_ok "Система полностью очищена."
}

# --- 5. Установка и Обновление ---

do_update() {
    echo_step "Запуск обновления..."
    logger -t "KDW-Update" "Starting update process."

    manage_services "stop"
    logger -t "KDW-Update" "All services stopped."
    sleep 2

    TMP_REPO_DIR="/opt/tmp/kdw_repo_$$"
    run_with_spinner "Загрузка последней версии" git clone --depth 1 "$REPO_URL" "$TMP_REPO_DIR"

    echo_step "Копирование новых файлов..."
    # Копируем только то, что нужно, не затирая пользовательские данные
    cp -r "$TMP_REPO_DIR/core" "$INSTALL_DIR/"
    cp -r "$TMP_REPO_DIR/scripts" "$INSTALL_DIR/"
    cp "$TMP_REPO_DIR/kdw_bot.py" "$INSTALL_DIR/"
    cp "$TMP_REPO_DIR/requirements.txt" "$INSTALL_DIR/"
    cp "$TMP_REPO_DIR/bootstrap.sh" "$INSTALL_DIR/"
    cp "$TMP_REPO_DIR/kdw.cfg.example" "$INSTALL_DIR/"
    echo_ok "Файлы приложения обновлены."

    rm -rf "$TMP_REPO_DIR"

    run_with_spinner "Обновление Python-зависимостей" "$VENV_DIR/bin/pip" install --upgrade -r "$INSTALL_DIR/requirements.txt"
    logger -t "KDW-Update" "Pip requirements updated."

    manage_services "start"
    logger -t "KDW-Update" "All services started."

    echo_ok "Обновление успешно завершено."
    logger -t "KDW-Update" "Update finished successfully."
}

do_install() {
    [ -d "$INSTALL_DIR" ] && echo_err "Бот уже установлен. Используйте --update."

    # Первичная настройка доступа
    BOT_TOKEN=""
    USER_ID=""
    for arg in "$@"; do
        case $arg in
            --token=*) BOT_TOKEN="${arg#*=}" ;;
            --user-id=*) USER_ID="${arg#*=}" ;;
        esac
    done

    if [ -z "$BOT_TOKEN" ] || [ -z "$USER_ID" ]; then
        if [ "$AUTO_CONFIRM" = "true" ]; then
            echo_err "В неинтерактивном режиме (-y) необходимо указать --token и --user-id."
        fi
        echo_step "Настройка доступа"
        printf "Введите Telegram Bot Token: "
        read BOT_TOKEN
        printf "Введите ваш Telegram User ID: "
        read USER_ID
    fi

    run_with_spinner "Обновление списка пакетов opkg" opkg update
    run_with_spinner "Установка системных зависимостей" opkg install $PKGS

    # Проверка целостности init-скриптов и их принудительная переустановка при отсутствии
    echo_step "Проверка и исправление скриптов запуска..."
    for pair in $PKG_MAP; do
        pkg=${pair%%:*}
        svc=${pair#*:}
        svc_file=$(find_svc "$svc")

        if [ ! -f "$svc_file" ]; then
            echo "  ! Пакет $pkg не создал файл службы. Исправление (force-reinstall)..."
            opkg install "$pkg" --force-reinstall >/dev/null 2>&1
            svc_file=$(find_svc "$svc")
        fi

        if [ -f "$svc_file" ]; then
            chmod +x "$svc_file"
            add_m "file:$svc_file"

            if [ "$svc" = "shadowsocks" ]; then
                sed -i 's/ss-local/ss-redir/g' "$svc_file"
                CUSTOM_CONF="${INSTALL_DIR}/ss.active.json"
                if ! grep -q "$CUSTOM_CONF" "$svc_file"; then
                    echo "  -> Применяем патч к службе $svc..."
                    sed -i "s|/opt/etc/shadowsocks.json|$CUSTOM_CONF|g" "$svc_file"
                fi
            fi
        fi
    done

    # Создаем правильный сервисный файл для Trojan, если его нет или он - пустышка
    TROJAN_SVC_FILE=$(find_svc "trojan")
    if [ ! -f "$TROJAN_SVC_FILE" ] || ! grep -q "start-stop-daemon" "$TROJAN_SVC_FILE"; then
        echo "  -> Создаем/обновляем сервисный файл для Trojan..."
        [ -f "$TROJAN_SVC_FILE" ] && rm -f "$TROJAN_SVC_FILE"
        NEW_TROJAN_SVC="/opt/etc/init.d/S22trojan"
        cat > "$NEW_TROJAN_SVC" << 'EOF'
#!/bin/sh
ENABLED=yes
PROCS=trojan
ARGS="-c /opt/etc/kdw/tr.active.json"
PREARGS=""
DESC=$PROCS
PATH=/opt/sbin:/opt/bin:/opt/usr/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
. /opt/etc/init.d/rc.func
EOF
        chmod +x "$NEW_TROJAN_SVC"
        add_m "file:$NEW_TROJAN_SVC"
    fi


    # Исправление модуля venv (в Entware 2025 venv вырезан из python3-light)
    if ! python3 -m venv --help >/dev/null 2>&1; then
        echo_step "Восстановление модуля venv (Entware fix)..."
        tmp_v="/opt/tmp/v_fix"; mkdir -p "$tmp_v"
        PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        PY_LIB_PATH=$(python3 -c "import site, os; print(os.path.dirname(site.getsitepackages()[0]))")
        run_with_spinner "Загрузка исходников модулей Python" git clone --depth=1 --branch="v$PY_VER" "$CPYTHON_REPO_URL" "$tmp_v"
        cp -r "$tmp_v/Lib/venv" "$tmp_v/Lib/ensurepip" "$PY_LIB_PATH/"
        rm -rf "$tmp_v"
    fi

    # Инициализация манифеста пакетов
    mkdir -p "$INSTALL_DIR"
    : > "$MANIFEST"
    for p in $PKGS; do add_m "pkg:$p"; done

    # Клонирование репозитория бота
    run_with_spinner "Клонирование репозитория бота" git clone --depth 1 "$REPO_URL" "/opt/tmp/repo"
    cp -r /opt/tmp/repo/* "$INSTALL_DIR/"
    rm -rf /opt/tmp/repo

    # Создание изолированного виртуального окружения Python
    run_with_spinner "Создание venv" python3 -m venv "$VENV_DIR"
    run_with_spinner "Установка зависимостей через pip" "$VENV_DIR/bin/pip" install --upgrade pip -r "$INSTALL_DIR/requirements.txt"

    # Создание структуры директорий KDW
    echo_step "Создание структуры директорий KDW..."
    mkdir -p "$LISTS_DIR"
    mkdir -p "$SCRIPTS_DIR"
    add_m "dir:$LISTS_DIR"
    add_m "dir:$SCRIPTS_DIR"

    # --- Создание файлов для Firewall ---
    echo_step "Создание файлов для управления Firewall..."

    # 1. Файл состояния
    FIREWALL_STATE_FILE="${INSTALL_DIR}/firewall_mode.state"
    echo "flushed" > "$FIREWALL_STATE_FILE"
    add_m "file:$FIREWALL_STATE_FILE"

    # 2. Главный скрипт автозапуска
    AUTORUN_SCRIPT_PATH="${SCRIPTS_DIR}/kdw-firewall-autorun.sh"
    cat > "$AUTORUN_SCRIPT_PATH" << 'EOF'
#!/bin/sh
STATE_FILE="/opt/etc/kdw/firewall_mode.state"
SCRIPTS_DIR="/opt/etc/kdw/scripts"

if [ ! -f "$STATE_FILE" ]; then
    exit 0
fi

MODE=$(cat "$STATE_FILE")

case "$MODE" in
    lists_only)
        sh "${SCRIPTS_DIR}/kdw_apply_proxy_lists.sh"
        ;;
    all_traffic)
        # Для этого режима нужны параметры, которые бот передает при интерактивном запуске.
        # При автозапуске мы не можем их знать, поэтому просто сбрасываем правила.
        # Это безопасное поведение по умолчанию.
        sh "${SCRIPTS_DIR}/kdw_flush_proxy_rules.sh"
        ;;
    flushed)
        sh "${SCRIPTS_DIR}/kdw_flush_proxy_rules.sh"
        ;;
esac
EOF
    chmod +x "$AUTORUN_SCRIPT_PATH"
    add_m "file:$AUTORUN_SCRIPT_PATH"

    # 3. Скрипт интеграции с Keenetic
    mkdir -p "$NDM_DIR"
    KEENETIC_SCRIPT_PATH="${NDM_DIR}/100-kdw-firewall.sh"
    cat > "$KEENETIC_SCRIPT_PATH" << EOF
#!/bin/sh
# Запускает скрипт KDW Firewall при старте системы
sh "${AUTORUN_SCRIPT_PATH}"
EOF
    chmod +x "$KEENETIC_SCRIPT_PATH"
    add_m "file:$KEENETIC_SCRIPT_PATH"
    add_m "dir:$NDM_DIR"

    # Генерация конфигурационного файла
    cat > "$INSTALL_DIR/kdw.cfg" << EOF
[telegram]
token = $BOT_TOKEN
access_ids = [$USER_ID]

[firewall]
default_proxy_type = trojan
EOF
    add_m "file:$INSTALL_DIR/kdw.cfg"

    # Создание службы автозапуска S99kdwbot
    SERVICE_FILE="/opt/etc/init.d/S99kdwbot"
    cat > "$SERVICE_FILE" << 'EOF'
#!/bin/sh
# KDW Bot Service (Entware Optimized 2026)

NAME="kdw_bot"
DESC="KDW Telegram Bot"
BOT_ROOT="/opt/etc/kdw"
BOT_PATH="$BOT_ROOT/kdw_bot.py"
PYTHON_EXEC="$BOT_ROOT/venv/bin/python"
PID_FILE="/var/run/${NAME}.pid"

# Цвета для терминала
C_GREEN='\033[0;32m'
C_RED='\033[0;31m'
C_YELLOW='\033[1;33m'
C_RESET='\033[0m'

check_env() {
    if [ ! -f "$BOT_PATH" ]; then
        echo -e "[${C_RED}ERROR${C_RESET}] Файл бота не найден: $BOT_PATH"
        exit 1
    fi
    if [ ! -x "$PYTHON_EXEC" ]; then
        echo -e "[${C_RED}ERROR${C_RESET}] Python venv не найден или не активен: $PYTHON_EXEC"
        exit 1
    fi
}

start() {
    check_env
    echo -n "Starting $DESC: "

    # Проверка на дубликат
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo -e "[${C_YELLOW}ALREADY RUNNING${C_RESET}]"
        return 0
    fi

    # Запуск: -S (start), -b (background), -m (make pidfile)
    # Перенаправляем вывод демона в /dev/null, чтобы сохранить строку чистой
    start-stop-daemon -S -b -m -p "$PID_FILE" -x "$PYTHON_EXEC" -- "$BOT_PATH" >/dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo -e "[${C_GREEN}OK${C_RESET}]"
        logger -t "$NAME" "Service started successfully"
    else
        echo -e "[${C_RED}FAILED${C_RESET}]"
    fi
}

stop() {
    echo -n "Stopping $DESC: "
    if [ ! -f "$PID_FILE" ]; then
        echo -e "[${C_GREEN}OK${C_RESET}] (not running)"
        return 0
    fi

    PID=$(cat "$PID_FILE")

    # Посылаем сигнал завершения (TERM)
    start-stop-daemon -K -s TERM -p "$PID_FILE" >/dev/null 2>&1

    # Имитируем --retry (ждем до 5 секунд)
    RETRIES=5
    while [ $RETRIES -gt 0 ]; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
        RETRIES=$((RETRIES - 1))
    done

    # Если процесс не сдается — убиваем принудительно
    if kill -0 "$PID" 2>/dev/null; then
        echo -ne "${C_YELLOW}Forcing...${C_RESET} "
        start-stop-daemon -K -s KILL -p "$PID_FILE" >/dev/null 2>&1
    fi

    rm -f "$PID_FILE"
    echo -e "[${C_GREEN}OK${C_RESET}]"
    logger -t "$NAME" "Service stopped"
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "$DESC is ${C_GREEN}running${C_RESET} (PID: $PID)"
            return 0
        fi
    fi
    echo -e "$DESC is ${C_RED}stopped${C_RESET}"
    return 3
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 1 ;;
esac
EOF
    chmod +x "$SERVICE_FILE"
    add_m "file:$SERVICE_FILE"

    # Регистрация всех файлов проекта в манифест
    find "$INSTALL_DIR" -mindepth 1 -type f | while read -r f; do add_m "file:$f"; done
    find "$INSTALL_DIR" -mindepth 1 -type d | while read -r d; do add_m "dir:$d"; done

    # Финальный запуск всех компонентов
    manage_services "start"

    echo ""
    echo_ok "УСТАНОВКА ЗАВЕРШЕНА!"
    echo "------------------------------------------------------"
    echo "Бот успешно запущен. Проверьте сообщения в Telegram."
    echo "Управление: sh $SERVICE_FILE {start|stop|restart|status}"
    echo "------------------------------------------------------"
}

# --- 6. Точка входа ---

case "$1" in
    --uninstall)
        if [ "$AUTO_CONFIRM" = "false" ]; then
            echo "ВНИМАНИЕ: Это действие полностью удалит бота, все его компоненты и конфигурационные файлы."
            printf "Вы уверены, что хотите продолжить? (y/N): "
            read -r confirmation
            case "$confirmation" in
                [yY]|[yY][eE][sS]) ;;
                *) echo "Удаление отменено."; exit 0 ;;
            esac
        fi
        do_uninstall
        exit 0
        ;;
    --install)
        shift
        do_install "$@"
        ;;
    --update)
        if [ "$AUTO_CONFIRM" = "false" ]; then
            echo "ВНИМАНИЕ: Будут загружены и установлены последние версии файлов бота."
            echo "Ваши настройки, ключи и списки затронуты не будут."
            printf "Вы уверены, что хотите продолжить? (y/N): "
            read -r confirmation
            case "$confirmation" in
                [yY]|[yY][eE][sS]) ;;
                *) echo "Обновление отменено."; exit 0 ;;
            esac
        fi
        do_update
        ;;
    *)
        echo "Использование: $0 КОМАНДА [ПАРАМЕТРЫ]"
        echo ""
        echo "Команды:"
        echo "  --install      Установить бота. Можно указать параметры доступа:"
        echo "                   --token=<BOT_TOKEN>"
        echo "                   --user-id=<USER_ID>"
        echo "  --update       Обновить файлы бота до последней версии"
        echo "  --uninstall    Полностью удалить бота и его компоненты"
        echo "  -y             Автоматически подтверждать все запросы"
        echo ""
        echo "Пример:"
        echo "  $0 --install --token=123:ABC --user-id=456"
        echo "  $0 --update -y"
        ;;
esac
