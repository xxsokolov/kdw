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
# --- 1. Расширяемая конфигурация ---
INSTALL_DIR="/opt/etc/kdw"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/xxsokolov/KDW.git"
TMP_REPO_DIR="/opt/tmp/kdw_repo"
MANIFEST_FILE="${INSTALL_DIR}/install.manifest"

# Явные списки пакетов и служб для удобства правок
PKGS="python3 python3-pip jq git git-http ipset dnsmasq-full sing-box tor tor-geoip"
SERVICES="kdwbot sing-box tor dnsmasq"

# --- 2. Вспомогательные функции ---
echo_step() { printf "\033[0;36m->\033[0m %s\n" "$1"; }
echo_ok() { printf "\033[0;32m[OK] %s\033[0m\n" "$1"; }
echo_err() { printf "\033[0;31m[ERROR] %s\033[0m\n" "$1"; exit 1; }
add_m() { [ -f "$MANIFEST" ] && echo "$1" >> "$MANIFEST"; }

# Остановка всех служб (поиск по маске S??название)
stop_all() {
    echo_step "Остановка связанных служб..."
    for s in $SERVICES; do
        for f in /opt/etc/init.d/S[0-9][0-9]$s*; do
            [ -f "$f" ] && "$f" stop >/dev/null 2>&1
        done
    done
}

# --- 3. Логика удаления ---
do_uninstall() {
    stop_all

    if [ -f "$MANIFEST" ]; then
        echo_step "Удаление компонентов по манифесту..."
        # Читаем манифест с конца, чтобы сначала удалять файлы, потом папки
        sed '1!G;h;$!d' "$MANIFEST" | while IFS=: read -r type path; do
            case $type in
                file|dir) [ -e "$path" ] && rm -rf "$path" ;;
                pkg) opkg remove "$path" --autoremove >/dev/null 2>&1 ;;
            esac
        done
    fi

    # Финальная зачистка "хвостов"
    echo_step "Очистка системных путей..."
    rm -rf "$INSTALL_DIR"
    # Удаляем любые скрипты запуска из init.d по нашему списку служб
    for s in $SERVICES; do
        find /opt/etc/init.d/ -name "S[0-9][0-9]$s*" -delete
    done
    find /opt/etc/ -name "*-opkg" -delete
    echo_ok "Удаление завершено."
}

# --- 4. Логика установки ---
do_install() {
    [ -d "$INSTALL_DIR" ] && echo_err "Бот уже установлен. Используйте --update."

    echo_step "Обновление opkg и установка пакетов..."
    opkg update && opkg install $PKGS

    # Гарантированная проверка критических файлов (бич Entware)
    [ ! -f "/opt/etc/init.d/S24sing-box" ] && opkg install sing-box --force-reinstall
    [ ! -f "/opt/etc/init.d/S35tor" ] && opkg install tor --force-reinstall

    # Лечение модуля venv (в Entware он вырезан)
    if ! python3 -m venv --help >/dev/null 2>&1; then
        echo_step "Восстановление модуля venv (Entware fix)..."
        tmp_v="/opt/tmp/v_fix"
        mkdir -p "$tmp_v"
        git clone --depth=1 --branch=3.11 github.com "$tmp_v"
        cp -r "$tmp_v/Lib/venv" "$tmp_v/Lib/ensurepip" /opt/lib/python3.11/
        rm -rf "$tmp_v"
    fi

    # Подготовка папок и манифеста
    mkdir -p "$INSTALL_DIR"
    : > "$MANIFEST"
    for p in $PKGS; do add_m "pkg:$p"; done

    # Клонирование и копирование кода
    echo_step "Загрузка кода бота..."
    tmp_repo="/opt/tmp/repo"
    git clone --depth 1 "$REPO_URL" "$tmp_repo"
    cp -r "$tmp_repo/core" "$tmp_repo/kdw_bot.py" "$tmp_repo/requirements.txt" "$INSTALL_DIR/"
    rm -rf "$tmp_repo"

    # Создание Python окружения
    echo_step "Создание виртуального окружения (venv)..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip -r "$INSTALL_DIR/requirements.txt"

    # Запись всех созданных файлов в манифест (для корректного удаления)
    find "$INSTALL_DIR" -mindepth 1 | while read -r f; do
        [ -d "$f" ] && add_m "dir:$f" || add_m "file:$f"
    done

    # Добавляем в манифест найденные скрипты инициализации
    for s in $SERVICES; do
        f=$(ls /opt/etc/init.d/S[0-9][0-9]$s* 2>/dev/null | head -n 1)
        [ -n "$f" ] && [ -f "$f" ] && add_m "file:$f" && chmod +x "$f"
    done

    echo_ok "Установка VLESS/Trojan/SS/Tor завершена."
}

# --- 5. Основной переключатель ---
case "$1" in
    --uninstall)
        do_uninstall
        exit 0
        ;;
    --install)
        do_install
        ;;
    --update)
        echo_step "Обновление системы..."
        # Сохраняем конфиг перед удалением
        [ -f "$INSTALL_DIR/kdw.cfg" ] && cp "$INSTALL_DIR/kdw.cfg" "/tmp/kdw.cfg.bak"

        # Скачиваем новый инсталлер (обход кэша GitHub)
        curl -sL "raw.githubusercontent.com(date +%s)" -o /tmp/bs.sh

        do_uninstall
        sh /tmp/bs.sh --install

        # Возвращаем конфиг на место
        [ -f "/tmp/kdw.cfg.bak" ] && mv "/tmp/kdw.cfg.bak" "$INSTALL_DIR/kdw.cfg"
        echo_ok "Обновление завершено."
        ;;
    *)
        echo "Использование: $0 {--install|--update|--uninstall}"
        exit 1
        ;;
esac