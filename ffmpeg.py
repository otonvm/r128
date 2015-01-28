# -*- coding: utf-8 -*-

__all__ = ["FFmpeg", "FFmpegNotFoundError", "FFmpegTestFailedError",
           "FFmpegProcessError", "FFmpegMissingLib", "NotSetError"]

from subprocess import Popen, PIPE, TimeoutExpired
from functools import partial
from collections import deque
from threading import Thread, Event
from queue import Queue, Empty
import sys
import os
import re
import pathlib

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


class FFmpegException(Exception):
    pass


class FFmpegNotFoundError(FFmpegException):
    pass


class FFmpegProcessError(FFmpegException):
    pass


class FFmpegTestFailedError(FFmpegException):
    pass


class NotSetError(FFmpegException):
    pass


class FFmpegMissingLib(FFmpegException):
    pass


class FFmpegProcess:
    def __init__(self, path, args=[], store_stderr=False):
        if args and not isinstance(args, list):
            raise ValueError("you must provide a list for args")

        self._path = path
        self._args = args
        self._keep_stderr = store_stderr

        self._cmd = []
        self._proc = None
        self._returncode = None
        self._interrupted = False
        self._full_stderr = deque()

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
            self._proc = Popen(self._cmd, stderr=PIPE, bufsize=0)

        except FileNotFoundError as err:
            raise FFmpegNotFoundError(err) from None
        except OSError as err:
            raise FFmpegProcessError(err) from None

    def __enter__(self):
        log.d("__enter__")
        self._cmd.append(self._path)

        if self._args:
            self._cmd.extend(self._args)

        self._run()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        log.d("__exit__")
        del traceback

        if self._proc.returncode is None:
            try:
                log.d("terminating process")
                self._proc.terminate()
                self._proc.communicate(timeout=5)
            except TimeoutExpired:
                log.d("killing process")
                self._proc.kill()

        if self._interrupted:
            raise KeyboardInterrupt

        if exc_type is not None:
            raise exc_type(exc_value)

        return True

    def __iter__(self):
        return self

    def __next__(self):
        buffer = deque()
        for err_char in iter(partial(self._proc.stderr.read, 1), b''):
            try:
                # replace any not decoded char with a space:
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


class FFmpeg:
    def __init__(self, path=None, debug=False):
        self.ffmpeg_bin = path
        self._debug = debug

        self._queue = None
        self._thread = None
        self._quit_event = None

        self._bar = None

        self._requirements = []
        self._full_stderr = []

        if not self.ffmpeg_bin:
            self._locate_bin()
            self._test_bin()

        else:
            log.d("testing provided path")

            if not pathlib.Path.is_file(self.ffmpeg_bin):
                raise ValueError("Given path for FFmpeg does not exist")

            if not os.access(self.ffmpeg_bin, os.X_OK):
                raise ValueError("Given path for FFmpeg must be executable")

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
    def path(self):
        return self.ffmpeg_bin

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
            with FFmpegProcess(self.ffmpeg_bin, store_stderr=self._debug) as ff:
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
    def _check_file(file):
        # test path for given input file:
        file = pathlib.Path(file).absolute()
        if not file.is_file():
            raise FileNotFoundError("{} not found or not a file.".format(file))

        if file.stat().st_size == 0:
            raise FFmpegProcessError("{} is 0-byte file".format(file))

    def _signal_progress(self, value=0, finish=False):
        # create a progress bar or send Qt signals

        # a progress bar does not exist:
        if not self._bar:
            self._bar = ProgressBar(widgets=[Bar('#'), ' ', Percentage()], maxval=value)
            self._bar.start()

        elif finish:
            # signal to exit the bar:
            self._bar.finish()
            self._bar = None

        else:
            # a progress bar exists so update it:
            self._bar.update(value)

    @staticmethod
    def _start_ffmpeg_process(queue, quit_event, bin_path, args=[], store_stderr=False):
        # to be started as a thread!
        try:
            with FFmpegProcess(bin_path, args=args, store_stderr=store_stderr) as ff:
                for line in ff:
                    if line:
                        queue.put(line)

                    if quit_event.is_set():
                        break
                if store_stderr:
                    queue.put(("stderr", ff.full_stderr))
        # catching all exceptions from the thread:
        except Exception:
            exc = sys.exc_info()
            queue.put((exc[0], exc[1]))

    def _create_queue_event_thread(self, args):
        self._queue = Queue()
        self._quit_event = Event()

        # start thread that reads from stderr:
        self._thread = Thread(target=self._start_ffmpeg_process,
                              args=(self._queue, self._quit_event, self.ffmpeg_bin, args, self._debug,))
        self._thread.daemon = True
        self._thread.start()
        log.d("started thread: {}".format(self._thread.name))

    def _thread_dead(self):
        return (not self._thread.is_alive()) and self._queue.empty()

    def _get_stderr_exception(self, data):
        # a tuple is either an exception or full stderr
        if isinstance(data, tuple):
            # get stderr info:
            if data[0] == "stderr":
                if self._debug:
                    self._full_stderr = data[1]
            else:
                # react to exception:
                self._signal_progress(finish=True)
                log.d("raising exception {} from thread".format(data[0]))
                raise data[0](data[1])

    def _quit_thread(self, exception=None):
        self._signal_progress(finish=True)

        self._quit_event.set()

        # give thread a chance:
        if self._thread.is_alive():
            log.d("thread {} is still alive".format(self._thread.name))
            self._thread.join(timeout=5)

        # check again:
        if self._thread.is_alive():
            log.d("thread {} is still alive, will not exit cleanly!".format(self._thread.name))

        if exception:
            raise exception

    def _get_duration(self):
        log.d("getting file duration")

        duration = 0
        while True:
            if self._thread_dead():
                break

            try:
                data = self._queue.get_nowait()
            except Empty:
                continue

            else:
                self._get_stderr_exception(data)

                if duration == 0:
                    duration_re = re.search(r"^Duration:\s(\d\d):(\d\d):(\d\d)\.(\d\d)", data)

                    if duration_re:
                        hh = int(duration_re.group(1))
                        mm = int(duration_re.group(2))
                        ss = int(duration_re.group(3))
                        ms = int(duration_re.group(4))
                        if ms > 50:
                            ss += 1  # round up
                        duration = hh * 60 * 60 + mm * 60 + ss

                else:
                    log.d("got duration: {}".format(duration))
                    break

        return duration

    def analyze_volume(self, input_file):
        self._check_file(input_file)

        # prepare args to give to ffmpeg:
        args = ["-hide_banner", "-nostats",
                "-i", str(input_file),
                "-vn", "-filter:a", "ebur128",
                "-f", "null", os.devnull]

        self._create_queue_event_thread(args)

        duration = self._get_duration()

        self._signal_progress(duration)

        try:
            lufs = 0
            peak = 0

            while True:
                if self._thread_dead():
                    self._signal_progress(finish=True)
                    break

                try:
                    data = self._queue.get(timeout=0.1)
                except Empty:
                    continue

                else:
                    self._get_stderr_exception(data)

                    try:
                        time_re = re.search(r"t:\s+(.*)\s+M", data)
                        lufs_re = re.search(r"^I:\s+(.*)\sLUFS", data)
                        peak_re = re.search(r"^Peak:\s+(.*)\sdBFS", data)
                    except TypeError:
                        pass

                    if time_re:
                        time = round(float(time_re.group(1)), 1)
                        if time < duration:
                            self._signal_progress(time)
                        else:
                            self._signal_progress(duration)

                    if lufs_re:
                        lufs = round(float(lufs_re.group(1)), 1)

                    if peak_re:
                        peak = round(float(peak_re.group(1)), 1)

            self._quit_thread()

            return lufs, peak

        except KeyboardInterrupt as exc:
            self._quit_thread(exc)

    def _single_file_conversion(self, args):
        self._create_queue_event_thread(args)

        duration = self._get_duration()

        self._signal_progress(duration)

        try:
            while True:
                if self._thread_dead():
                    self._signal_progress(finish=True)
                    break

                try:
                    data = self._queue.get(timeout=0.1)
                except Empty:
                    continue

                else:
                    self._get_stderr_exception(data)

                    try:
                        time_re = re.search(r"^.*time=(\d\d):(\d\d):(\d\d).(\d\d)", data)
                    except TypeError:
                        pass

                    if time_re:
                        hh = int(time_re.group(1))
                        mm = int(time_re.group(2))
                        ss = int(time_re.group(3))
                        ms = int(time_re.group(4))

                        if ms > 50:
                            ss += 1  # round up

                        time = hh * 60 * 60 + mm * 60 + ss

                        if time < duration:
                            self._signal_progress(time)
                        else:
                            self._signal_progress(duration)

                    if "Error" in data:
                        self._quit_thread(FFmpegProcessError(data))

            self._quit_thread()

        except KeyboardInterrupt as exc:
            self._quit_thread(exc)

    def convert_to_mp3(self, input_file, output_file, volume=0):
        self._check_file(input_file)

        # prepare args to give to ffmpeg:
        args = ["-hide_banner", "-i", str(input_file),
                "-vn", "-c:a", "libmp3lame", "-qscale:a", "0",
                "-compression_level", "0",
                "-filter:a", "volume={}dB".format(volume),
                "-f", "mp3", "-y", str(output_file)]

        self._single_file_conversion(args)

        self._check_file(output_file)

    def convert_to_ac3(self, input_file, output_file, volume=0):
        self._check_file(input_file)

        # prepare args to give to ffmpeg:
        args = ["-hide_banner",
                "-i", str(input_file),
                "-vn", "-c:a", "ac3", "-b:a", "640k",
                "-filter:a",
                "aresample=48000:out_sample_fmt=fltp:resampler=soxr:precision=28,volume={}dB".format(volume),
                "-f", "ac3", "-y", str(output_file)]

        self._single_file_conversion(args)

        self._check_file(output_file)

    def convert_to_flac(self, input_file, output_file, volume=0):
        self._check_file(input_file)

        # prepare args to give to ffmpeg:
        args = ["-hide_banner",
                "-i", str(input_file),
                "-vn", "-c:a", "flac",
                "-filter:a",
                "volume={}dB".format(volume),
                "-f", "flac", "-y", str(output_file)]

        self._single_file_conversion(args)

        self._check_file(output_file)

if __name__ == "__main__":
    stanovanje = True

    ffmpeg = r"C:\Users\Oton\Dropbox\Python\r128\tools\ffmpeg\ffmpeg.exe"
    lame = r"C:\Users\Oton\Dropbox\Python\r128\tools\lame\lame.exe"
    flac = r"C:\Users\Oton\Downloads\BACKUP\Sido - Maske (2004) (Flac)\04 - Mein Block.flac"
    if stanovanje:
        ffmpeg = r"D:\Dropbox\Python\r128\tools\ffmpeg\ffmpeg.exe"
        lame = r"D:\Dropbox\Python\r128\tools\lame\lame.exe"
        flac = r"D:\Downloads\FLAC\2009 - In Search Of Sunrise 6 - Ibiza (Unmixed Tracks) [SBCD 10] WEB\03. Andy Duguid feat. Leah - Don't Belong.flac"

    ff = FFmpeg(debug=True)
    try:
        ff.convert_to_ac3(flac, "test.mp3")
        print(ff.full_stderr)
    except (KeyboardInterrupt, FFmpegProcessError) as err:
        print(err)
    print(ff.full_stderr)
