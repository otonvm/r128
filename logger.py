# -*- coding: utf-8 -*-

import os
import sys
import logging
import inspect
import traceback

import colorama

__all__ = ["Logger"]


class ColorHandler(logging.StreamHandler):
    def __init__(self, stream=sys.stderr):
        super().__init__(colorama.AnsiToWin32(stream).stream)
        self._stream = stream

    @property
    def is_tty(self):
        isatty = getattr(self._stream, 'isatty', None)
        return isatty and isatty()

    def format(self, record):
        message = logging.StreamHandler.format(self, record)

        if self.is_tty:
            if record.levelno == logging.DEBUG:
                style = colorama.Style.DIM + colorama.Back.CYAN + colorama.Fore.BLUE
                # style = colorama.Style.DIM + colorama.Fore.WHITE

            elif record.levelno == logging.INFO:
                style = colorama.Style.BRIGHT + colorama.Fore.WHITE

            elif record.levelno == logging.WARN:
                style = colorama.Style.BRIGHT + colorama.Fore.YELLOW

            elif record.levelno == logging.ERROR:
                style = colorama.Style.BRIGHT + colorama.Fore.RED

            elif record.levelno == logging.CRITICAL:
                style = colorama.Style.BRIGHT + colorama.Back.RED + colorama.Fore.WHITE

            else:
                style = colorama.Style.NORMAL + colorama.Fore.WHITE

            return style + message + colorama.Style.RESET_ALL

        else:
            return message


class LogFormat(logging.Formatter):
    def __init__(self):
        super().__init__()

    def format(self, record):
        if record.levelno == logging.DEBUG:
            self._style = logging._STYLES['{'][0]("DEBUG: {message}")

        elif record.levelno == logging.INFO:
            self._style = logging._STYLES['{'][0]("{message}")

        elif record.levelno == logging.WARNING:
            self._style = logging._STYLES['{'][0]("WARN: {message}")

        elif record.levelno == logging.ERROR:
            self._style = logging._STYLES['{'][0]("ERROR: {message}")

        elif record.levelno == logging.CRITICAL:
            self._style = logging._STYLES['{'][0]("CRITICAL ERROR: {message}")

        else:
            self._style = logging._STYLES['{'][0]("{message}")

        return logging.Formatter.format(self, record)


class Singleton(type):
    def __init__(self, *args, **kwargs):
        self.__instance = None
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.__instance is None:
            self.__instance = super().__call__(*args, **kwargs)
            return self.__instance
        else:
            return self.__instance


class Logger(metaclass=Singleton):
    LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, name):
        self._level = logging.INFO
        self._log = logging.getLogger(name)
        self._logger_set = False

    @property
    def level(self):
        return self._level

    @level.setter
    def level(self, log_level):
        try:
            self._level = getattr(logging, log_level)
            self._update_log_level()
        except AttributeError:
            raise AttributeError("Valid options: {}".format(", ".join(self.LEVELS))) from None

    def _update_log_level(self):
        if self._log.level != self._level:
            self._log.setLevel(self._level)

    def _setup_logger(self):
        handler = ColorHandler()
        format = LogFormat()
        handler.setFormatter(format)
        self._log.addHandler(handler)
        self._update_log_level()
        self._logger_set = True

    def _exceptions(self, exc_type, exc_value, exc_traceback):
        self._log.debug("", exc_info=(exc_type, exc_value, exc_traceback))

    def handle_exceptions(self):
        sys.excepthook = self._exceptions

    def d(self, msg):
        if not self._logger_set:
            self._setup_logger()
        if self._log.isEnabledFor(logging.DEBUG):
            # inspect one frame backwards:
            frame = inspect.currentframe().f_back
            trace_back = traceback.extract_stack(frame)[-1]
            module = os.path.basename(trace_back[0])  # filename
            line = trace_back[1]  # line number
            self._log.debug("line {} in {}: {}".format(line, module, msg))

    def i(self, msg):
        if not self._logger_set:
            self._setup_logger()
        if self._log.isEnabledFor(logging.INFO):
            self._log.info(msg)

    def w(self, msg):
        if not self._logger_set:
            self._setup_logger()
        if self._log.isEnabledFor(logging.WARNING):
            self._log.warning(msg)

    def e(self, msg):
        if not self._logger_set:
            self._setup_logger()
        if self._log.isEnabledFor(logging.ERROR):
            self._log.error(msg)

    def c(self, msg):
        if not self._logger_set:
            self._setup_logger()
        if self._log.isEnabledFor(logging.CRITICAL):
            self._log.critical(msg)


if __name__ == "__main__":
    log = Logger("test")
    log.level = "DEBUG"
    log.d("debug message")
    log.i("info message")
    log.w("warn message")
    log.e("error message")
    log.c("critical message")
    log.handle_exceptions()
    raise SystemError("test error")
