#!/usr/bin/python3
#========================================================
# Python script for linux to make and scale scans.
# relies on scanimage (SANE) for the scanning and
# ImageMagick for the image manipulation
#========================================================
# Copyright Jody M Sankey 2010 - 2018
#========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
#========================================================


import sys
import scan_core


def print_option_set(option_set, leader):
    """Print a line for each option in the set, prefixed with leader"""
    for option in option_set:
        labels = ",".join(option['labels'])
        option_set = leader + labels + " "*(20-len(labels)) + "- " + option['description']
        print(option_set)


def print_usage():
    """Print standard help string then quit"""
    leader = "        "
    print("\n  Usage: scanning [-v|-c|-k=N] SOURCE PAPER SCALE COLOR [basename]\n")
    print("  SOURCE  Paper source:")
    print_option_set(scan_core.SOURCES, leader)
    print("  PAPER    Paper size:")
    print_option_set(scan_core.PAPERS, leader)
    print("  SCALE    Scaling factor:")
    print_option_set(scan_core.SCALES, leader)
    print("  COLOR    Colour mode:")
    print_option_set(scan_core.COLORS, leader)
    print("  basename Desired base filename, optionally including path")
    print("  -v       View each scan when conversion is complete")
    print("  -c       Confirm each scan before saving in final location\n")
    print("  -k=N     Do not convert page N of scan\n")
    print("SCANNING Script (c)2010 Jody Sankey")
    v = sys.version_info
    print("Currently running in Python v{}.{}.{}\n".format(*v))
    sys.exit()


def die(print_string):
    """Prints the specified string then exits with code 1"""
    print(print_string)
    sys.exit(1)


if __name__ == '__main__':
    #If run as a script take parameters to feed the function from the command line

    #Just print usage if no arguments supplied
    if len(sys.argv)<2:
        print_usage()
    args = sys.argv[1:]

    #Declare and initialize the variables controlled by switch
    check = False
    view = False
    kills = []

    #Eat any switches from the front
    while len(args) and args[0].startswith('-'):
        arg = args.pop(0).lower()
        print("eating " + arg)
        mko = re.search(r"-k=([1-9]+)$", arg)
        if mko is not None:
            kills.append(int(mko.groups()[0]))
        elif arg == '-c':
            check = True
        elif arg == '-v':
            view = True
        elif arg == '--help':
            print_usage()
        else:
            die("ERROR: Switch '{}' not recognized".format(arg))

    # Do we have enough parameters left?
    if len(args) not in range(4,6):
        print(args)
        die("ERROR: Wrong number of parameters supplied")
    dest = os.path.join(SCAN_PATH, args[4]) if len(args) == 5 else None

    scan_core.perform_scan(dest, args[0], args[1], args[2], args[3], view, check, kills)