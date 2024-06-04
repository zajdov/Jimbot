"""
logger.py
"""


import logging

from src.utils import concatenate


class ColorFormat(logging.Formatter):

    DEFAULT_FORMAT: str = '[%(asctime)s %(levelname)s]: %(message)s'

    FORMATS: dict = {
        logging.WARNING: f'\033[93m[%(asctime)s WARN]: %(message)s\033[0m',
        logging.ERROR: f'\033[91m{DEFAULT_FORMAT}\033[0m',
    }

    def format(self, record) -> str:
        fmt = self.FORMATS.get(record.levelno, self.DEFAULT_FORMAT)
        formatter = logging.Formatter(fmt, '%H:%M:%S')
        return formatter.format(record)


class Logger:

    def __init__(self, debug_enabled=False) -> None:
        self.log = logging.getLogger("logger")
        self.debug_enabled = debug_enabled

        handler = logging.StreamHandler()
        handler.setFormatter(ColorFormat())
        
        self.level = logging.DEBUG if debug_enabled else logging.INFO
        self.log.setLevel(self.level)
        self.log.addHandler(handler)

    def info(self, *args: any) -> None:
        self.log.info(concatenate(args))

    def warn(self, *args: any) -> None:
        self.log.warning(concatenate(args))

    def error(self, *args: any) -> None:
        self.log.error(concatenate(args))

    def debug(self, *args: any) -> None:
        self.log.debug(concatenate(args))


log = Logger()
