#!/usr/bin/python3

"""Script for linux to dump a list of hashes for all files in
a set of directories. The output is sorted by hash."""

#========================================================
# Copyright Jody M Sankey 2019
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import argparse
import base64
import hashlib
import os
import re
import sys

BLOCK_SIZE = 1024*1024
LOG_INTERVAL = 100

def _create_arg_parser():
    """Returns a configured ArgumentParser."""
    parser = argparse.ArgumentParser(description='Builds a list of files and their hashes '
                                     'sorted by hash')
    parser.add_argument('-i', '--in', required=True, action='append', dest='input',
                        help='path to search for files, more than one may be used')
    parser.add_argument('-e', '--exclude', action='append', metavar='EX',
                        help='regex to exclude files or directories from the search')
    parser.add_argument('-o', '--out', required=True, dest='output',
                        help='output filename')
    parser.add_argument('-s', '--silent', action='store_true',
                        help='don\'t output progress information')
    return parser


def _gather_paths(in_dirs, exclude_regex, log_interval):
    """Returns a list of fully qualified paths for every not-excluded file in in_dirs."""
    output = []
    count_since_log, file_count, dir_count, exclude_file_count, exclude_dir_count = (0, 0, 0, 0, 0)
    excludes = [re.compile(r) for r in exclude_regex]
    for in_dir in in_dirs:
        for root, dirs, files in os.walk(in_dir):
            # Remove any directories that match the regex exclusion patterns so we don't walk them
            filtered_dirs = [d for d in dirs if not any((ex.search(d) for ex in excludes))]
            exclude_dir_count += (len(dirs) - len(filtered_dirs))
            dirs[:] = filtered_dirs

            # Remove any files that match the regex exclusion patterns
            filtered_files = [f for f in files if not any((ex.search(f) for ex in excludes))]
            exclude_file_count += (len(files) - len(filtered_files))

            dir_count += 1
            for f in filtered_files:
                output.append(os.path.join(root, f))
                file_count += 1
                count_since_log += 1
                if count_since_log >= log_interval:
                    print("Gathered {} files from {} dirs, excluded {} files and {} dirs".format(
                        file_count, dir_count, exclude_file_count, exclude_dir_count))
                    count_since_log = 0
    return output


def hash_file(path):
    """Returns a base64 encoded hash of the input file."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        buffer = f.read(BLOCK_SIZE)
        while len(buffer) > 0:
            hasher.update(buffer)
            buffer = f.read(BLOCK_SIZE)
    return base64.urlsafe_b64encode(hasher.digest()[:12]).decode('utf-8')


def hash_paths(paths, log_interval):
    """Returns a map of the base64 hash to the filename for all paths in path."""
    output = {}
    count_since_log = 0

    for path in paths:
        output[hash_file(path)] = os.path.basename(path)
        count_since_log += 1
        if count_since_log >= log_interval:
            print("Hashed {} of {} files: {}".format(len(output), len(paths),
                                                     os.path.basename(path)))
            count_since_log = 0
    return output


def _output_hashes(hashes, output_path):
    """Writes the supplied dictionary of hashes to an ordered file."""
    keys = sorted(hashes.keys())
    with open(output_path, 'w') as f:
        for k in keys:
            f.write("{}\t{}\n".format(k, hashes[k]))


def main():
    """Hashes a set of files based on command line arguments."""
    args = _create_arg_parser().parse_args()

    log_interval = sys.maxsize if args.silent else LOG_INTERVAL
    exclude_paths = ["^[.]"] + (args.exclude if args.exclude else [])

    if not args.silent:
        print("Gathering matching files.")
    paths = _gather_paths(args.input, exclude_paths, log_interval * 10)
    if not args.silent:
        print("Calculating hashes.")
    hashes = hash_paths(paths, log_interval)
    if not args.silent:
        print("Writing output file.")
    _output_hashes(hashes, args.output)
    if not args.silent:
        print("Done.")


if __name__ == '__main__':
    main()
