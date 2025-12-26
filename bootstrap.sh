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
#   sh bootstrap.sh --install [--token=TOKEN --user-id=ID]
#   sh bootstrap.sh --update
#   sh bootstrap.sh --uninstall
#
# Автор: xxsokolov
# GitHub: https://github.com/xxsokolov/KDW
# =================================================================
#
# --- 1. Конфигурация ---
INSTALL_DIR="/opt/etc/kdw"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/xxsokolov/kdw.git"
CPYTHON_REPO_URL="https://github.com/python/cpython.git"
MANIFEST="${INSTALL_DIR}/install.manifest"

# Список системных пакетов для архитектуры mipselsf-k3.4
PKGS="python3 python3-pip jq git git-http ipset dnsmasq-full shadowsocks-libev-ss-redir trojan v2ray-core tor tor-geoip"

# Карта соответствия пакетов и их скриптов инициализации для проверки установки
PKG_MAP="
    shadowsocks-libev-ss-redir:shadowsocks
    trojan-plus:trojan
    v2ray-core:v2ray
    tor:tor
    dnsmasq-full:dnsmasq
"

# Список служб для автоматизированного управления (остановка/запуск/очистка)
MANAGED_SERVICES="shadowsocks trojan v2ray tor dnsmasq kdwbot"

# --- 2. Вспомогательные функции ---

# Вывод этапов установки
echo_step() { printf "\033[0;36m->\033[0m %s\n" "$1"; }
# Вывод успешного завершения
echo_ok() { printf "\033[0;32m[OK] %s\033[0m\n" "$1"; }
# Вывод ошибки и выход
echo_err() { printf "\033[0;31m[ERROR] %s\033[0m\n" "$1"; exit 1; }

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
    [ $res -ne 0 ] && { echo "$OUTPUT"; echo_err "$text завершилось с ошибкой"; }
    echo_ok "$text"
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
                "$file" "$action" >/dev/null 2>&1
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
            # Проверка, что путь находится внутри /opt/
            case "$path" in
                /opt/*)
                    case $type in
                        file|dir) [ -e "$path" ] && rm -rf "$path" ;;
                        pkg) opkg remove "$path" --autoremove >/dev/null 2>&1 ;;
                    esac
                    ;;
                *)
                    echo "  ! Пропуск удаления небезопасного пути: $path"
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

# --- 5. Установка ---

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
            # Перевод Shadowsocks из режима клиента (local) в режим прозрачного прокси (redir)
            [ "$svc" = "shadowsocks" ] && sed -i 's/ss-local/ss-redir/g' "$svc_file"
        fi
    done

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
    cp -r /opt/tmp/repo/core /opt/tmp/repo/kdw_bot.py /opt/tmp/repo/requirements.txt "$INSTALL_DIR/"
    rm -rf /opt/tmp/repo

    # Создание изолированного виртуального окружения Python
    run_with_spinner "Создание venv" python3 -m venv "$VENV_DIR"
    run_with_spinner "Установка зависимостей через pip" "$VENV_DIR/bin/pip" install --upgrade pip -r "$INSTALL_DIR/requirements.txt"

    # Генерация конфигурационного файла
    cat > "$INSTALL_DIR/kdw.cfg" << EOF
[telegram]
token = $BOT_TOKEN
access_ids = [$USER_ID]
EOF
    add_m "file:$INSTALL_DIR/kdw.cfg"

    # Создание службы автозапуска S99kdwbot
    SERVICE_FILE="/opt/etc/init.d/S99kdwbot"
    cat > "$SERVICE_FILE" << EOF
#!/bin/sh
# KDW Bot Service (Entware)
BOT_PATH="${INSTALL_DIR}/kdw_bot.py"
PYTHON_EXEC="${VENV_DIR}/bin/python"
PID_FILE="/var/run/kdw_bot.pid"
start() {
    if [ -f "\$PID_FILE" ]; then return; fi
    \$PYTHON_EXEC \$BOT_PATH > /dev/null 2>&1 &
    echo \$! > \$PID_FILE
}
stop() {
    [ -f "\$PID_FILE" ] && kill \$(cat \$PID_FILE) && rm -f \$PID_FILE
}
case "\$1" in
    start) start ;; stop) stop ;; restart) stop; sleep 2; start ;;
esac
EOF
    chmod +x "$SERVICE_FILE"
    add_m "file:$SERVICE_FILE"

    # Регистрация всех файлов проекта в манифест
    find "$INSTALL_DIR" -mindepth 1 | while read -r f; do
        [ -d "$f" ] && add_m "dir:$f" || add_m "file:$f"
    done

    # Финальный запуск всех компонентов
    manage_services "start"

    echo ""
    echo_ok "УСТАНОВКА ЗАВЕРШЕНА!"
    echo "------------------------------------------------------"
    echo "Бот успешно запущен. Проверьте сообщения в Telegram."
    echo "Логирование: /opt/var/log/kdw_bot.log"
    echo "Управление: sh $0 {--update|--uninstall}"
    echo "------------------------------------------------------"
}

# --- 6. Точка входа ---

# Сохраняем все аргументы для возможной передачи
ARGS="$@"

case "$1" in
    --uninstall) do_uninstall; exit 0 ;;
    --install)   shift; do_install "$@" ;;
    --update)
        echo_step "Начало процесса обновления..."
        CONFIG_ARGS=""
        if [ -f "$INSTALL_DIR/kdw.cfg" ]; then
            # Более надежный способ извлечь токен и ID
            TOKEN=$(awk -F' = ' '/^token =/ {print $2}' "$INSTALL_DIR/kdw.cfg")
            USER_ID=$(sed -n 's/^access_ids = \[\(.*\)\].*/\1/p' "$INSTALL_DIR/kdw.cfg")
            [ -n "$TOKEN" ] && [ -n "$USER_ID" ] && CONFIG_ARGS="--token=$TOKEN --user-id=$USER_ID"
        fi

        # Гарантированная очистка временного файла
        TMP_SCRIPT="/tmp/bootstrap_update.sh"
        trap "rm -f '$TMP_SCRIPT'" EXIT HUP INT QUIT TERM

        if ! curl -sL "https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh?$(date +%s)" -o "$TMP_SCRIPT"; then
            echo_err "Не удалось скачать скрипт обновления."
        fi

        # Запускаем новый скрипт с нужными аргументами
        do_uninstall && sh "$TMP_SCRIPT" --install $CONFIG_ARGS

        echo_ok "Обновление завершено." ;;
    *)
        echo "Использование: $0 КОМАНДА [ПАРАМЕТРЫ]"
        echo ""
        echo "Команды:"
        echo "  --install      Установить бота. Можно указать параметры доступа:"
        echo "                   --token=<BOT_TOKEN>"
        echo "                   --user-id=<USER_ID>"
        echo "  --update       Обновить бота до последней версии"
        echo "  --uninstall    Полностью удалить бота и его компоненты"
        echo ""
        echo "Пример:"
        echo "  $0 --install --token=123:ABC --user-id=456"
        ;;
esac
