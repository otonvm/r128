# -*- coding: utf-8 -*-

__all__ = ["Qaac", "QaacNotFoundError", "QaacProcessError", "QaacTestFailedError"]

from subprocess import Popen, PIPE, TimeoutExpired
from functools import partial
from collections import deque
from threading import Thread, Event
from queue import Queue, Empty
import sys
import os
import re
import pathlib
import traceback

import config
import logger
from ffmpeg import *


conf = config.Config()

log = logger.Logger(__name__)
if conf.log_level:
    log.level = conf.log_level
else:
    log.level = "DEBUG"

from utils import locate_bin, HashProgressBar


class QaacException(Exception):
    pass


class QaacNotFoundError(QaacException):
    pass


class QaacProcessError(QaacException):
    pass


class QaacTestFailedError(QaacException):
    pass


class QaacProcess:
    def __init__(self, ff_path, qaac_path, ff_args=[], qaac_args=[], test=False, store_stderr=False):
        if ff_args and not isinstance(ff_args, list):
            raise ValueError("you must provide a list for args")

        if qaac_args and not isinstance(qaac_args, list):
            raise ValueError("you must provide a list for args")

        self._ff_path = ff_path
        self._qaac_path = qaac_path
        self._ff_args = ff_args
        self._qaac_args = qaac_args
        self._test = test
        self._keep_stderr = store_stderr

        self._ff_cmd = []
        self._qaac_cmd = []
        self._ff_proc = None
        self._qaac_proc = None
        self._ff_returncode = None
        self._qaac_returncode = None
        self._interrupted = False
        self._ff_stderr = deque()
        self._qaac_stderr = None

    @property
    def ff_args(self):
        return self._ff_args

    @ff_args.setter
    def ff_args(self, value):
        if not isinstance(value, list):
            raise ValueError("you must provide a list for args")

    @property
    def qaac_args(self):
        return self._qaac_args

    @qaac_args.setter
    def qaac_args(self, value):
        if not isinstance(value, list):
            raise ValueError("you must provide a list for args")

        self._qaac_args = value

    def _run(self):
        try:
            if self._test:
                log.d("starting qaac test subprocess")
                self._qaac_proc = Popen([self._qaac_path, "--check"], stderr=PIPE, bufsize=0)
            else:
                log.d("starting ffmpeg subprocess: {}".format(self._ff_cmd))
                log.d("starting qaac subprocess: {}".format(self._qaac_cmd))
                self._ff_proc = Popen(self._ff_cmd, stderr=PIPE, stdout=PIPE, bufsize=0)
                self._qaac_proc = Popen(self._qaac_cmd, stdin=self._ff_proc.stdout, stderr=PIPE, bufsize=0)

        except FileNotFoundError as err:
            raise QaacNotFoundError(err) from None
        except OSError as err:
            raise QaacProcessError(err) from None

    def test(self):
        # runs qaac without arguments
        # returns a tuple (returncode, stderr)
        self._test = True
        self._run()
        return self._qaac_proc.communicate()[1].decode("utf-8"), self._qaac_proc.returncode

    def __enter__(self):
        log.d("__enter__")
        self._ff_cmd.append(self._ff_path)
        self._ff_cmd.extend(self._ff_args)

        self._qaac_cmd.append(self._qaac_path)
        self._qaac_cmd.extend(self._qaac_args)

        self._run()
        return self

    def __exit__(self, exc_type, exc_value, exc_trace):
        log.d("__exit__")

        if self._ff_proc.returncode is None:
            try:
                log.d("terminating ffmpeg process")
                self._ff_proc.terminate()
                self._ff_proc.communicate(timeout=5)
            except TimeoutExpired:
                log.d("killing ffmpeg process")
                self._ff_proc.kill()

        if self._qaac_proc.returncode is None:
            try:
                log.d("terminating qaac process")
                self._qaac_proc.terminate()
                self._qaac_proc.communicate(timeout=5)
            except TimeoutExpired:
                log.d("killing qaac process")
                self._qaac_proc.kill()

        if self._interrupted:
            raise KeyboardInterrupt

        if exc_type is not None:
            stack = traceback.extract_tb(exc_trace)
            raise exc_type((exc_value, stack))

        return True

    def __iter__(self):
        return self

    def _stop_iteration(self):
        self._ff_returncode = self._ff_proc.poll()
        self._qaac_returncode = self._qaac_proc.poll()

        # give qaac a chance to terminate cleanly:
        if self._keep_stderr:
            # and get stderr:
            self._qaac_stderr = self._qaac_proc.communicate(timeout=5)[1]
        self._qaac_proc.communicate(timeout=5)
        raise StopIteration

    def __next__(self):
        buffer = deque()
        for err_char in iter(partial(self._ff_proc.stderr.read, 1), b''):
            try:
                if self._qaac_proc.poll() is not None:
                    # caught when exiting generator:
                    raise QaacProcessError("unexpected termination")
                    # noinspection PyUnreachableCode
                    raise StopIteration

                # replace any not decoded char with a space:
                try:
                    buffer.append(err_char.decode("utf-8"))
                except UnicodeDecodeError:
                    buffer.append(' ')

                if '\r' in buffer:
                    line = "".join(buffer).strip()
                    buffer.clear()

                    if self._keep_stderr:
                        self._ff_stderr.append(line)

                    return line

            except KeyboardInterrupt:
                self._interrupted = True
                self._stop_iteration()
        else:
            self._stop_iteration()

    @property
    def ffmpeg_returncode(self):
        return self._ff_returncode

    @property
    def qaac_returncode(self):
        return self._qaac_returncode

    @property
    def ff_stderr(self):
        return self._ff_stderr

    @property
    def qaac_stderr(self):
        return self._qaac_stderr.decode("utf-8")


class Qaac:
    def __init__(self, ff_path=None, qaac_path=None, debug=False):
        self._ff_path = ff_path
        self._qaac_path = qaac_path
        self._debug = debug

        self._ff_args = []
        self._qaac_args = []
        self._duration = 0
        self._ff_stderr = []
        self._qaac_stderr = None
        self._qaac_supported_ver = "2.45"
        self._cat_supported_ver = "7.9.9.4"

        self._progressbar = HashProgressBar()

        try:
            if self._ff_path:
                self._ff_path = FFmpeg(self._ff_path).path
            else:
                self._ff_path = FFmpeg().path
        except FFmpegTestFailedError as exc:
            raise QaacTestFailedError(exc)

        if not self._qaac_path:
            self._qaac_path = locate_bin("qaac", QaacNotFoundError)
            self._test_bin()

        else:
            log.d("testing provided path")

            if not pathlib.Path.is_file(self._qaac_path):
                raise ValueError("Given path for Qaac does not exist")

            if not os.access(self._qaac_path, os.X_OK):
                raise ValueError("Given path for Qaac must be executable")

            self._test_bin()

    def _test_bin(self):
        log.d("testing qaac binary")

        qaac = QaacProcess(ff_path=None, qaac_path=self._qaac_path, test=True, store_stderr=True)
        qaac = qaac.test()

        if qaac[1] == 0:
            ver_re = re.search(r"qaac\s(.*),\sCoreAudioToolbox\s(.*)", qaac[0])

            if ver_re:
                ver_qaac = ver_re.group(1)
                ver_cat = ver_re.group(2)
                log.d("got qaac ver. {} and coreaudio ver. {}".format(ver_qaac, ver_cat))

            if ver_qaac != self._qaac_supported_ver or ver_cat != self._cat_supported_ver:
                log.w("Only Qaac version {} and "
                      "CoreAudioToolbox version {} "
                      "are supported.".format(self._qaac_supported_ver, self._cat_supported_ver))
                log.w("If there are errors try those versions.")
            else:
                log.d("testing qaac binary succeded")

        else:
            log.d("testing qaac binary failed")
            raise QaacTestFailedError("did not run or test correctly")

    @property
    def ffmpeg_stderr(self):
        try:
            return "\n".join(self._ff_stderr)
        except TypeError:
            return None

    @property
    def qaac_stderr(self):
        try:
            return self._qaac_stderr
        except TypeError:
            return None

    @staticmethod
    def _check_file(file):
        # test path for given input file:
        file = pathlib.Path(file).absolute()
        if not file.is_file():
            raise FileNotFoundError("{} not found or not a file.".format(file))

        if file.stat().st_size == 0:
            raise QaacProcessError("{} is 0-byte file".format(file))

    @staticmethod
    def _start_qaac_process(queue, quit_event, ff_path, qaac_path, ff_args=[], qaac_args=[], store_stderr=False):
        # to be started as a thread!
        # noinspection PyBroadException
        try:
            with QaacProcess(ff_path, qaac_path, ff_args, qaac_args, store_stderr=store_stderr) as qaac:
                for line in qaac:
                    if line:
                        queue.put(line)

                    if quit_event.is_set():
                        break
                if store_stderr:
                    queue.put(("stderr", qaac.ff_stderr, qaac.qaac_stderr))
        # catching all exceptions from the thread:
        except Exception:
            exc = sys.exc_info()
            queue.put((exc[0], exc[1]))

    def _create_queue_event_thread(self):
        self._queue = Queue()
        self._quit_event = Event()

        # start thread that reads from stderr:
        self._thread = Thread(target=self._start_qaac_process, args=(self._queue, self._quit_event,
                                                                     self._ff_path, self._qaac_path,
                                                                     self._ff_args, self._qaac_args,
                                                                     self._debug))
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
                    self._ff_stderr = data[1]
                    self._qaac_stderr = data[2]
            else:
                # react to exception:
                self._progressbar.finish()
                log.d("raising exception {} from thread".format(data[0]))
                raise data[0](data[1])

    def _quit_thread(self, exception=None):
        self._progressbar.finish()

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
                data = self._queue.get(timeout=0.1)
            except Empty:
                continue

            else:
                self._get_stderr_exception(data)

                if duration == 0:
                    duration_re = None
                    try:
                        duration_re = re.search(r"^Duration:\s(\d\d):(\d\d):(\d\d)\.(\d\d)", data)
                    except TypeError:
                        pass

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
                    self._duration = duration
                    break

    def _single_file_conversion(self):
        self._create_queue_event_thread()

        self._get_duration()

        self._progressbar.create(self._duration)

        try:
            while True:
                if self._thread_dead():
                    self._progressbar.finish()
                    break

                try:
                    data = self._queue.get(timeout=0.1)
                except Empty:
                    continue

                else:
                    self._get_stderr_exception(data)

                    time_re = None
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

                        if time < self._duration:
                            self._progressbar.update(time)
                        else:
                            self._progressbar.update(self._duration)

                    if "Error" in data:
                        self._quit_thread(QaacProcessError(data))

            self._quit_thread()

        except KeyboardInterrupt as exc:
            self._quit_thread(exc)

    def convert_to_aac(self, input_file, output_file, volume=0):
        self._check_file(input_file)

        self._ff_args = ["-hide_banner",
                         "-i", str(input_file),
                         "-vn", "-filter:a",
                         "volume={}dB".format(volume),
                         "-f", "wav", "-y", "-"]

        self._qaac_args = ["--tvbr", "127", "--quality", "2",
                           "--native-resampler=bats,127",
                           "-", "-o", str(output_file)]

        log.i("Converting {} to {}...".format(input_file.name, output_file.name))
        self._single_file_conversion()

        self._check_file(output_file)

    def convert_to_alac(self, input_file, output_file, volume=0):
        self._check_file(input_file)

        self._ff_args = ["-hide_banner",
                         "-i", str(input_file),
                         "-vn", "-filter:a",
                         "volume={}dB".format(volume),
                         "-f", "wav", "-y", "-"]

        self._qaac_args = ["--alac",
                           "--native-resampler=bats,127",
                           "--bits-per-sample", "24",
                           "-", "-o", str(output_file)]

        log.i("Converting {} to {}...".format(input_file.name, output_file.name))
        self._single_file_conversion()

        self._check_file(output_file)
