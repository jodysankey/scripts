#!/bin/python3

"""Script to link duplicate files to the same inode
Run with --help to see the command line options."""

#==============================================================
# Copyright Jody M Sankey 2022
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENCE.md file for details.
#==============================================================
# AppliesTo: linux
# AppliesTo: server
# RemoveExtension: True
# PublicPermissions: True
#==============================================================

import argparse
import os.path
import stat
import sys


class File:
    """A uniquely named files."""
    def __init__(self, path, size, inode):
        self.path = path
        self.size = size
        self.inode = inode

    def __str__(self):
        return f'{self.path}'


def find_duplicates(path, unlinked_fn, linked_fn):
    """Searches all files in path for duplicate names and matching sizes,
    running linked_fn with (first_path, other_path) if they already
    point to the same inode and unlinked_fn if they don't. Prints a
    warning on files with the same name but different sizes. Returns
    the number of unique files."""

    found = {}
    for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
        dirs.sort()
        for f in files:
            f_path = os.path.join(root, f)
            f_stat = os.stat(f_path, follow_symlinks=False)
            if not stat.S_ISREG(f_stat.st_mode):
                print(f'Ignoring non regular file {f_path}')
                continue

            this_file = File(f_path, f_stat.st_size, f_stat.st_ino)
            if f in found:
                existing_file = found[f]
                if existing_file.size != this_file.size:
                    print(f'Ignoring {this_file.path} with different size to {existing_file.path}'
                          f' ({this_file.size} vs {existing_file.size})')
                # Process this duplicate file
                elif existing_file.inode == this_file.inode:
                    linked_fn(existing_file.path, this_file.path)
                else:
                    unlinked_fn(existing_file.path, this_file.path)
            else:
                # Add this file we've not seen before.
                found[f] = this_file
    return len(found)


def dry_run(path):
    """Runs the program in dry run mode."""
    count = find_duplicates(path=path,
                            unlinked_fn=lambda f, o: print(f'Would link {o} to {f}'),
                            linked_fn=lambda f, o: print(f'Already linked {o} to {f}'))
    print(f'{count} distinct files')


def live(path):
    """Runs the program in live mode."""
    existing_matches = {}
    new_matches = {}

    def increment_dict_count(dictionary, member):
        try:
            dictionary[member] += 1
        except KeyError:
            dictionary[member] = 1

    def linked_fn(first, _):
        increment_dict_count(existing_matches, first)

    def unlinked_fn(first, other):
        print(f'Hardlinking {other} to {first}')
        os.unlink(other)
        os.link(src=first, dst=other)
        increment_dict_count(new_matches, first)

    total_distinct = find_duplicates(path=path, unlinked_fn=unlinked_fn, linked_fn=linked_fn)
    for name, count in existing_matches.items():
        print(f'{count} existing links to {name}')
    print(f'{sum(existing_matches.values())} existing hard links')
    print(f'{sum(new_matches.values())} new hard links')
    print(f'{total_distinct} distinct files')


def create_parser():
    """Creates the definition of the expected command line flags."""
    parser = argparse.ArgumentParser(
        description='Script to link files with the same name and size to the same inode. '
                    'NOTE: This obviously won\'t work well if the directory name contains '
                    'duplicates, but its great for backup directories where a hash of the '
                    'content is included in the filename.',
        epilog='Copyright Jody Sankey 2022')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-d', '--dryrun', action='store_true',
                       help='Print changes that would be made.')
    group.add_argument('-l', '--live', action='store_true',
                       help='Actually make changes.')
    parser.add_argument('path', action='store', help='The path to search')
    return parser


def main():
    """Executes the script using command line arguments."""
    args = create_parser().parse_args()
    if args.live:
        live(args.path)
    else:
        dry_run(args.path)


if __name__ == '__main__':
    main()
