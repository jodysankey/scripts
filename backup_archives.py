#!/usr/bin/python3
#========================================================
# Python script for linux to copy a dated set of archives
# on the primary server
#--------------------------------------------------------
# A new dated directory is created within the backup
# directory, with contents hardlinked to the previous
# backup for existing files, and copied from the current
# archive where not.
#========================================================
# Copyright Jody M Sankey 2015
#========================================================
# AppliesTo: linux
# AppliesTo: oberon
# RemoveExtension: True
#========================================================

VERBOSE = True # Set to see individual file operations

# Copies the archives for each user into a dated backup,
# using hardlinks to the previous backup to conserve space
# where possible.

from datetime import date
from os import path

import argparse
import os
import pwd
import re
import shutil
import sys


USERS = ('jody', 'family', 'systems')
ARCHIVE_DIR = 'archive'
BACKUP_DIR = 'archive_backups'
YMD_REGEX = re.compile(r'(\d{4})-(\d{2})-(\d{2})')

EXCLUDE_DIRS = ['large']


#TODO: When cron gets annoying write this to a log file instead of stdout
def _logDebug(text):
    if VERBOSE: print(text)

#TODO: When cron gets annoying write this to a log file instead of stdout
def _logInfo(text):
    print(text)

def _logWarning(text):
    print(text, file=sys.stderr)


def _datedDirs(directory):
    """Returns an ordered list of all date subdirectories, latest first"""
    # This was copied from datebatch
    dated_dirs = []
    for subdir in os.listdir(directory):
        mo = YMD_REGEX.search(subdir)
        if mo is not None and path.isdir(path.join(directory, subdir)):
            dated_dirs.append(date(*[int(x) for x in mo.groups()]))
    return sorted(dated_dirs)

def _latestYmdInDirectory(directory):
    """Return the largest matching YYYY-MM-DD directory in the directory,
    or None if no such directory exists."""
    dated_dirs = _datedDirs(directory)
    return path.join(directory, dated_dirs[-1].isoformat()) if dated_dirs else None

def _copyOrLinkFile(out_dir, in_dir, existing_dir, filename):
    """Builds an output directory in out_dir, containing all files in
    in_dir. If a file of the same name exsits in esisting_dir it will
    be hardlinked, if not the file will be copied from in_dir.
    existing_dir may be None, in which case all files will be copied."""
    out_file = path.join(out_dir, filename)
    in_file = path.join(in_dir, filename)
    existing_file = path.join(existing_dir, filename) if existing_dir else None

    # TODO: A bit more fault tolerance here
    # Note archives are touch'ed each date they are still accurate, so don't want to
    # use modifiction time as  change detector
    if (existing_file and path.exists(existing_file) and 
          path.getsize(existing_file) == path.getsize(in_file)):
        _logDebug('   Hardlinking {} to {}'.format(existing_file, out_file))
        os.link(existing_file, out_file)
    else:
        _logDebug('   Copying {} to {}'.format(in_file, out_file))
        shutil.copy2(in_file, out_file)


def backupUserArchives(backup_dir, in_dir):
    """Creates a directory with the current date within backup_dir,
    containing all files in in_dir, using hardlinks from the previous
    backup where possible. Return True on success and False on fail."""
    if not path.exists(in_dir):
        _logWarning('Input directory {} did not exist'.format(in_dir))
        return False
    elif not path.exists(backup_dir):
        _logWarning('Backup directory {} did not exist'.format(backup_dir))
        return False

    last_backup_dir = _latestYmdInDirectory(backup_dir)
    this_backup_dir = path.join(backup_dir, date.today().isoformat())
    if path.exists(this_backup_dir):
        _logInfo("Today's backup already exists " + this_backup_dir)
        return True
    else:
        _logInfo("Creating backup directory " + this_backup_dir)
        os.mkdir(this_backup_dir)

    for in_current, dirs, files in os.walk(in_dir, topdown=True):
        # Copy/link the files, create the directories.
        current_rel = path.relpath(in_current, in_dir)
        last_backup_current = path.join(last_backup_dir, current_rel) if last_backup_dir else None
        this_backup_current = path.join(this_backup_dir, current_rel)
        if not path.exists(this_backup_current):
            # Note we get .../YYY_MM_DD/. which exsits, other should not
            _logInfo('Making ' + this_backup_current)
            os.mkdir(this_backup_current)
            for f in files:
                _copyOrLinkFile(this_backup_current, in_current, last_backup_current, f)
            for d in dirs:
                if d in EXCLUDE_DIRS:
                    dirs.remove(d)
                    _logInfo('Skipping excluded dir ' + d)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Copies files from an archive location to a new '
            'dated directory in a backup directory, hardlinking to files in the previous date '
            'where possible')
    parser.add_argument('-a', '--archive_dir', required=True,
                        help='Path to copy archive files from')
    parser.add_argument('-b', '--backup_dir', required=True, 
                        help='Path to be create dated backup directory')
    parser.add_argument('-u', '--user',
                        help='Username to run operations as')
    args = parser.parse_args()

    if args.user:
        os.setuid(pwd.getpwnam(args.user).pw_uid)
    success = backupUserArchives(args.backup_dir, args.archive_dir)
    sys.exit(0 if success else 1)
