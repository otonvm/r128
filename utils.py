# -*- coding: utf-8 -*-

import sys
import colorama
colorama.init(wrap=False)
stream = colorama.AnsiToWin32(sys.stderr).stream


def print_stderr(msg):
    print(colorama.Fore.GREEN + str(msg) + colorama.Style.RESET_ALL, file=stream, flush=True)


def print_and_exit(msg, errorlevel=0):
    print_stderr(msg)
    raise SystemExit(errorlevel)
