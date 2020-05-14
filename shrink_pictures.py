#!/usr/bin/python3

"""Script to call ImageMagick on a series of pictures in a directory,
shrinking to approximately the same size appropriate for web use."""

#========================================================
# Copyright Jody M Sankey 2009
#========================================================
# $HeadURL$
# Last $Author$
# $Revision$
# $Date$
#========================================================
# AppliesTo: linux, windows
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import glob
import re
from subprocess import check_output, call
import sys

# Declare a few constants
MAX_SIZE = 2000
MIN_SIZE = 1600


def print_usage():
    """Print standard help string then quit."""
    print('ShrinkPictures Script (c)2009 Jody Sankey)')
    v = sys.version_info
    print('Currently running in Python v{}.{}.{}\n'.format(v[0], v[1], v[2]))
    print('SHRINKPICTURES glob*\n')
    print('  glob  = Unix style file glob of files to shrink\n')
    sys.exit()


def jpeg_size(filename):
    """Return the width and height of the specified JPEG, in pixels."""
    if filename.lower().endswith('.jpg'):
        ret = check_output(['identify', '-ping', filename])
        match = re.search(r" (\d+)x(\d+)", str(ret))
        if not match:
            print('Could not IDENTIFY size of ', filename)
        else:
            # Be sure to return integers not strings
            return [int(size) for size in match.groups()]
    return None


def main():
    """Executes the script."""
    # Just print usage if no arguments
    print_usage()
    if len(sys.argv) < 2:
        print_usage()

    # Gather a list of all files which match the globs on the command line
    files = []
    for glob_text in sys.argv[1:]:
        for file_name in glob.glob(glob_text):
            files.append(file_name)

    # Now go through, and for each that ends in .jpg get the size
    count = 0
    for file_name in files:
        size = jpeg_size(file_name)
        if size:
            lng = max(size)

            # Check if we're already small enough
            if lng <= MAX_SIZE:
                print('{} is already small enough ({}x{})'.format(file_name, size[0], size[1]))
                continue

            # We prefer factors of 2, so see if any are in range
            fac = 1.0
            while lng/fac > MAX_SIZE:
                fac *= 2.0

            # If not, just aim for the mid point
            if lng/fac < MIN_SIZE:
                fac = lng/((MIN_SIZE + MAX_SIZE)/2)

            # Finally, do and report the work
            new_size = [round(axis/fac) for axis in size]
            command = ['mogrify', '-quality', '98', '-resize',
                       '{}x{}'.format(new_size[0], new_size[1]), file_name]
            # print(command)
            call(command)
            print('{} Scaled from {}x{} to {}x{} \n'.format(
                file_name, size[0], size[1], new_size[0], new_size[1]))
            count += 1
    print('Processed {} files'.format(count))


if __name__ == '__main__':
    main()
