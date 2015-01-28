#! python3
# -*- coding: utf-8 -*-

"""
Transcoder and EBU R128 Normalizer

This app transcodes single FLAC files or recusively a folder containing FLAC files while
also normlizing all files according to EBU R128 standard.

By default it normalizes to -16dB however other options are available (including -23dB).

FLAC files can be transcoded to AAC or ALAC through Qaac or MP3 through LAME.
A single FLAC file can also be transcoded to AC3 through just FFmpeg.

In a folder next to the script or somewhere in your PATH should be:
 - ffmpeg.exe
 - qaac.exe (requires iTunes or Apple Support Tools or a portable installation)
 - lame.exe
"""

__author__ = "Oton Mahnič"
__copyright__ = "2015 Oton Mahnič"
__version__ = "1.5"

# library imports:
import os
import sys
import argparse
import pathlib

# local imports:
import logger
import config
import readchar
from utils import *
from ffmpeg import *
from lame import *
from qaac import *
from database import *


def parse_args():
    parser = argparse.ArgumentParser(description="EBU R128 Loudness Normalizer v{}".format(__version__),
                                     formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("-v", action="store_true", dest="verbose",
                        help="verbose")
    parser.add_argument("-d", action="store_true", dest="debug",
                        help="debug")

    parser.add_argument("-n", action="store_true", dest="dry_run",
                        help="simulate all actions")

    itunes = parser.add_mutually_exclusive_group()
    itunes.add_argument("--itunes", action="store_true",
                        help="encode both AAC and ALAC formats [default]")
    itunes.add_argument("--aac", action="store_true",
                        help="encode only AAC format")
    itunes.add_argument("--alac", action="store_true",
                        help="encode only ALAC format")

    parser.add_argument("--mp3", action="store_true",
                        help="{}\n{}".format("encode MP3 format",
                                             " - disables AAC or ALAC formats that can be enabled manually"))

    parser.add_argument("--ac3", action="store_true",
                        help="{}\n{}\n{}".format("encode ac3 format",
                                                 " - disables other encoding",
                                                 " - is only available when converting a single file"))

    parser.add_argument("--quality", default=9, type=int, metavar="q",
                        help="{}\n{}\n{}".format("set quality of MP3 or AAC encoding",
                                                 " - from 0 to 9 where 0 = lowest, 9 = highest [default])",
                                                 "(not implemented)"))

    parser.add_argument("--volume", default=-16, type=int, metavar="vol", choices=[-23, -19, -16],
                        help="{}\n{}\n{}".format("set value to which to normalize",
                                                 " - -23 is by standard",
                                                 " - -19 or -16 [default] are slightly louder"))

    parser.add_argument("--no-db", action="store_true",
                        help="don't create a volumes.db file")

    parser.add_argument("input", metavar="<input file or folder>")

    try:
        return parser.parse_args()
    except SystemExit:
        if ('-h' or '--help') not in sys.argv:
            print("Press any key to quit...", end='', file=sys.stderr, flush=True)
            readchar.readkey()
        raise


def init_config(args):
    conf.input = pathlib.Path(args.input).absolute()

    # check if the input exists:
    if not pathlib.Path.exists(conf.input):
        print_and_exit("{} does not exist!".format(conf.input), 1)

    # create string rapresentation:
    conf.input_str = str(conf.input)

    conf.input_is_file = conf.input.is_file()

    # parse other options:
    conf.itunes = args.itunes
    conf.aac = args.aac
    conf.alac = args.alac
    conf.mp3 = args.mp3
    conf.ac3 = args.ac3
    conf.quality = args.quality
    conf.volume = args.volume

    # set some defaults:
    if conf.itunes:
        conf.aac = True
        conf.alac = True

    if not conf.aac and not conf.alac and not conf.mp3:
        conf.itunes = True
        conf.aac = True
        conf.alac = True
        log.d("defaulting to itunes output")

    if conf.ac3:
        conf.itunes = conf.aac = conf.alac = conf.mp3 = False
        log.d("encoding to ac3")

    conf.dry_run = args.dry_run
    conf.no_db = args.no_db

    conf.verbose = args.verbose
    conf.debug = args.debug

    log.d("parsed commandline arguments: {}".format(conf))


def init_ffmpeg():
    # test ffmpeg:
    try:
        conf.ffmpeg = FFmpeg(debug=conf.debug)

        # check if this ffmpeg has the required libraries compiled in:
        conf.ffmpeg.requrements = "libmp3lame"
        conf.ffmpeg.requrements = "libsoxr"

        conf.ffmpeg.check_requirements()

    except FFmpegNotFoundError:
        log_and_exit("FFmpeg binary could not be found.\nMake sure it's in your path.", 1)

    except (FFmpegTestFailedError, FFmpegProcessError):
        log_and_exit("Error while trying to run FFmpeg.", 1)

    except FFmpegMissingLib as err:
        log_and_exit("FFmpeg at {} doesn't have the required library: {}".format(conf.ffmpeg.path, err), 1)


def init_lame():
    # qaac is not required so it can fail detection:
    try:
        conf.lame = LAME(debug=conf.debug)

    except LAMENotFoundError:
        log.w("LAME binary could not be found.\nMake sure it's in your path.")

    except (LAMETestFailedError, LAMEProcessError):
        log.w("Error while trying to run LAME.")


def init_qaac():
    # qaac is not required so it can fail detection:
    try:
        conf.qaac = Qaac(debug=conf.debug)

    except QaacNotFoundError:
        log.w("Qaac binary could not be found. Make sure it's in your path.")

    except (QaacTestFailedError, QaacProcessError):
        log.w("Error while trying to run Qaac.")


def calc_volume(lufs):
    log.d("lufs: {}, calculating to: {}".format(lufs, conf.volume))
    return round(conf.volume - lufs, 1)


def init_db(conversion_list):
    # try to create/open the volumes database:
    if not conf.db:
        conf.db = Database(conf.database_path, in_memory=(conf.dry_run or conf.no_db))

    for input_file, _ in conversion_list:
        input_file_md5 = conf.db.md5sum(input_file)

        if not conf.db.get_entry(input_file_md5):
            log.d("analyzing volume for file: {}".format(input_file.name))
            lufs, _ = conf.ffmpeg.analyze_volume(input_file)

            conf.db.set_entry(input_file_md5, calc_volume(lufs))
    log.d("database: {}".format(conf.db))


def main(args):
    init_config(args)

    init_ffmpeg()

    if conf.itunes or conf.aac or conf.alac:
        init_qaac()

    if conf.mp3:
        init_lame()

    # disable aac and alac encoding if qaac is not present:
    if not conf.qaac:
        conf.aac = False
        conf.alac = False

    # disable mp3 encoding if lame is not present:
    if not conf.lame:
        conf.mp3 = False

    if not conf.aac and not conf.alac and not conf.mp3 and not conf.ac3:
        log_and_exit("No available encoder has been selected.")

    # create a list of all input flac files:
    if conf.input_is_file:
        if not conf.input.name.endswith(".flac"):
            log_and_exit("File {} is not a FLAC file!".format(conf.input.name), 1)

        log.i("Processing one file...")

        conf.input_list.append(conf.input)

    else:
        if conf.ac3:
            log_and_exit("Only files are supported for ac3 encoding!", 1)

        conf.input_list = [file for file in conf.input.glob("*.flac")]

        if len(conf.input_list) == 0:
            log_and_exit("No FLAC files found in {}!".format(conf.input.name), 1)

        log.i("Processing {} files...".format(len(conf.input_list)))

    # loop over all input files and create (input, output) combinations
    # while filtering out existing files:
    for file in conf.input_list:
        if conf.input_is_file:
            # create a list that contains only one file
            # this is to prevent the creation of a new folder
            aac_output_filename = file.parent / "{}_aac.m4a".format(file.stem)
            if not aac_output_filename.exists():
                conf.aac_conversion_list.append((file, aac_output_filename))
            else:
                log.i("{} alredy exists. Skipping...".format(aac_output_filename))

            alac_output_filename = file.parent / "{}_alac.m4a".format(file.stem)
            if not alac_output_filename.exists():
                conf.alac_conversion_list.append((file, alac_output_filename))
            else:
                log.i("{} alredy exists. Skipping...".format(alac_output_filename))

            mp3_output_filename = file.parent / "{}.mp3".format(file.stem)
            if not mp3_output_filename.exists():
                conf.mp3_conversion_list.append((file, mp3_output_filename))
            else:
                log.i("{} alredy exists. Skipping...".format(mp3_output_filename))

            ac3_output_filename = file.parent / "{}.ac3".format(file.stem)
            if not ac3_output_filename.exists():
                conf.ac3_conversion_list.append((file, ac3_output_filename))
            else:
                log.i("{} alredy exists. Skipping...".format(ac3_output_filename))

        else:
            aac_output_filename = conf.input / "aac" / "{}.m4a".format(file.stem)
            if not aac_output_filename.exists():
                conf.aac_conversion_list.append((file, aac_output_filename))
            else:
                log.i("{} alredy exists. Skipping...".format(aac_output_filename))

            alac_output_filename = conf.input / "alac" / "{}.m4a".format(file.stem)
            if not alac_output_filename.exists():
                conf.alac_conversion_list.append((file, alac_output_filename))
            else:
                log.i("{} alredy exists. Skipping...".format(alac_output_filename))

            mp3_output_filename = conf.input / "mp3" / "{}.mp3".format(file.stem)
            if not mp3_output_filename.exists():
                conf.mp3_conversion_list.append((file, mp3_output_filename))
            else:
                log.i("{} alredy exists. Skipping...".format(mp3_output_filename))

    # setup database path:
    if conf.input_is_file:
        conf.database_path = conf.input.parent / "volumes.db"
    else:
        conf.database_path = conf.input / "volumes.db"
    log.d("database path: {}".format(conf.database_path))

    if conf.aac:
        print_stderr("Converting to aac...")
        if len(conf.aac_conversion_list) > 0:
            init_db(conf.aac_conversion_list)

            # create the output folder if needed:
            if not conf.input_is_file:
                if not pathlib.Path(conf.input / "aac").is_dir():
                    if not conf.dry_run:
                        pathlib.Path.mkdir(conf.input / "aac")

            for input_file, output_file in conf.aac_conversion_list:
                if not conf.dry_run:
                    volume = conf.db.get_entry(conf.db.md5sum(input_file))

                    try:
                        conf.qaac.convert_to_aac(input_file, output_file, volume=volume)
                    except QaacProcessError as err:
                        try:
                            os.remove(str(output_file))
                        except PermissionError:
                            pass

                        log_and_exit("Qaac error: {}".format(err), 1)
                    except KeyboardInterrupt:
                        try:
                            os.remove(str(output_file))
                        except PermissionError:
                            pass
                        raise

                    log.d("full qaac stderr: {}".format(conf.qaac.qaac_stderr))
                else:
                    log.i("Would convert {} to {}.".format(input_file, output_file))
        else:
            print_stderr("Nothing to do!")

    if conf.alac:
        print_stderr("Converting to alac...")
        if len(conf.alac_conversion_list) > 0:
            init_db(conf.alac_conversion_list)

            if not conf.input_is_file:
                if not pathlib.Path(conf.input / "alac").is_dir():
                    if not conf.dry_run:
                        pathlib.Path.mkdir(conf.input / "alac")

            for input_file, output_file in conf.alac_conversion_list:
                if not conf.dry_run:
                    volume = conf.db.get_entry(conf.db.md5sum(input_file))
                    try:
                        conf.qaac.convert_to_alac(input_file, output_file, volume=volume)
                    except QaacProcessError as err:
                        try:
                            os.remove(str(output_file))
                        except PermissionError:
                            pass

                        log_and_exit("Qaac error: {}".format(err), 1)
                    except KeyboardInterrupt:
                        try:
                            os.remove(str(output_file))
                        except PermissionError:
                            pass
                        raise

                    log.d("full qaac stderr: {}".format(conf.qaac.qaac_stderr))
                else:
                    log.i("Would convert {} to {}.".format(input_file, output_file))
        else:
            print_stderr("Nothing to do!")

    if conf.mp3:
        print_stderr("Converting to mp3...")
        if len(conf.mp3_conversion_list) > 0:
            init_db(conf.mp3_conversion_list)

            if not conf.input_is_file:
                if not pathlib.Path(conf.input / "mp3").is_dir():
                    if not conf.dry_run:
                        pathlib.Path.mkdir(conf.input / "mp3")

            for input_file, output_file in conf.mp3_conversion_list:
                if not conf.dry_run:
                    volume = conf.db.get_entry(conf.db.md5sum(input_file))
                    try:
                        conf.lame.convert_to_mp3(input_file, output_file, volume=volume)
                    except KeyboardInterrupt:
                        try:
                            os.remove(str(output_file))
                        except PermissionError:
                            pass
                        raise

                    log.d("full lame stderr: {}".format(conf.lame.lame_stderr))
                else:
                    log.i("Would convert {} to {}.".format(input_file, output_file))
        else:
            print_stderr("Nothing to do!")

    if conf.ac3:
        print_stderr("Converting to ac3...")
        if len(conf.ac3_conversion_list) > 0:
            init_db(conf.ac3_conversion_list)

            # for future:
            if not conf.input_is_file:
                if not pathlib.Path(conf.input / "ac3").is_dir():
                    if not conf.dry_run:
                        pathlib.Path.mkdir(conf.input / "ac3")

            for input_file, output_file in conf.ac3_conversion_list:
                if not conf.dry_run:
                    volume = conf.db.get_entry(conf.db.md5sum(input_file))
                    try:
                        conf.ffmpeg.convert_to_ac3(input_file, output_file, volume=volume)
                    except KeyboardInterrupt:
                        try:
                            os.remove(str(output_file))
                        except PermissionError:
                            pass
                        raise

                    log.d("full stderr: {}".format(conf.ffmpeg.full_stderr))
                else:
                    log.i("Would convert {} to {}.".format(input_file, output_file))
        else:
            print_stderr("Nothing to do!")


if __name__ == "__main__":
    print(getattr(sys, "frozen"))
    print(pathlib.Path(sys.executable).parent)
    arguments = parse_args()

    # initialize the config class
    # to store and share configuration
    # has to be in global scope:
    conf = config.Config()

    log = logger.Logger(__name__)
    if arguments.debug:
        conf.log_level = "DEBUG"
    elif arguments.verbose:
        conf.log_level = "INFO"
    else:
        conf.log_level = "ERROR"
    log.level = conf.log_level

    log.d("all arguments: {}".format(arguments))

    try:
        main(arguments)
    except KeyboardInterrupt:
        print_and_exit("Interrupted!", 1)
