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

MODES = [{"letter":"r", "description":"Report total size of configuration",
          "regex":False, "require_file":False},
         {"letter":"i", "description":"Increase size of a configuration, by regex or interactively",
          "regex":True, "require_file":True},
         {"letter":"d", "description":"Decrease size of a configuration, by regex or interactively",
          "regex":True, "require_file":False},
         {"letter":"q", "description":"Query current contents of android device",
          "regex":False, "require_file":True},
         {"letter":"p", "description":"Push configuration to an android device",
          "regex":False, "require_file":True}, ]

class MusicDirectory:
    """Define a local directory containing a set of music files"""
    def __init__(self, rel_dir):
        self.rel_dir = rel_dir
        self.included = True

    def __str__(self):
        return self.rel_dir

    @property
    def abs_dir(self):
        """The absolute path of this directory."""
        return os.path.join(MUSIC_ROOT, self.rel_dir)

    @property
    def abs_files(self):
        """A list of the absolute file paths in this directory."""
        return [(os.path.join(self.abs_dir, f)) for f in os.listdir(self.abs_dir)
                if os.path.isfile(os.path.join(self.abs_dir, f))]

    @property
    def size(self):
        """The total size of all files in this directory."""
        return sum([os.path.getsize(f) for f in self.abs_files])


def sanitize(inp):
    """Removes the special characters that ADB fails to handle even with escaping."""
    return inp.replace('"', '').replace('?', '').replace(':', '')


def fmt_bytes(num):
    """Returns a formatted string of num bytes."""
    for units in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "{:3.1f} {}".format(num, units)
        num /= 1024.0
    return "{:3.1f} PB".format(num)


def build_all_music_directories():
    """Create objects for each music directory in MUSIC_ROOT and add to the global list"""
    global music_dirs
    music_dirs = []
    for root, dirs, files in os.walk(MUSIC_ROOT):
        # Only process leaf directories with files
        if files and not dirs and not os.path.basename(root).startswith('.'):
            music_dirs.append(MusicDirectory(os.path.relpath(root, MUSIC_ROOT)))
        elif dirs:
            dirs.sort()


def build_all_android_directories():
    """Create strings for each music directory on the Android device and add to the global list"""
    global android_dirs
    android_dirs = []
    # We use a BFS algorithm
    unvisited = [""]
    while len(unvisited) > 0:
        current = unvisited.pop(0)
        current_abs = os.path.join(ANDROID_ROOT, current)
        contents = subprocess.check_output(
            ['adb', 'shell', 'ls', '-F', '"{}"'.format(current_abs)]
            ).decode("utf-8").split("\n")
        unvisited.extend([os.path.join(current, ln.strip()[:-1])
                          for ln in contents if ln.endswith("/")])
        if current != "": android_dirs.append(current)


def mark_excluded_using_file(exclusion_file_name):
    """Set each music_dir present in the supplied exclusion_file to exclude."""
    music_dict = {d.rel_dir: d for d in music_dirs}
    exclusion_file = open(exclusion_file_name, mode="r")
    for line in [l.strip() for l in exclusion_file]:
        if line not in music_dict:
            print("WARNING: Ignoring unknown exclusion directory " + line)
        else:
            music_dict[line].included = False
    exclusion_file.close()


def write_excluded_to_file(exclusion_file_name):
    """Write a exclusion_file containing the names of all directories that are marked as excluded"""
    exclusion_file = open(exclusion_file_name, mode="w")
    for music_dir in music_dirs:
        if not music_dir.included: exclusion_file.write(music_dir.rel_dir + "\n")
    exclusion_file.close()


def print_usage():
    """Prints syntax help to stdout."""
    print("Android music library subconfiguration manager, Jody Sankey 2013")
    print("  Usage:  " + os.path.basename(__file__) + " <mode> <exclusion_file> [regex]")
    print("  Where <mode> is one of:")
    for mode in MODES:
        print("    -{}  {}".format(mode["letter"], mode["description"]))


def __get_skip_select_quit(prompt):
    """Repeatedly prompts the user until they return a valid selection from skip/select/quit."""
    while True:
        response = input(prompt + " [enter to skip, 's' to select, 'q' to quit]")
        if response == "":
            return "skip"
        if response == "s":
            return "select"
        if response == "q":
            return "quit"


def __add_remove(base, delta, adding):
    """Add or remove delta from base."""
    if adding:
        return base + delta
    return base - delta


def flip_music_directories(dirs, total_size, regex):
    """Interacts with the user (or uses a regex if provided) to toggle inclusion
    state of music directories."""
    adding = (len(dirs) > 0 and not dirs[0].included)
    count = 0
    size_change = 0
    for d in dirs:
        if regex is None:
            action = __get_skip_select_quit("Current size {:7s}, {} {} ({})?".format(
                fmt_bytes(__add_remove(total_size, size_change, adding)),
                "add" if adding else "remove", d.rel_dir, fmt_bytes(d.size)))
            if action == "quit":
                break
            if action == "select":
                d.included = not d.included
                count += 1
                size_change += d.size
        elif re.search(regex, d.rel_dir):
            print("{}ing {} ({})".format("Add" if adding else "Remov",
                                         d.rel_dir, fmt_bytes(d.size)))
            d.included = not d.included
            count += 1
            size_change += d.size
    print("{} {} directories, {} {}, for a new total size of {}".format(
        "Added" if adding else "Removed",
        count,
        "adding" if adding else "saving",
        fmt_bytes(size_change),
        fmt_bytes(__add_remove(total_size, size_change, adding))))


def sync_music_directories():
    """Pushes a set of music dirs to an Android device where the directory is absent, and
    removes additional directories. Directory contents are not checked for consistency"""
    unused_android_set = set(android_dirs)
    for music_dir in (x for x in music_dirs if x.included):
        if sanitize(music_dir.rel_dir) not in unused_android_set:
            dest_dir = os.path.join(ANDROID_ROOT, sanitize(music_dir.rel_dir))
            print("Creating {} ...".format(dest_dir))
            subprocess.check_call(['adb', 'shell', 'mkdir', '-p', r'"{}"'.format(dest_dir)])
            for f in music_dir.abs_files:
                dest_file = sanitize(os.path.join(dest_dir, os.path.relpath(f, music_dir.abs_dir)))
                #print("  Copying {} to {} ...   ".format(f, dest_file))
                sys.stdout.flush()
                subprocess.check_call(['adb', 'push', f, dest_file])
        used_dir = sanitize(music_dir.rel_dir)
        while used_dir != '':
            unused_android_set.discard(used_dir)
            used_dir = os.path.split(used_dir)[0]
    # Anything we have left in the unused set should not be on the device,
    # remove from longest to shortest
    for unused_dir in sorted(unused_android_set, reverse=True):
        target = os.path.join(ANDROID_ROOT, unused_dir)
        print("Deleting {} ...".format(target))
        subprocess.check_call(['adb', 'shell', 'rm', '-rf', target])


def validate_inputs():
    """Validates the music directory and command lines, printing informative errors
    and exiting on failure or returning mode and exclusion file on success."""
    if not os.path.exists(MUSIC_ROOT):
        print("ERROR: Could not find music directory: " + MUSIC_ROOT)
        sys.exit(1)
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    exclusion_file = sys.argv[2]
    selected_mode = None
    for mode in MODES:
        if sys.argv[1] == "-"+mode["letter"]:
            selected_mode = mode
    if selected_mode is None:
        print("ERROR: Invalid mode")
    elif len(sys.argv) > (4 if selected_mode["regex"] else 3):
        print("ERROR: Invalid number of arguments")
    elif selected_mode["require_file"] and not os.path.exists(exclusion_file):
        print("ERROR: {} is not a valid exclusion exclusion_file".format(exclusion_file))
    else:
        return (selected_mode, exclusion_file)
    sys.exit(1)


def main():
    """Runs the script using command line inputs."""
    (mode, exclusion_file) = validate_inputs()

    # Set up our directory set
    build_all_music_directories()
    if os.path.exists(sys.argv[2]):
        mark_excluded_using_file(exclusion_file)
    included = [d for d in music_dirs if d.included]
    excluded = [d for d in music_dirs if not d.included]
    total_size = sum([d.size for d in music_dirs if d.included])

    # Do the functions
    if mode["letter"] == "r":
        print("{} directories excluded".format(len(excluded)))
        print("{} directories included with a total size of {}".format(
            len(included), fmt_bytes(total_size)))
    elif mode["letter"] == "d" or mode["letter"] == "i":
        flip_music_directories(included if mode["letter"] == "d" else excluded,
                               total_size,
                               sys.argv[3] if len(sys.argv) == 4 else None)
        if input("Enter any character to confirm overwrite {}, or enter to skip:".format(
                exclusion_file)) != "":
            write_excluded_to_file(exclusion_file)
    elif mode["letter"] == "p":
        build_all_android_directories()
        sync_music_directories()


if __name__ == '__main__':
    main()
