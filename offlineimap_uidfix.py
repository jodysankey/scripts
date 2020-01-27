#!/usr/bin/python3
# -*- coding: utf-8 -*-
#========================================================
# Python script to remove all trace of a missynchronized
# offlineimap mailbox.
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

  configroot = os.path.expanduser('~/.offlineimap')
  storageroot = os.path.expanduser('~/files/dealings/Email')
  paths = [
    os.path.join(storageroot, sys.argv[1] + 'Maildir', sys.argv[2]),
    os.path.join(configroot, 'Account-' + sys.argv[1], 'LocalStatus', sys.argv[2]),
    os.path.join(configroot, 'Repository-' + sys.argv[1] + 'Remote',
        'FolderValidity', 'INBOX.' + sys.argv[2]),
  ]

  for p in paths:
    if not os.path.exists(p):
      print('Could not find folder' + p)
      sys.exit(1)
  for p in paths:
    if os.path.isdir(p):
      print('Recursively deleting ' + p)
      shutil.rmtree(p)
    else:
      print('Deleting ' + p)
      os.remove(p)
