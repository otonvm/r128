#!python3
# -*- coding: utf-8 -*-

# library imports:
import argparse
import pathlib

# local imports:
import logger
from config import *
from utils import *
from ffmpeg import *
from qaac import *
from database import *


def parse_args():
    parser = argparse.ArgumentParser(description="EBU R128 Loudness Normalizer")

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
                        help="encode MP3 format (disables AAC or ALAC formats)")

    parser.add_argument("--quality", default=9, type=int, metavar="q",
                        help="set quality of MP3 or AAC encoding (from 0 to 9 where 0 = low, 9 = max [default])")

    parser.add_argument("--no-db", action="store_true",
                        help="don't create a volumes.db file")

    parser.add_argument("input", metavar="<input file or folder>")

    return parser.parse_args()


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
    conf.quality = args.quality

    # set some defaults:
    if conf.itunes:
        conf.aac = True
        conf.alac = True

    if not conf.aac and not conf.alac and not conf.mp3:
        conf.itunes = True
        conf.aac = True
        conf.alac = True
        log.d("defaulting to itunes output")

    conf.dry_run = args.dry_run
    conf.no_db = args.no_db

    conf.verbose = args.verbose
    conf.debug = args.debug

    log.d("parsed commandline arguments: {}".format(conf))


def init_ffmpeg():
    # test ffmpeg:
    try:
        ffmpeg = FFmpeg(debug=conf.debug)

        # check if this ffmpeg has the required libraries compiled in:
        ffmpeg.requrements = "libmp3lame"
        ffmpeg.requrements = "libsoxr"

        ffmpeg.check_requirements()

    except FFmpegNotFoundError:
        print_stderr("FFmpeg binary could not be found.")
        print_and_exit("Make sure it's in your path.", 1)

    except (FFmpegTestFailedError, FFmpegProcessError):
        print_and_exit("Error while trying to run FFmpeg.", 1)

    except FFmpegMissingLib as err:
        print_and_exit(err, 1)

    else:
        conf.ffmpeg = ffmpeg


def init_qaac():
    try:
        qaac = Qaac(debug=conf.debug)

    except QaacNotFoundError:
        print_stderr("Qaac binary could not be found.")
        print_and_exit("Make sure it's in your path.", 1)

    except (QaacTestFailedError, QaacProcessError):
        print_and_exit("Error while trying to run Qaac.", 1)

    else:
        conf.qaac = qaac


def calc_volume(lufs):
    # calculation to -16dB LUFS:
    return round(-16 - lufs, 1)


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
    init_qaac()

    # create a list of all input flac files:
    if conf.input_is_file:
        if not conf.input.name.endswith(".flac"):
            print_and_exit("File {} is not a FLAC file!".format(conf.input.name), 1)

        conf.input_list.append(conf.input)

    else:
        conf.input_list = [file for file in conf.input.glob("*.flac")]

        if len(conf.input_list) == 0:
            print_and_exit("No FLAC files found in {}!".format(conf.input.name), 1)

    # loop over all input files and create (input, output) combinations while filtering out existing files:
    for file in conf.input_list:
        if conf.input_is_file:  # create a list that contains only one file
            aac_output_filename = file.parent / "{}_aac.m4a".format(file.stem)
            if not aac_output_filename.exists():
                conf.aac_conversion_list.append((file, aac_output_filename))
            else:
                print_stderr("{} alredy exists. Skipping...".format(aac_output_filename))

            alac_output_filename = file.parent / "{}_alac.m4a".format(file.stem)
            if not alac_output_filename.exists():
                conf.alac_conversion_list.append((file, alac_output_filename))
            else:
                print_stderr("{} alredy exists. Skipping...".format(alac_output_filename))

            mp3_output_filename = file.parent / "{}_mp3.m4a".format(file.stem)
            if not mp3_output_filename.exists():
                conf.mp3_conversion_list.append((file, mp3_output_filename))
            else:
                print_stderr("{} alredy exists. Skipping...".format(mp3_output_filename))

        else:
            aac_output_filename = conf.input / "aac" / "{}.m4a".format(file.stem)
            if not aac_output_filename.exists():
                conf.aac_conversion_list.append((file, aac_output_filename))
            else:
                print_stderr("{} alredy exists. Skipping...".format(aac_output_filename))

            alac_output_filename = conf.input / "alac" / "{}.m4a".format(file.stem)
            if not alac_output_filename.exists():
                conf.alac_conversion_list.append((file, alac_output_filename))
            else:
                print_stderr("{} alredy exists. Skipping...".format(alac_output_filename))

            mp3_output_filename = conf.input / "mp3" / "{}.mp3".format(file.stem)
            if not mp3_output_filename.exists():
                conf.mp3_conversion_list.append((file, mp3_output_filename))
            else:
                print_stderr("{} alredy exists. Skipping...".format(mp3_output_filename))

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
                        print_and_exit("Qaac error: {}".format(err), 1)
                    log.d("full stderr: {}".format(conf.qaac.full_stderr))
                else:
                    print_stderr("Would convert {} to {}.".format(input_file, output_file))
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
                        print_and_exit("Qaac error: {}".format(err), 1)
                    log.d("full stderr: {}".format(conf.qaac.full_stderr))
                else:
                    print_stderr("Would convert {} to {}.".format(input_file, output_file))
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
                    conf.ffmpeg.convert_to_mp3(input_file, output_file, volume=volume)
                    log.d("full stderr: {}".format(conf.ffmpeg.full_stderr))
                else:
                    print_stderr("Would convert {} to {}.".format(input_file, output_file))
        else:
            print_stderr("Nothing to do!")


if __name__ == "__main__":
    arguments = parse_args()

    # initialize the config class to store and share configuration:
    conf = Config()

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
