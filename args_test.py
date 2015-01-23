#!python3
# -*- coding: utf-8 -*-


if __name__ == "__main__":
    import argparse
    import sys
    #sys.argv.append("--itunes")
    sys.argv.append("--aac")
    sys.argv.append("--mp3")
    sys.argv.append("-v")
    sys.argv.append("-h")
    #sys.argv.append("--quality=4")
    sys.argv.append("ggg")

    parser = argparse.ArgumentParser(description="EBU R128 Loudness Normalizer")

    parser.add_argument("-v", action="store_true", dest="verbose",
                        help="verbose")
    parser.add_argument("-d", action="store_true", dest="debug",
                        help="debug")

    parser.add_argument("-n", action="store_true", dest="simulate",
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

    parser.add_argument("input", metavar="<input file or folder>")

    args = parser.parse_args()
    print(args)
