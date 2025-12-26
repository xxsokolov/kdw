#!/bin/sh
#
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
#
# --- 1. Конфигурация ---
INSTALL_DIR="/opt/etc/kdw"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/xxsokolov/kdw.git"
MANIFEST="${INSTALL_DIR}/install.manifest"

# Список пакетов, доступных для mipselsf-k3.4
PKGS="python3 python3-pip jq git git-http ipset dnsmasq-full shadowsocks-libev-ss-redir trojan v2ray-core tor tor-geoip"

# Словарь ПАКЕТ:СЛУЖБА для автоматической проверки и фикса
# Формат: "имя_пакета:имя_init_скрипта"
PKG_MAP="
    shadowsocks-libev-ss-redir:shadowsocks
    trojan-plus:trojan
    v2ray-core:v2ray
    tor:tor
    dnsmasq-full:dnsmasq
"

# Список имен для автоматического управления (stop/delete)
MANAGED_SERVICES="kdwbot shadowsocks trojan v2ray tor dnsmasq"

# --- 2. Вспомогательные функции ---
echo_step() { printf "\033[0;36m->\033[0m %s\n" "$1"; }
echo_ok() { printf "\033[0;32m[OK] %s\033[0m\n" "$1"; }
echo_err() { printf "\033[0;31m[ERROR] %s\033[0m\n" "$1"; exit 1; }

add_m() {
    [ ! -d "$INSTALL_DIR" ] && mkdir -p "$INSTALL_DIR"
    echo "$1" >> "$MANIFEST"
}

# Поиск файла в /opt/etc/init.d/ по маске
find_svc() {
    ls /opt/etc/init.d/S[0-9][0-9]$1* 2>/dev/null | head -n 1
}

# Универсальный спиннер
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
    [ $res -ne 0 ] && { echo "$OUTPUT"; echo_err "$text failed"; }
    echo_ok "$text"
}

# --- 3. Управление службами ---
manage_services() {
    local action=$1
    echo_step "Действие '$action' для служб..."
    for name in $MANAGED_SERVICES; do
        local file=$(find_svc "$name")
        if [ -f "$file" ]; then
            if [ "$action" = "delete" ]; then
                rm -f "$file" && echo "  - Файл $file удален"
            else
                echo "  - Служба $(basename "$file") $action"
                "$file" "$action" >/dev/null 2>&1
            fi
        fi
    done
}

# --- 4. Удаление ---
do_uninstall() {
    manage_services "stop"
    if [ -f "$MANIFEST" ]; then
        echo_step "Удаление по манифесту..."
        sed '1!G;h;$!d' "$MANIFEST" | while IFS=: read -r type path; do
            case $type in
                file|dir) [ -e "$path" ] && rm -rf "$path" ;;
                pkg) opkg remove "$path" --autoremove >/dev/null 2>&1 ;;
            esac
        done
    fi
    rm -rf "$INSTALL_DIR"
    manage_services "delete"
    find /opt/etc/ -name "*-opkg" -delete
    echo_ok "Система очищена."
}

# --- 5. Установка ---
do_install() {
    [ -d "$INSTALL_DIR" ] && echo_err "Бот уже установлен."

    run_with_spinner "Обновление opkg" opkg update
    run_with_spinner "Установка пакетов" opkg install $PKGS

    # Декларативная проверка и фикс
    echo_step "Проверка init-скриптов..."
    for pair in $PKG_MAP; do
        pkg=${pair%%:*}
        svc=${pair#*:}
        svc_file=$(find_svc "$svc")

        if [ ! -f "$svc_file" ]; then
            echo "  ! Фикс: $pkg (force-reinstall)"
            opkg install "$pkg" --force-reinstall >/dev/null 2>&1
            svc_file=$(find_svc "$svc")
        fi

        if [ -f "$svc_file" ]; then
            chmod +x "$svc_file"
            add_m "file:$svc_file"
            [ "$svc" = "shadowsocks" ] && sed -i 's/ss-local/ss-redir/g' "$svc_file"
        fi
    done

    # Лечение venv (обязательно для Entware 2025)
    if ! python3 -m venv --help >/dev/null 2>&1; then
        echo_step "Восстановление модуля venv..."
        tmp_v="/opt/tmp/v_fix"; mkdir -p "$tmp_v"
        run_with_spinner "Клонирование CPython" git clone --depth=1 --branch=3.11 github.com "$tmp_v"
        cp -r "$tmp_v/Lib/venv" "$tmp_v/Lib/ensurepip" /opt/lib/python3.11/
        rm -rf "$tmp_v"
    fi

    # Инициализация манифеста
    mkdir -p "$INSTALL_DIR"
    : > "$MANIFEST"
    for p in $PKGS; do add_m "pkg:$p"; done

    # Код бота
    run_with_spinner "Загрузка кода бота" git clone --depth 1 "$REPO_URL" "/opt/tmp/repo"
    cp -r /opt/tmp/repo/core /opt/tmp/repo/kdw_bot.py /opt/tmp/repo/requirements.txt "$INSTALL_DIR/"
    rm -rf /opt/tmp/repo

    # Python
    run_with_spinner "Создание venv" python3 -m venv "$VENV_DIR"
    run_with_spinner "Установка pip-зависимостей" "$VENV_DIR/bin/pip" install --upgrade pip -r "$INSTALL_DIR/requirements.txt"

    # Запись файлов в манифест
    find "$INSTALL_DIR" -mindepth 1 | while read -r f; do
        [ -d "$f" ] && add_m "dir:$f" || add_m "file:$f"
    done

    echo_ok "Установка завершена. Протоколы SS, Trojan, VMESS, Tor готовы к управлению."
}

# --- 6. Запуск ---
case "$1" in
    --uninstall) do_uninstall; exit 0 ;;
    --install)   do_install ;;
    --update)
        [ -f "$INSTALL_DIR/kdw.cfg" ] && cp "$INSTALL_DIR/kdw.cfg" "/tmp/kdw.cfg.bak"
        curl -sL "raw.githubusercontent.com(date +%s)" -o /tmp/bs.sh
        do_uninstall && sh /tmp/bs.sh --install
        [ -f "/tmp/kdw.cfg.bak" ] && mv "/tmp/kdw.cfg.bak" "$INSTALL_DIR/kdw.cfg"
        echo_ok "Обновлено." ;;
    *) echo "Usage: $0 {--install|--update|--uninstall}" ;;
esac