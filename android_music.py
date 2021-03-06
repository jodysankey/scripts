#!/usr/bin/python3
# -*- coding: utf-8 -*-
#========================================================
# Python script for linux to manipulate a subset of music
# and synchronize that music with an android device
#--------------------------------------------------------
# Set of directories to exclude from the complete corpus
# is stored in a supplied exclusion file, and can be
# modified to add or remove directories. Android 
# interactions use adb and probably won't work outside of
# Linux.
#========================================================
# Copyright Jody M Sankey 2013
#========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import os.path
import sys
import re
import subprocess

MUSIC_ROOT = "/mnt/open/music"
ANDROID_ROOT = "/sdcard/Music"

music_dirs = []
android_dirs = []

modes = [{"letter":"r", "description":"Report total size of configuration", "regex":False, "require_file":False},
         {"letter":"i", "description":"Increase size of a configuration, by regex or interactively", "regex":True, "require_file":True},
         {"letter":"d", "description":"Decrease size of a configuration, by regex or interactively", "regex":True, "require_file":False},
         {"letter":"q", "description":"Query current contents of android device", "regex":False, "require_file":True},
         {"letter":"p", "description":"Push configuration to an android device", "regex":False, "require_file":True}, ]

class MusicDirectory:
    """Define a local directory containing a set of music files"""
    def __init__(self, rel_dir): 
        self.rel_dir = rel_dir
        self.included = True
    def __str__(self):
        return self.rel_dir
    @property
    def abs_dir(self):
        return os.path.join(MUSIC_ROOT, self.rel_dir)
    @property
    def abs_files(self):
        return [(os.path.join(self.abs_dir,f)) for f in os.listdir(self.abs_dir) if os.path.isfile(os.path.join(self.abs_dir,f))]
    @property
    def size(self):
        return sum([os.path.getsize(f) for f in self.abs_files])
   

def sizeofFmt(num):
    for x in ['bytes','KB','MB','GB','TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0

def buildAllMusicDirectories():
    """Create objects for each music directory in MUSIC_ROOT and add to the global list"""
    global music_dirs
    music_dirs = []
    for root, dirs, files in os.walk(MUSIC_ROOT):
        #Only process leaf directories with files
        if files and not dirs:
            music_dirs.append(MusicDirectory(os.path.relpath(root, MUSIC_ROOT)))
        elif dirs:
            dirs.sort()
   
def buildAllAndroidDirectories():
    """Create strings for each music directory on the Android device and add to the global list"""
    global android_dirs
    android_dirs = []
    # We use a BFS algorithm
    unvisited = [""]
    while len(unvisited) > 0:
        current = unvisited.pop(0)
        contents = subprocess.check_output(['adb', 'shell', 'ls', '-F', os.path.join(ANDROID_ROOT, current)]).decode("utf-8").split("\n")
        unvisited.extend([os.path.join(current, ln.strip()[2:]) for ln in contents if ln.startswith("d ")])
        if current != "": android_dirs.append(current)

def markExcludedUsingFile(exclusion_file_name):   
    """Set each music_dir present in the supplied exclusion_file to excluded"""
    music_dict = dict([[d.rel_dir, d] for d in music_dirs])
    if not os.path.exists(exclusion_file_name): return
    exclusion_file = open(exclusion_file_name, mode="r")
    for line in [l.strip() for l in exclusion_file]:
        if line not in music_dict:
            print("WARNING: Ignoring unknown exclusion directory " + line) 
        else:
            music_dict[line].included = False
    exclusion_file.close()
  
def writeExcludedToFile(exclusion_file_name):
    """Write a exclusion_file containing the names of all directories that are marked as excluded""" 
    exclusion_file = open(exclusion_file_name, mode="w")
    for d in music_dirs:
        if not d.included: exclusion_file.write(d.rel_dir + "\n")
    exclusion_file.close()       

def printUsage():
    """Prints syntax help to stdout""" 
    print("Android music library subconfiguration manager, Jody Sankey 2013")
    print("  Usage:  " + os.path.basename(__file__) + " <mode> <exclusion_file> [regex]")
    print("  Where <mode> is one of:")
    for m in modes:
        print("    -{}  {}".format(m["letter"], m["description"]))
 
def __getSkipSelectQuit(prompt): 
    """Repeatedly prompts the user until he returns a valid selection from skip/select/quit"""
    while True:
        response = input(prompt + " [enter to skip, 's' to select, 'q' to quit]")
        if response == "": return "skip"
        elif response == "s": return "select"
        elif response == "q": return "quit"

def __addRemove(base, delta, adding):
    if adding:
        return base + delta
    return base - delta
 
def flipMusicDirectories(dirs, total_size, regex):   
    """Interacts with the user (or uses a regex if provided) to toggle inclusion state of music directories"""
    adding = (len(dirs)>0 and not dirs[0].included)
    count = 0
    size_change = 0
    for d in dirs:
        if regex is None:
            action = __getSkipSelectQuit("Current size {:7s}, {} {} ({})?".format(
                    sizeofFmt(__addRemove(total_size, size_change, adding)),
                    "add" if adding else "remove", d.rel_dir, sizeofFmt(d.size)))
            if action == "quit": 
                break
            elif action == "select":
                d.included = not d.included
                count += 1
                size_change += d.size
        elif re.search(regex, d.rel_dir):
            print("{}ing {} ({})".format("Add" if adding else "Remov", d.rel_dir, sizeofFmt(d.size)))
            d.included = not d.included
            count += 1
            size_change += d.size
    print("{}ed {} directories, {}ing {}, for a new total size of {}".format("Add" if adding else "Remov", count, 
        "add" if adding else "sav", sizeofFmt(size_change), sizeofFmt(__addRemove(total_size, size_change, adding))))

def syncMusicDirectories():
    """Pushes a set of music dirs to an Android device where the directory is absent, and removes additional directories. 
    Directory contents are not checked for consistency"""
    unused_android_set = set(android_dirs)
    for music_dir in (x for x in music_dirs if x.included):
        if music_dir.rel_dir not in unused_android_set:
            dest = os.path.join(ANDROID_ROOT, music_dir.rel_dir)
            print("Creating {} ...".format(dest))
            subprocess.check_call(['adb', 'shell', 'mkdir', '-p', dest])
            for f in music_dir.abs_files:
                print("  Copying {} ...   ".format(f), end="")
                sys.stdout.flush()
                subprocess.check_call(['adb', 'push', f, os.path.join(dest,os.path.relpath(f, music_dir.abs_dir))])
        used_dir = music_dir.rel_dir
        while used_dir != '':
            unused_android_set.discard(used_dir)
            used_dir = os.path.split(used_dir)[0]
    # Anything we have left in the unused set should not be on the device, remove from longest to shortest
    for unused_dir in sorted(unused_android_set, reverse=True):
        target = os.path.join(ANDROID_ROOT, unused_dir)
        print("Deleting {} ...".format(target))
        subprocess.check_call(['adb', 'shell', 'rm', '-rf', target])
     

if __name__ == '__main__':

    # Validate directory and command line
    ok = False
    if not os.path.exists(MUSIC_ROOT):
        print("ERROR: Could not find music directory: " + MUSIC_ROOT)
    elif len(sys.argv) < 2:
        printUsage()
    else:
        exclusion_file = sys.argv[2]
        mode = None
        for m in modes:
            if sys.argv[1] == "-"+m["letter"]: 
                mode = m
        if mode is None:
            print("ERROR: Invalid mode")
        elif len(sys.argv) > (4 if mode["regex"] else 3):
            print("ERROR: Invalid number of arguments")
        elif mode["require_file"] and not os.path.exists(exclusion_file):
            print("ERROR: {} is not a valid exclusion exclusion_file".format(exclusion_file))
        else:
            ok = True
    if not ok:
        sys.exit(1)
       
    # Set up our directory set
    buildAllMusicDirectories()
    if os.path.exists(sys.argv[2]): 
        markExcludedUsingFile(exclusion_file)
    included = [d for d in music_dirs if d.included]
    excluded = [d for d in music_dirs if not d.included]
    total_size = sum([d.size for d in music_dirs if d.included])

    # Do the functions
    if mode["letter"] == "r":
        print("{} directories excluded".format(len(excluded)))
        print("{} directories included with a total size of {}".format(len(included), sizeofFmt(total_size)))
    elif mode["letter"] == "d" or mode["letter"] == "i":
        flipMusicDirectories(included if mode["letter"] == "d" else excluded, total_size, sys.argv[3] if len(sys.argv) == 4 else None)
        if input("Enter any character to confirm overwrite {}, or enter to skip:".format(exclusion_file)) != "":
            writeExcludedToFile(exclusion_file)
    elif mode["letter"] == "p":
        buildAllAndroidDirectories()
        syncMusicDirectories()
    