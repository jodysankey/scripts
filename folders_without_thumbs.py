#!/usr/bin/python3
#========================================================
# Python script for linux or windows to list all the 
# lowest level directories in the current working directory
# which do not contain a THUMB file as specified in the
# constant below.
#========================================================
# Copyright Jody M Sankey 2010
#========================================================
# $HeadURL$
# Last $Author: jody $
# $Revision: 720 $
# $Date: 2009-10-30 18:12:20 -0500 (Fri, 30 Oct 2009) $
#========================================================
# AppliesTo: linux, windows
# RemoveExtension: True
# PublicPermissions: True
#========================================================

THUMB = "folder.jpg"

import os
import sys

if len(sys.argv)>1:
    dir = sys.argv[1]
else:
    dir = os.getcwd()

for root, dirs, files in os.walk(dir):
    if len(dirs)==0:
        if not(THUMB in files):
            print(root)
