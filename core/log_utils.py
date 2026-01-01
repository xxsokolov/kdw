import logging
import subprocess
import sys
from configparser import ConfigParser
import os


class ContextualFormatter(logging.Formatter):
    """
    Кастомный форматтер, который добавляет в запись ID пользователя.
    Если ID не передан, используется значение по умолчанию 'SYSTEM'.
    """
    def format(self, record):
        # Проверяем: если атрибута нет ИЛИ он равен None, ставим 'SYSTEM'
        user_id = getattr(record, 'user_id', None)
        record.user_id = user_id if user_id is not None else 'SYSTEM'
        return super().format(record)


class KeeneticSystemHandler(logging.Handler):
    """
    Кастомный обработчик для пересылки логов в системный журнал KeeneticOS.
    Использует системную утилиту 'logger', что гарантирует корректную
    работу фильтров и цветовой индикации в веб-интерфейсе роутера.
    """

    # Соответствие уровней Python уровням Syslog для подсветки в GUI
    # DEBUG/INFO - белый, WARNING - желтый, ERROR/CRITICAL - красный
    LOG_LEVEL_MAP = {
        logging.DEBUG: 'user.debug',
        logging.INFO: 'user.info',
        logging.WARNING: 'user.warn',
        logging.ERROR: 'user.err',
        logging.CRITICAL: 'user.crit'
    }

    def emit(self, record):
        try:
            # Формируем текст сообщения через форматтер
            msg = self.format(record)
            # Определяем уровень важности для раскраски в журнале
            priority = self.LOG_LEVEL_MAP.get(record.levelno, 'user.info')

            # Вызов системной команды:
            # -p: задает уровень (для цвета)
            # -t: задает тег/имя (отображается в колонке "Отправитель")
            subprocess.run(
                ['logger', '-p', priority, '-t', record.name, msg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception:
            self.handleError(record)


def get_logger(name='KDW-Bot'):
    """
    Настройка системы логирования.
    Читает уровень из kdw.cfg или использует INFO по умолчанию.

    Args:
        name (str): Имя отправителя, которое будет видно в журнале Keenetic.

    Returns:
        logging.Logger: Настроенный объект логгера.
    """
    logger = logging.getLogger(name)
    
    # Определение уровня логирования
    config_level = 'INFO'
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(script_dir, '..', 'kdw.cfg')
        if os.path.exists(config_file):
            config = ConfigParser()
            config.read(config_file)
            if config.has_option('logging', 'level'):
                config_level = config.get('logging', 'level').upper()
    except Exception:
        pass # В случае ошибки будет использован уровень INFO

    # Получаем атрибут уровня из модуля logging (e.g., logging.INFO)
    # Если уровень в конфиге некорректный, по умолчанию ставим INFO
    level = getattr(logging, config_level, logging.INFO)
    logger.setLevel(level)

    # Очистка существующих обработчиков (защита от дублирования строк в консоли)
    if logger.handlers:
        logger.handlers.clear()

    # --- БЛОК 1: Системный журнал Keenetic (GUI) ---
    syslog_handler = KeeneticSystemHandler()
    syslog_format = ContextualFormatter('[%(user_id)s] - %(message)s')
    syslog_handler.setFormatter(syslog_format)
    logger.addHandler(syslog_handler)

    # --- БЛОК 2: Консольный вывод (SSH / Docker) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_format = ContextualFormatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s: [%(user_id)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    return logger


def set_level(level_name: str, user_id=None):
    """
    Динамически изменяет уровень логирования.
    
    Args:
        level_name (str): 'INFO', 'WARNING', 'ERROR', 'DEBUG'.
        user_id (str, optional): ID пользователя для лога.
    """
    # Получаем атрибут уровня из модуля logging. По умолчанию INFO.
    level = getattr(logging, level_name.upper(), logging.INFO)
    log.setLevel(level)
    log.info(f"Уровень логирования изменен на {level_name.upper()}", extra={'user_id': user_id})


log = get_logger()

# # Примеры записей с разной подсветкой в веб-интерфейсе:
# log.info("Система запущена")  # Обычный текст
# log.warning("Низкий заряд батареи")  # Желтая подсветка
# log.error("Сбой подключения к API")  # Красная подсветка
