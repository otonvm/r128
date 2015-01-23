# -*- coding: utf-8 -*-

__all__ = ["FFmpeg", "FFmpegNotFoundError", "FFmpegTestFailedError", "FFmpegProcessError", "FFmpegMissingLib"]

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


class FFmpegNotFoundError(Exception):
    pass


class FFmpegProcessError(Exception):
    pass


class FFmpegTestFailedError(Exception):
    pass


class NotSetError(Exception):
    pass


class FFmpegMissingLib(Exception):
    pass


class FFmpegProcess:
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
            raise FFmpegNotFoundError(err.strerror) from None
        except OSError as err:
            raise FFmpegProcessError(err.strerror) from None

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
                try:
                    buffer.append(err_char.decode("utf-8"))
                except UnicodeDecodeError:
                    buffer.append(' ')

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


class FFmpeg:
    def __init__(self, path=None, debug=False):
        self.ffmpeg_bin = path
        self._debug = debug

        self._requirements = []
        self._full_stderr = []

        if not self.ffmpeg_bin:
            self._locate_bin()
            self._test_bin()

        else:
            log.d("testing path")

            if not isinstance(self.ffmpeg_bin, str):
                raise ValueError("Path must be a string.")

            if not self.ffmpeg_bin.endswith(".exe") or not os.access(self.ffmpeg_bin, os.X_OK):
                raise ValueError("Path must be of an executable.")

            self._test_bin()

    def _locate_bin(self):
        log.d("trying to find ffmpeg binary")

        # script folder should be among the first to be searched:
        search_paths = sys.path

        # the add the system PATH:
        search_paths.extend(os.environ["PATH"].split(os.pathsep))

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
                if "ffmpeg" in exe:
                    self.ffmpeg_bin = exe
                    log.d("found ffmpeg bin: {}".format(self.ffmpeg_bin))
                    break

            # ffmpeg has been found, exit needless loops:
            if self.ffmpeg_bin:
                break
        else:
            raise FFmpegNotFoundError("Could not locate ffmpeg binary anywhere in PATH.")

    def _test_bin(self):
        log.d("testing ffmpeg binary")

        with FFmpegProcess(self.ffmpeg_bin) as ff:
            for line in ff:
                if ff.returncode != 0 and line == "Use -h to get full help or, even better, run 'man ffmpeg'":
                    log.d("testing ffmpeg binary succeded")
                    return
            log.d("testing ffmpeg binary failed")
            raise FFmpegTestFailedError("FFmpeg did not exit correctly.")

    @property
    def requrements(self):
        return self._requirements

    @requrements.setter
    def requrements(self, value):
        if isinstance(value, list):
            self._requirements.extend(value)
        elif isinstance(value, str):
            self._requirements.append(value)
        else:
            raise ValueError("value must be a str or a list")

    def check_requirements(self):
        log.d("checking ffmpeg for required libs: {}".format(self.requrements))

        if self.requrements:
            with FFmpegProcess(self.ffmpeg_bin, keep_stderr=self._debug) as ff:
                for line in ff:
                    if line.startswith("configuration:"):
                        log.d("ffmpeg {}".format(line))

                        missing = [lib for lib in self.requrements if lib not in line]

                        if len(missing) > 0:
                            raise FFmpegMissingLib("{}".format(", ".join(missing)))
                self._full_stderr = ff.full_stderr
        else:
            raise NotSetError("requirements property must be set")

    @property
    def full_stderr(self):
        try:
            return "\n".join(self._full_stderr)
        except TypeError:
            return None

    @staticmethod
    def _get_duration(line):
        duration_re = re.search(r"^Duration:\s(\d\d):(\d\d):(\d\d)\.(\d\d)", line)
        if duration_re:
            hh = int(duration_re.group(1))
            mm = int(duration_re.group(2))
            ss = int(duration_re.group(3))
            ms = int(duration_re.group(4))
            if ms > 50:
                ss += 1  # round up
            return hh * 60 * 60 + mm * 60 + ss
        return None

    def analyze_volume(self, input_file):
        # test path for given input file:
        input_file = pathlib.Path(input_file).absolute()
        if not input_file.is_file():
            raise FileNotFoundError("{} not found or not a file.".format(input_file))

        # prepare args to give to ffmpeg:
        args = ["-hide_banner", "-nostats"]
        args.extend(["-i", str(input_file)])
        args.extend(["-vn", "-filter_complex", "ebur128=peak=true"])
        args.extend(["-f", "null", os.devnull])

        lufs = None
        peak = None

        # start ffmpeg:
        with FFmpegProcess(self.ffmpeg_bin, args=args, keep_stderr=self._debug) as ff:
            # get total duration in sec:
            duration = 0
            for line in ff:
                duration = self._get_duration(line)
                if duration:
                    break

            # create a progress bar using total duration:
            print_stderr("Calculating current LUFS for file {}:".format(str(input_file)))

            bar = ProgressBar(widgets=[Bar('#'), ' ', Percentage()], maxval=duration)
            bar.start()

            for line in ff:
                time_re = re.search(r"t:\s+(.*)\s+M", line)
                lufs_re = re.search(r"^I:\s+(.*)\sLUFS", line)
                peak_re = re.search(r"^Peak:\s+(.*)\sdBFS", line)

                if time_re:
                    time = round(float(time_re.group(1)), 1)
                    if time < duration:
                        bar.update(time)
                    else:
                        bar.update(duration)

                if lufs_re:
                    lufs = round(float(lufs_re.group(1)), 1)

                if peak_re:
                    peak = round(float(peak_re.group(1)), 1)
            bar.finish()

            self._full_stderr = ff.full_stderr

        return lufs, peak

    def convert_to_mp3(self, input_file, output_file, volume=0):
        # test path for given input file:
        input_file = pathlib.Path(input_file).absolute()
        if not input_file.is_file():
            raise FileNotFoundError("{} not found or not a file.".format(input_file))

        # prepare args to give to ffmpeg:
        args = ["-hide_banner"]
        args.extend(["-i", str(input_file)])
        args.extend(["-vn", "-qscale:a", "0"])
        args.extend(["-af", "volume={}dB".format(volume)])
        args.extend(["-y", str(output_file)])

        # start ffmpeg:
        with FFmpegProcess(self.ffmpeg_bin, args=args, keep_stderr=self._debug) as ff:
            # get total duration in sec:
            duration = 0
            for line in ff:
                duration = self._get_duration(line)
                if duration:
                    break

            # create a progress bar using total duration:
            print_stderr("Converting {} to {}:".format(str(input_file), str(output_file)))

            bar = ProgressBar(widgets=[Bar('#'), ' ', Percentage()], maxval=duration)
            bar.start()

            for line in ff:
                time_re = re.search(r"^.*time=(\d\d):(\d\d):(\d\d).(\d\d)", line)

                if time_re:
                    hh = int(time_re.group(1))
                    mm = int(time_re.group(2))
                    ss = int(time_re.group(3))
                    ms = int(time_re.group(4))

                    if ms > 50:
                        ss += 1  # round up

                    time = hh * 60 * 60 + mm * 60 + ss

                    if time < duration:
                        bar.update(time)
                    else:
                        bar.update(duration)
            bar.finish()

            self._full_stderr = ff.full_stderr
