import os
import logging
from logging import Logger

class KeeneticLogger(Logger):
    """
    Кастомный логгер, который пишет в системный журнал Keenetic через утилиту logmsg.
    """
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
        # Преобразуем уровень logging в уровень logmsg
        if level >= logging.ERROR:
            log_level = 'err'
        elif level >= logging.WARNING:
            log_level = 'warn'
        else:
            log_level = 'info'
        
        # Форматируем сообщение
        if args:
            msg = msg % args
        
        # Очищаем сообщение от кавычек, чтобы не сломать shell-команду
        safe_msg = msg.replace('"', "'").replace('`', "'")
        
        # Формируем и выполняем команду
        command = f'logmsg {log_level} "KDW-Bot: {safe_msg}"'
        try:
            os.system(command)
        except Exception:
            # Если что-то пошло не так, просто печатаем в консоль
            print(f"KDW-Bot ({log_level}): {msg}")

class Log:
    def __init__(self, debug=False):
        # Заменяем стандартный класс логгера на наш кастомный
        logging.setLoggerClass(KeeneticLogger)
        
        self.log = logging.getLogger(__name__)
        
        if debug:
            self.log.setLevel(logging.DEBUG)
        else:
            self.log.setLevel(logging.INFO)

        # Убираем все стандартные обработчики, так как мы пишем напрямую через os.system
        for handler in self.log.handlers[:]:
            self.log.removeHandler(handler)
