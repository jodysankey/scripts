#!/usr/bin/python3

"""Script for linux to make and scale scans. Relies on scan_core, which
in turn uses scanimage (SANE) for the scanning and ImageMagick for the
image manipulation."""

# ========================================================
# Copyright Jody M Sankey 2010 - 2025
# ========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
# ========================================================

import os
import re
import sys
import scan_core

OUTPUT_PATH: str = os.path.expanduser("~/tmp/scan")
DEFAULT_PREFIX: str = "scan"


def print_customization_options(
    options: scan_core.CustomizationOptions, leader: str
) -> None:
    """Print a line for each option in the set, prefixed with leader"""
    for option in options:
        labels = ",".join(option.labels)
        options = leader + labels + " " * (20 - len(labels)) + "- " + option.description
        print(options)


def print_usage() -> None:
    """Print standard help string then quit"""
    leader = "        "
    print("\n  Usage: scanning [-v|-c|-k=N] SOURCE PAPER SCALE COLOR [basename]\n")
    print("  SOURCE  Paper source:")
    print_customization_options(scan_core.SOURCES, leader)
    print("  PAPER    Paper size:")
    print_customization_options(scan_core.PAPERS, leader)
    print("  SCALE    Scaling factor:")
    print_customization_options(scan_core.SCALES, leader)
    print("  COLOR    Colour mode:")
    print_customization_options(scan_core.COLORS, leader)
    print("  basename Desired base filename")
    print("  -v       View each scan when conversion is complete")
    print("  -c       Confirm each scan before saving in final location")
    print("  -d       Print the scanning and conversion commands for debugging")
    print("  -k=N     Do not convert page N of scan\n")
    print("SCANNING Script (c)2010 Jody Sankey")
    version = sys.version_info
    print("Currently running in Python v{}.{}.{}\n".format(*version))


def main() -> None:
    """Run the scanning function using parameters from the command line."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit()
    args = sys.argv[1:]

    # Declare and initialize the variables controlled by switch
    options = scan_core.ScanOptions()
    kills = []

    # Eat any switches from the front
    while args and args[0].startswith("-"):
        arg = args.pop(0).lower()
        mko = re.search(r"-k=([1-9]+)$", arg)
        if mko is not None:
            kills.append(int(mko.groups()[0]))
        elif arg == "-c":
            options.check = True
        elif arg == "-v":
            options.view = True
        elif arg == "-d":
            options.debug = True
        elif arg == "--help":
            print_usage()
            sys.exit()
        else:
            print("ERROR: Switch '{}' not recognized".format(arg))
            sys.exit(1)

    # Do we have enough parameters left?
    if len(args) not in (4, 5):
        print(args)
        print("ERROR: Wrong number of parameters supplied")
        sys.exit(1)

    try:
        customizations = scan_core.SelectedCustomizations.from_labels(
            args[0], args[1], args[2], args[3]
        )
    except KeyError as err:
        print(err)
        sys.exit(1)

    scan_core.scan_and_convert(
        OUTPUT_PATH,
        args[4] if len(args) == 5 else DEFAULT_PREFIX,
        customizations,
        options,
        kills,
    )


if __name__ == "__main__":
    main()
