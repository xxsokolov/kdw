import logging
import os
from logging.handlers import SysLogHandler


def get_logger(name='KDW-Bot', debug=False):
    """
    Настраивает логгер для KeeneticOS.
    Приоритет: 1. Локальный сокет /dev/log 2. Сетевой UDP 514 3. Консоль (Stream)
    """
    logger = logging.getLogger(name)

    # Установка уровня логирования
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Очистка старых обработчиков (предотвращает дублирование логов)
    if logger.hasHandlers():
        logger.handlers.clear()

    handler = None
    log_format = '%(name)s: %(message)s'  # Стандарт для Syslog (время добавит система)

    # 1. Пробуем подключиться к системному сокету (самый быстрый способ)
    if os.path.exists('/dev/log'):
        try:
            handler = SysLogHandler(address='/dev/log', facility=SysLogHandler.LOG_USER)
        except Exception:
            handler = None

    # 2. Если сокет недоступен, пробуем локальный UDP порт (стандарт syslog)
    if handler is None:
        try:
            handler = SysLogHandler(address=('127.0.0.1', 514), facility=SysLogHandler.LOG_USER)
        except Exception:
            handler = None

    # 3. Если syslog полностью недоступен, пишем в стандартный вывод (stdout)
    if handler is None:
        handler = logging.StreamHandler()
        # Для консоли добавляем время и уровень, так как там нет системного префикса
        log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        logger.warning("Системный журнал (syslog) недоступен. Переход на StreamHandler.")

    # Настройка форматирования и добавление обработчика
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Создаем экземпляр для использования в проекте
# В основном файле можно будет сделать: from logger import log
log = get_logger()
