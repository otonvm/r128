# -*- coding: utf-8 -*-

import sys

import colorama
colorama.init(wrap=False)
stream = colorama.AnsiToWin32(sys.stderr).stream

import config
conf = config.Config()

import logger
log = logger.Logger(__name__)
if conf.log_level:
    log.level = conf.log_level
else:
    log.level = "DEBUG"


def print_stderr(msg):
    print(colorama.Fore.GREEN + str(msg) + colorama.Style.RESET_ALL, file=stream, flush=True)


def print_and_exit(msg, errorlevel=0):
    print_stderr(msg)
    raise SystemExit(errorlevel)


def log_and_exit(msg, errorlevel=0):
    log.e(msg)
    raise SystemExit(errorlevel)
