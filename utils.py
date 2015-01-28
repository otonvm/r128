# -*- coding: utf-8 -*-

import os
import sys
import pathlib

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


def locate_bin(bin_name, exception):
    if not issubclass(exception, Exception):
        raise AttributeError("exception must be a Exception type")

    log.d("trying to find {} binary".format(bin_name))

    # script folder should be among the first to be searched:
    frozen = getattr(sys, 'frozen', '')

    if frozen in ('dll', 'console_exe', 'windows_exe'):
        # py2exe:
        approot = pathlib.Path(sys.executable).parent

    else:
        # not frozen: in regular python interpreter
        approot = pathlib.Path(__file__).parent

    search_paths = []

    search_paths.append(approot)
    search_paths.extend(sys.path)

    # the add the system PATH:
    search_paths.extend(os.environ["PATH"].split(os.pathsep))

    bin_path = None
    for path in search_paths:
        path = pathlib.Path(path)
        log.d("searching inside {}".format(path))

        try:
            # create a list of all exe files in the folder beeing searched:
            executables = [str(exe) for exe in path.glob("**/*.exe")
                           if exe.is_file() and os.access(str(exe), os.X_OK)]
        except (KeyError, PermissionError):
            continue

        for exe in executables:
            if bin_name in exe.lower():
                bin_path = exe
                log.d("found ffmpeg bin: {}".format(bin_path))
                break

        # exe has been found, exit needless loops:
        if bin_path:
            break
    else:
        raise exception("Could not locate {} binary anywhere in PATH.".format(bin_name))

