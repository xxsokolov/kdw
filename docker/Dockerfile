# Используем стандартный, надежный образ Alpine Linux
FROM alpine:latest

# Устанавливаем только базовые зависимости, НЕ включая пакеты служб
RUN apk add --no-cache python3 py3-pip git curl jq nano ipset bind-tools

# Устанавливаем рабочую директорию
WORKDIR /opt/etc/kdw

# Копируем только requirements.txt для кэширования слоя с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip3 install -r requirements.txt --break-system-packages

# Копируем все остальные файлы проекта
COPY . .

# Создаем директории, которые имитируют структуру KeeneticOS
# /etc/init.d - стандартный путь для init-скриптов в Alpine/OpenWrt
RUN mkdir -p /etc/init.d /opt/etc/unblock /opt/bin

# Делаем основной скрипт исполняемым
RUN chmod +x bootstrap.sh

# Копируем entrypoint в корень и делаем его исполняемым для надежности
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Копируем и делаем исполняемыми скрипты из референсного проекта
RUN sed -i '1s|#!/bin/bash|#!/bin/sh|' bypass_keenetic-main/unblock_update.sh
COPY bypass_keenetic-main/unblock_update.sh /opt/bin/unblock_update.sh
RUN chmod +x /opt/bin/unblock_update.sh

# Копируем примеры файлов списков для тестирования ListManager
COPY bypass_keenetic-main/unblocksh.txt /opt/etc/unblock/unblocksh.txt
COPY bypass_keenetic-main/unblocktor.txt /opt/etc/unblock/unblocktor.txt

# Указываем, что при запуске контейнера нужно выполнить наш entrypoint
ENTRYPOINT ["/entrypoint.sh"]
