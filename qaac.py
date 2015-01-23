# -*- coding: utf-8 -*-

__all__ = ["Qaac", "QaacNotFoundError", "QaacProcessError", "QaacTestFailedError"]

import pathlib
import sys
import os
import re
import subprocess
from functools import partial

import config
conf = config.Config()

import logger
log = logger.Logger(__name__)
if conf.log_level:
    log.level = conf.log_level
else:
    log.level = "DEBUG"

from utils import print_stderr

from progressbar import ProgressBar, Percentage, Bar


class QaacNotFoundError(Exception):
    pass


class QaacProcessError(Exception):
    pass


class QaacTestFailedError(Exception):
    pass


class QaacProcess:
    def __init__(self, path, args=None, keep_stderr=False):
        if args and not isinstance(args, list):
            raise ValueError("you must provide a list for args")

        self._path = path
        self._args = args
        self._keep_stderr = keep_stderr

        self._cmd = []
        self._proc = None
        self._returncode = None
        self._interrupted = False
        self._full_stderr = []

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, value):
        if not isinstance(value, list):
            raise ValueError("you must provide a list for args")

        self._args = value

    def _run(self):
        log.d("starting subprocess: {}".format(self._cmd))
        try:
            self._proc = subprocess.Popen(self._cmd, stderr=subprocess.PIPE, bufsize=0)
        except FileNotFoundError as err:
            raise QaacNotFoundError(err.strerror) from None
        except OSError as err:
            raise QaacProcessError(err.strerror) from None

    def __enter__(self):
        log.d("__enter__")

        self._cmd.append(self._path)

        if self._args:
            self._cmd.extend(self._args)

        self._run()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        log.d("__exit__")

        if exc_type is not None:
            return False

        if self._proc.returncode is not 0:
            try:
                log.d("terminating process")
                self._proc.terminate()
                self._proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

        if self._interrupted:
            raise KeyboardInterrupt

        return True

    def __iter__(self):
        return self

    def __next__(self):
        buffer = []

        for err_char in iter(partial(self._proc.stderr.read, 1), b''):
            try:
                buffer.append(err_char.decode("utf-8"))
                if '\r' in buffer:
                    line = "".join(buffer).strip()
                    buffer.clear()

                    if self._keep_stderr:
                        self._full_stderr.append(line)

                    return line

            except KeyboardInterrupt:
                self._returncode = self._proc.poll()
                self._interrupted = True
                raise StopIteration
        else:
            self._returncode = self._proc.poll()
            raise StopIteration

    @property
    def returncode(self):
        return self._returncode

    @property
    def full_stderr(self):
        return self._full_stderr

    def clear_full_stderr(self):
        if self._full_stderr:
            self._full_stderr.clear()
            self._full_stderr = None


class Qaac:
    def __init__(self, path=None, debug=False):
        self.qaac_bin = path
        self._debug = debug

        self._full_stderr = []

        if not self.qaac_bin:
            self._locate_bin()
            self._test_bin()

        else:
            log.d("testing given path")

            if not self.qaac_bin.endswith(".exe") or not os.access(self.qaac_bin, os.X_OK):
                raise ValueError("path must be a path of an executable.")

            self._test_bin()

    def _locate_bin(self):
        # script folder should be among the first to be searched:
        search_paths = sys.path

        # the add the system PATH:
        search_paths.extend(os.environ["PATH"].split(os.pathsep))

        for path in search_paths:
            path = pathlib.Path(path)
            log.d("searching inside {}".format(path))

            try:
                # create a list of all exe files in the folder beeing searched:
                executables = [str(exe) for exe in path.glob("**/*.exe") if exe.is_file() and os.access(str(exe), os.X_OK)]
            except (KeyError, PermissionError):
                continue

            for exe in executables:
                if "qaac" in exe:
                    self.qaac_bin = exe
                    log.d("found qaac bin: {}".format(self.qaac_bin))
                    break

            # qaac has been found, exit needless loops:
            if self.qaac_bin:
                break
        else:
            raise QaacNotFoundError("could not locate qaac binary anywhere in PATH")

    def _test_bin(self):
        log.d("testing qaac binary")

        with QaacProcess(self.qaac_bin, args=["--check"], keep_stderr=self._debug) as qaac:
            for line in qaac:
                if qaac.returncode != 0 and "CoreAudioToolbox" in line:
                    log.d("testing qaac binary succeded")
                    self._full_stderr = qaac.full_stderr
                    return

            log.d("testing qaac binary failed")
            raise QaacTestFailedError("Qaac did not exit correctly")

    @property
    def full_stderr(self):
        try:
            return "\n".join(self._full_stderr)
        except TypeError:
            return None

    @staticmethod
    def _test_path(input_file):
        # test path for given input file:
        input_file = pathlib.Path(input_file).absolute()

        if not input_file.is_file():
            raise FileNotFoundError("{} not found or not a file.".format(input_file))

        return input_file

    def _convert(self, args):
        with QaacProcess(self.qaac_bin, args=args, keep_stderr=self._debug) as qaac:
            # create a progress bar using total duration:
            bar = ProgressBar(widgets=[Bar('#'), ' ', Percentage()], maxval=100)
            bar.start()

            for line in qaac:
                progress_re = re.search(r"^\[(\d|\d\d|\d\d\d)\.(\d)%\]", line)
                error_re = re.search(r"^ERROR:\s(.*)$", line)

                if error_re:
                    error_str = error_re.group(1)
                    bar.finish()
                    raise QaacProcessError(error_str)

                if progress_re:
                    progress = int(progress_re.group(1))
                    if int(progress_re.group(2)) >= 5:
                        progress += 1

                    if progress < 100:
                        bar.update(progress)
                    else:
                        bar.update(100)
            bar.finish()

            self._full_stderr = qaac.full_stderr

    def convert_to_aac(self, input_file, output_file, volume=0):
        input_file = self._test_path(input_file)

        print_stderr("Converting {} to {}:".format(str(input_file), str(output_file)))

        # prepare args for qaac:
        args = ["--tvbr", "127", "--quality", "2"]
        args.extend(["--native-resampler=bats,127"])
        args.extend(["--gain", str(volume)])
        args.extend([str(input_file)])
        args.extend(["-o", str(output_file)])

        self._convert(args)

    def convert_to_alac(self, input_file, output_file, volume=0):
        input_file = self._test_path(input_file)

        print_stderr("Converting {} to {}:".format(str(input_file), str(output_file)))

        # prepare args for qaac:
        args = ["--alac"]
        args.extend(["--native-resampler=bats,127"])
        args.extend(["--bits-per-sample", "24"])
        args.extend(["--gain", str(volume)])
        args.extend([str(input_file)])
        args.extend(["-o", str(output_file)])

        self._convert(args)
