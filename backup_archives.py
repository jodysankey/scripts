#!/usr/bin/python3

"""Python script for linux to copy a dated set of archives on the primary server.

A new dated directory is created within the backup directory, with contents hardlinked to the
previous backup for existing files, and copied from the current archive where not."""

#========================================================
# Copyright Jody M Sankey 2015-2020
#========================================================
# AppliesTo: linux
# AppliesTo: oberon
# RemoveExtension: True
#========================================================

import argparse
from datetime import date
import os
from os import path
import pwd
import re
import shutil
import sys


VERBOSE = True # Set to see individual file operations

YMD_REGEX = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
EXCLUDE_DIRS = ['large']


#TODO: When cron gets annoying write this to a log file instead of stdout
def _log_debug(text):
    if VERBOSE: print(text)

#TODO: When cron gets annoying write this to a log file instead of stdout
def _log_info(text):
    print(text)

def _log_warning(text):
    print(text, file=sys.stderr)


def _dated_dir(directory):
    """Returns an ordered list of all date subdirectories, latest first"""
    # This was copied from datebatch
    dated_dirs = []
    for subdir in os.listdir(directory):
        match = YMD_REGEX.search(subdir)
        if match is not None and path.isdir(path.join(directory, subdir)):
            dated_dirs.append(date(*[int(x) for x in match.groups()]))
    return sorted(dated_dirs)

def _latest_ymd_in_directory(directory):
    """Return the largest matching YYYY-MM-DD directory in the directory,
    or None if no such directory exists."""
    dated_dirs = _dated_dir(directory)
    return path.join(directory, dated_dirs[-1].isoformat()) if dated_dirs else None

def _copy_or_link_file(out_dir, in_dir, existing_dir, filename):
    """Builds an output directory in out_dir, containing all files in
    in_dir. If a file of the same name exists in existing_dir it will
    be hardlinked, if not the file will be copied from in_dir.
    existing_dir may be None, in which case all files will be copied."""
    out_file = path.join(out_dir, filename)
    in_file = path.join(in_dir, filename)
    existing_file = None if existing_dir is None else path.join(existing_dir, filename)

    # TODO: A bit more fault tolerance here
    # Note archives are touch'ed each date they are still accurate, so don't want to
    # use modification time as change detector
    if (existing_file and path.exists(existing_file) and
            path.getsize(existing_file) == path.getsize(in_file)):
        _log_debug('   Hardlinking {} to {}'.format(existing_file, out_file))
        os.link(existing_file, out_file)
    else:
        _log_debug('   Copying {} to {}'.format(in_file, out_file))
        shutil.copy2(in_file, out_file)


def backup_user_archives(backup_dir, in_dir):
    """Creates a directory with the current date within backup_dir,
    containing all files in in_dir, using hardlinks from the previous
    backup where possible. Return True on success and False on fail."""
    if not path.exists(in_dir):
        _log_warning('Input directory {} did not exist'.format(in_dir))
        return False
    if not path.exists(backup_dir):
        _log_warning('Backup directory {} did not exist'.format(backup_dir))
        return False

    last_backup_dir = _latest_ymd_in_directory(backup_dir)
    this_backup_dir = path.join(backup_dir, date.today().isoformat())
    if path.exists(this_backup_dir):
        _log_info("Today's backup already exists " + this_backup_dir)
        return True

    _log_info("Creating backup directory " + this_backup_dir)
    os.mkdir(this_backup_dir)

    for in_current, dirs, files in os.walk(in_dir, topdown=True):
        # Copy/link the files, create the directories.
        current_rel = path.relpath(in_current, in_dir)
        last_backup_current = path.join(last_backup_dir, current_rel) if last_backup_dir else None
        this_backup_current = path.join(this_backup_dir, current_rel)
        if not path.exists(this_backup_current):
            # Note we get .../YYY_MM_DD/. which exists, other should not
            _log_info('Making ' + this_backup_current)
            os.mkdir(this_backup_current)
            for _file in files:
                _copy_or_link_file(this_backup_current, in_current, last_backup_current, _file)
            for _dir in dirs:
                if _dir in EXCLUDE_DIRS:
                    dirs.remove(_dir)
                    _log_info('Skipping excluded dir ' + _dir)
    return True


def build_parser():
    """Creates a command line argument parser."""
    parser = argparse.ArgumentParser(
        description='Copies files from an archive location to a new dated directory in a backup '
        'directory, hardlinking to files in the previous date where possible')
    parser.add_argument('-a', '--archive_dir', required=True,
                        help='Path to copy archive files from')
    parser.add_argument('-b', '--backup_dir', required=True,
                        help='Path to be create dated backup directory')
    parser.add_argument('-u', '--user',
                        help='Username to run operations as')
    return parser


def main():
    """Creates a user archive backup using command line inputs."""
    args = build_parser().parse_args()
    if args.user:
        os.setuid(pwd.getpwnam(args.user).pw_uid)
    success = backup_user_archives(args.backup_dir, args.archive_dir)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
