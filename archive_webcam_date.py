#!/usr/bin/python3
#========================================================
# Python script for linux to slimdown a directory of files 
# named by date, currently configured to keep the first 
# file from every hour. 
# A date must be specified on the command line, either as 
# absolute or number of days prior to today. The first 
# image from each hour on that day will be copied from 
# live to archive, the rest will be deleted
#========================================================
# Copyright Jody M Sankey 2010
#========================================================
# AppliesTo: linux
# AppliesTo: oberon
# RemoveExtension: True
#========================================================


LIVE_DIR = "/home/open/webcam/live"                             # Location of files
ARCHIVE_DIR = "/home/open/webcam/archive"                       # Location of files
FILE_FORMAT_RE =  r"(\d{4}-\d{2}-\d{2}_\d{2}):\d{2}:\d{2}\.jpg" # RegEx which filenames must match, ones with distinct group[0] are kept
DATE_FORMAT_OUTPUT = "%Y-%m-%d_00"                              # Strftime string to convert date object to the group[0] above
DATE_FORMAT_INPUT = "%Y-%m-%d"                                  # Strftime string to convert string to date object

import getopt
import os
import re
import sys
from datetime import date,timedelta,datetime


# Function to print usage then quit with the given code
def usage(quit_code):
    bn = os.path.basename(sys.argv[0])
    print(bn + ", copyright 2010 Jody Sankey")
    print("  {} [-v|--verbose] int|date|all".format(bn))
    print("  Specify DATE to archive or")
    print("  Specify archive of (today - INT) or")
    print("  Specify archive of ALL days before today")
    sys.exit(quit_code)


# Parse the command line for the one valid option
try:
    opts, args = getopt.getopt(sys.argv[1:], "v", ["verbose"])
except getopt.GetoptError as err:
    print(err)
    usage(1)
verbose = len(opts)>0

if len(args)!=1:
    usage()
    sys.exit(1)    

#Determine the date range to process and get the strings to match
if args[0].lower() == 'all':
    date_range = [date(1900,1,1),date.today()]
else:
    the_date = None
    try:
        i = int(args[0])
        if i<1:
            print("\nERROR: INT must be greater than zero")
            usage(1)
        the_date = date.today() - timedelta(i)
    except ValueError as err:
        try:
            the_date = datetime.strptime(args[0],DATE_FORMAT_INPUT) 
        except ValueError as err:
            print(err)
            usage(1)
    date_range = [the_date,the_date + timedelta(1)]


match_range = [d.strftime(DATE_FORMAT_OUTPUT) for d in date_range]
if verbose: print("Wish to archive from {} to {}".format(*match_range))
#sys.exit(0) This was the safety switch during testing

# Gather a sorted list of all files 
files = os.listdir(LIVE_DIR)
files.sort()
prev_match = ""

for file in files:
    mo = re.search(FILE_FORMAT_RE, file)
    
    # Only do files which match our template
    if mo:                                              
        if mo.groups()[0] >= match_range[1]:
            # Stop if we're bigger then the stop string
            if verbose: print("Stopping at {}, after specified date".format(file))
            break
        elif mo.groups()[0] >= match_range[0]:
            #Something worthy of examining
            if mo.groups()[0] == prev_match:
                # Delete the file if its the same match (i.e. hour) as the previous one
                if verbose: print("Removing {} since it shares {}".format(file,prev_match))
                os.remove(os.path.join(LIVE_DIR,file))    
            else:
                # Otherwise move the file
                if verbose: print("Archiving {}".format(file))
                os.rename(os.path.join(LIVE_DIR,file),os.path.join(ARCHIVE_DIR,file))
                prev_match = mo.groups()[0]
