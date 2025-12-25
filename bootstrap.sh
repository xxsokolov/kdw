#!/bin/sh

# KDW Bot Installer (Bootstrap) - Single Source of Truth
# https://github.com/xxsokolov/KDW

# --- Configuration ---
INSTALL_DIR="/opt/etc/kdw"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/xxsokolov/KDW.git"
TMP_REPO_DIR="/opt/tmp/kdw_repo"
# Зависимости, которые будут установлены и удалены вместе с проектом
OPKG_DEPENDENCIES="python3 python3-pip jq git git-http dnsmasq-full ipset shadowsocks-libev-ss-redir"
# Файл-манифест для чистого удаления
MANIFEST_FILE="${INSTALL_DIR}/install.manifest"

# --- Functions ---
echo_step() { printf "-> %s\n" "$1"; }
echo_success() { printf "\033[0;32m[OK] %s\033[0m\n" "$1"; }
echo_error() { printf "\033[0;31m[ERROR] %s\033[0m\n" "$1"; exit 1; }
add_to_manifest() { echo "$1" >> "$MANIFEST_FILE"; }

# --- Argument Parsing ---
ACTION="install"
POSTINST_ARGS=""
# Простой и надежный парсинг первого аргумента
if [ -n "$1" ]; then
    case $1 in
        --install) ACTION="install"; shift ;;
        --update) ACTION="update"; shift ;;
        --uninstall) ACTION="uninstall"; shift ;;
        *) ACTION="install" ;;
    esac
    POSTINST_ARGS="$@"
fi

# --- Action: Uninstall ---
if [ "$ACTION" = "uninstall" ]; then
    echo_step "Запуск полного удаления KDW Bot..."
    if [ ! -f "$MANIFEST_FILE" ]; then
        echo "Манифест установки не найден. Попытка стандартного удаления..."
        [ -f /opt/etc/init.d/S99kdwbot ] && sh /opt/etc/init.d/S99kdwbot stop
        rm -rf "$INSTALL_DIR" /opt/etc/init.d/S99kdwbot /opt/etc/init.d/S99unblock
        opkg remove --force-depends $OPKG_DEPENDENCIES
        rm -f /opt/etc/dnsmasq.conf /opt/etc/dnsmasq.conf-opkg
        echo_success "Стандартное удаление завершено."
        exit 0
    fi

    echo_step "Остановка служб..."
    sh /opt/etc/init.d/S99kdwbot stop

    # Сначала читаем список пакетов в переменную, пока манифест не удален
    PACKAGES_TO_REMOVE=$(grep '^pkg:' "$MANIFEST_FILE" | cut -d':' -f2- | tr '\n' ' ')

    echo_step "Удаление файлов и директорий из манифеста..."
    # Используем awk для обратного чтения файла (аналог tac)
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

    echo_step "Удаление системных пакетов из манифеста..."
    if [ -n "$PACKAGES_TO_REMOVE" ]; then
        opkg remove --force-depends $PACKAGES_TO_REMOVE
    fi
    rm -f /opt/etc/dnsmasq.conf /opt/etc/dnsmasq.conf-opkg
    echo_success "Системные пакеты удалены."

    echo_success "KDW Bot полностью удален."
    exit 0
fi

# --- Action: Update ---
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

    echo_step "Скачивание последней версии установщика..."
    curl -sL -o /tmp/bootstrap_new.sh https://raw.githubusercontent.com/xxsokolov/KDW/main/bootstrap.sh
    if [ $? -ne 0 ]; then echo_error "Не удалось скачать новый установщик."; fi

    echo_step "Удаление старой версии..."
    sh $0 --uninstall

    echo_step "Установка новой версии..."
    sh /tmp/bootstrap_new.sh --install $POSTINST_ARGS

    rm /tmp/bootstrap_new.sh
    [ -f "$CONFIG_BACKUP" ] && rm "$CONFIG_BACKUP"
    echo_success "Обновление завершено!"
    exit 0
fi

# --- Action: Install ---
echo_step "Запуск установки KDW Bot..."

if [ -d "$INSTALL_DIR" ]; then
    echo_step "Обнаружена старая установка. Полное удаление перед новой установкой..."
    sh $0 --uninstall
    echo_success "Старая версия полностью удалена."
fi

echo_step "Установка системных зависимостей..."
opkg update > /dev/null
# Используем --force-maintainer для перезаписи измененных конфигов
opkg install --force-maintainer $OPKG_DEPENDENCIES
if [ $? -ne 0 ]; then echo_error "Не удалось установить базовые пакеты."; fi
echo_success "Системные зависимости установлены."

echo_step "Клонирование репозитория KDW Bot..."
rm -rf "$TMP_REPO_DIR"
git clone --depth 1 "$REPO_URL" "$TMP_REPO_DIR"
if [ $? -ne 0 ]; then echo_error "Не удалось клонировать репозиторий."; fi

echo_step "Копирование рабочих файлов и создание манифеста..."
mkdir -p "$INSTALL_DIR"
rm -f "$MANIFEST_FILE"
touch "$MANIFEST_FILE"
add_to_manifest "dir:$INSTALL_DIR"

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

for pkg in $OPKG_DEPENDENCIES; do add_to_manifest "pkg:$pkg"; done
echo_success "Манифест пакетов создан."

echo_step "Создание виртуального окружения Python..."
python3 -m venv "$VENV_DIR"
if [ $? -ne 0 ]; then echo_error "Не удалось создать виртуальное окружение."; fi
add_to_manifest "dir:$VENV_DIR"
echo_success "Виртуальное окружение создано."

echo_step "Обновление pip..."
${VENV_DIR}/bin/python -m pip install --upgrade pip
if [ $? -ne 0 ]; then echo_error "Не удалось обновить pip."; fi

echo_step "Установка Python-библиотек..."
${VENV_DIR}/bin/pip install --upgrade -r "${INSTALL_DIR}/requirements.txt"
if [ $? -ne 0 ]; then echo_error "Не удалось установить Python-библиотеки."; fi
echo_success "Python-библиотеки установлены."

# --- Финальная настройка ---
echo_step "Финальная настройка..."

# Парсим аргументы, переданные в bootstrap.sh
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
