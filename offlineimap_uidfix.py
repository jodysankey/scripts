#!/usr/bin/python3

"""Script to remove all trace of a missynchronized offlineimap mailbox."""

#========================================================
# Copyright Jody M Sankey 2017
#========================================================
# AppliesTo: linux
# AppliesTo: server
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import os
import shutil
import sys

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('USAGE {} MailServer Dot.Separated.Mailbox.Without.INBOX.Prefix'.format(sys.argv[0]))
        sys.exit(1)

    CONFIG_ROOT = os.path.expanduser('~/.offlineimap')
    STORAGE_ROOT = os.path.expanduser('~/files/dealings/Email')
    PATHS = [
        os.path.join(STORAGE_ROOT, sys.argv[1] + 'Maildir', sys.argv[2]),
        os.path.join(CONFIG_ROOT, 'Account-' + sys.argv[1], 'LocalStatus', sys.argv[2]),
        os.path.join(CONFIG_ROOT, 'Repository-' + sys.argv[1] + 'Remote',
                     'FolderValidity', 'INBOX.' + sys.argv[2]),
    ]

    for path in PATHS:
        if not os.path.exists(path):
            print('Could not find folder' + path)
            sys.exit(1)
    for path in PATHS:
        if os.path.isdir(path):
            print('Recursively deleting ' + path)
            shutil.rmtree(path)
        else:
            print('Deleting ' + path)
            os.remove(path)
