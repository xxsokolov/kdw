import logging
import sys

class CustomFormatter(logging.Formatter):
    grey = '\x1b[38;21m'
    green = '\x1b[32m'
    blue = '\x1b[38;5;39m'
    yellow = '\x1b[38;5;226m'
    red = '\x1b[31m'
    bold_red = '\x1b[38;5;196m'
    reset = '\x1b[0m'

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.green + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class Log:
    def __init__(self, debug=False):
        if debug:
            self.log_level = logging.DEBUG
        else:
            self.log_level = logging.INFO

        global_format = ("[%(asctime)s] - PID:%(process)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s: %("
                         "message)s")
        self.log = logging.getLogger(None if debug else __name__)
        self.log.setLevel(self.log_level)
        
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(self.log_level)
        stdout_handler.setFormatter(CustomFormatter(fmt=global_format))
        self.log.addHandler(stdout_handler)

    def get_level_name(self):
        return logging.getLevelName(self.log.getEffectiveLevel())
