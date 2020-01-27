#!/usr/bin/python3
# -*- coding: utf-8 -*-
#========================================================
# Simple script to return a zero success code at most
# once per day, when the host is connected to the 
# standard network. Useful for fixing cron to work when
# machines are not reliably powered on.
#========================================================
# Copyright Jody M Sankey 2014
#========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import os
import re
import sys
import subprocess
from datetime import date, datetime


def printUsage():
    print("Usage:")
    print("  {} trigger_file [essid]".format(os.path.basename(__file__)))
    print("  trigger_file = a file to use to record previous executions")
    print("  essid  = an optional ESSID srting that must be in the current")
    print("           iwconfig otherwise the script will fail")
    print("Return values:")
    print("  0 = if supplied, essid is present and first time this")
    print("      condition has been met today.")
    print("  1 = run has already succeeded for today")
    print("  2 = mount_point was not mounted")
    print("  3 = invalid arguments")
    print("  4 = some other problem")
    
#        try:
#            mounts = subprocess.check_output(["mount"]).decode("utf-8").split("\n")
#            filtered = [m for m in mounts if (" " + mount_point + " ") in m]
#        except Exception as e:
#            print(sys.exc_info())
#            sys.exit(4)
#        if len(filtered) == 0:
#            sys.exit(2)
 
if __name__ == '__main__':

    #Just print usage if wrong number of arguments supplied
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        printUsage()
        sys.exit(3)
    trigger_file = sys.argv[1]
    essid = None if len(sys.argv) == 2 else sys.argv[2]

    #If trigger file is present and modified today we're good
    if os.path.exists(trigger_file):
        if date.fromtimestamp(os.path.getmtime(trigger_file)) == date.today():
            sys.exit(1)

    #If we had an ESSID check it is currently connected
    if essid is not None:
        finder = re.compile("ESSID.+" + essid)
        try:
            iwconfig = subprocess.check_output(["iwconfig"]).decode("utf-8").split("\n")
            filtered = [l for l in iwconfig if finder.search(l)]
        except Exception as e:
            print(sys.exc_info())
            sys.exit(4)
        if len(filtered) == 0:
            sys.exit(2)
            
    #Write the current datetime to the file
    try:
        with open(trigger_file, "a") as fh:
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), file=fh)
    except Exception as e: 
        print(sys.exc_info())
        sys.exit(4)

    #Return success
    sys.exit(0)
