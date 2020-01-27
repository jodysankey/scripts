#!/usr/bin/python3
#========================================================
# Python script for linux or windows to retrieve the
# latest copies of all scripts from Subversion and install
# them on the local machine, filtering out those which are
# not relevant based on "AppliesTo" comments.
#
# This current version is going to need work to actually
# run on windows, and there is still work on the auth
# for bitbucket. Currently did a hacky copy of the jody
# cross-machine RSA key to root's home.
#========================================================
# Copyright Jody M Sankey 2010-2020
#========================================================
# $HeadURL$
# Last $Author: jody $
# $Revision: 720 $
# $Date: 2009-10-30 18:12:20 -0500 (Fri, 30 Oct 2009) $
#========================================================
# AppliesTo: linux, windows
# RemoveExtension: True
#========================================================


import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile


# Define machine of each type.
CLIENTS = {'vicki', 'debbie', 'katie', 'sasha', 'scarlett'}
SERVERS = {'oberon', 'umbriel'}

# Define a pattern for the repository location
REPO_PATTERN = 'git@bitbucket.org:jodysankey/{}.git'

# Define destination directories for each OS.
DESTINATIONS = {'windows':'c:/windows/scripts', 'linux':'/usr/local/scripts'}

# Define the magic header strings, split to prevent of finding them in this script.
APPLICABLE = "Applies" + "To:"
REMOVE_EXT = "Remove" + "Extension:"
PUBLIC_PERM = "Public" + "Permissions:"

# The file extensions that we consider moving.
EXTENSIONS = {'.py', '.sh', '.bat', '.pl'}


def _get_host_properties():
    """Returns a dictionary of properties that describe the current host."""
    properties = {'host': socket.gethostname().lower(),
                  'platform': 'windows' if sys.platform.lower().startswith('win') else 'linux'}
    if properties['host'] in CLIENTS:
        properties['type'] = 'client'
    elif properties['host'] in SERVERS:
        properties['type'] = 'server'
    return properties


def _get_reasons_to_apply_file(path, host_props):
    """Returns a list of reasons to keep the specified file based on matching the
    the "AppliesTo" lines in the specified file with the supplied properties."""
    host_prop_set = set(host_props.values())
    reasons = []
    open_file = open(path, 'r')
    try:
        for line in open_file:
            pos = line.find(APPLICABLE)
            if pos >= 0:
                prop_list = line[pos+len(APPLICABLE):].split(',')
                desired_prop_set = set([p.strip() for p in prop_list])
                matching_prop_set = desired_prop_set.intersection(host_prop_set)
                if not matching_prop_set:
                    # We must match something in *every* ApplyTo line
                    return []
                else:
                    reasons.append(matching_prop_set)
    except Exception as e:
        raise Exception("Error parsing {}: {}".format(path, str(e)))
    finally:
        open_file.close()
    return reasons


def _should_remove_extension(path):
    """Returns true iff there is a "RemoveExtension" line set to True in the specified file"""
    open_file = open(path, 'r')
    try:
        for line in open_file:
            pos = line.find(REMOVE_EXT)
            if pos >= 0 and line[pos+len(REMOVE_EXT):].strip().lower() == 'true':
                return True
    except Exception as ex:
        raise Exception("Error parsing {}: {}".format(path, str(ex)))
    finally:
        open_file.close()
    return False


def _should_make_public(path):
    """Returns true iff there is a "PublicPermissions" line set to True in the specified file"""
    open_file = open(path, 'r')
    try:
        for line in open_file:
            pos = line.find(PUBLIC_PERM)
            if pos >= 0 and line[pos+len(PUBLIC_PERM):].strip().lower() == 'true':
                return True
    except Exception as ex:
        raise Exception("Error parsing {}: {}".format(path, str(ex)))
    finally:
        open_file.close()
    return False


def _clone_repo(repo_name, target_dir):
    """Performs a shallow clone of the named git repo into a directory in target_dir."""
    repo_path = REPO_PATTERN.format(repo_name)
    target_path = os.path.join(target_dir, repo_name)
    if subprocess.call([ 'git', 'clone', '--depth=1', repo_path, target_path]) != 0:
        raise Exception(("Error cloning git repo. Maybe check permissions with "
            + "'git clone {} /tmp/test'").format(repo_path))


def _selectively_copy_files(source, dest, host_props):
    """Copies files from source to dest iff any AppliesTo lines match the supplied host
    properties, removing the file extension and adding permissions if the file requests it."""
    for root, dirs, files in os.walk(source):
        # Exclude hidden files and directories, in particular ".git".
        files = [f for f in files if not f[0] == '.']
        dirs[:] = [d for d in dirs if not d[0] == '.']
        for fn in files:
            fn_base, fn_ext = os.path.splitext(fn)
            if fn_ext not in EXTENSIONS:
                print(" Ignoring {} because extension {} doesn't match".format(fn, fn_ext))
                continue
            source_path = os.path.join(root, fn)
            reasons = _get_reasons_to_apply_file(source_path, host_props)
            if len(reasons) > 0:
                dest_fn = fn_base if _should_remove_extension(source_path) else fn
                dest_path = os.path.join(dest, dest_fn)
                print(" Keeping {} as {} because host matches {}".format(fn, dest_fn, reasons))
                try:
                    shutil.copy(source_path, dest_path)
                except Exception as ex:
                    raise Exception("Error copying {}: {}".format(source_path, str(ex)))

                if host_props['platform'] == 'linux':
                    # Git follow umask for public permissions. Explicitly add or remove based
                    # on whether the file says it wants them.
                    if _should_make_public(source_path):
                        subprocess.check_call(['chmod', 'o+rx', dest_path])
                    else:
                        subprocess.check_call(['chmod', 'o-rwx', dest_path])
            else:
                #print(" Discarding {} because not all properties matched".format(fn))
                pass


def main():
    """Clones script and python path repos and copies applicable files to the host."""
    if os.geteuid() != 0:
        print("Script needs to run as root to edit the scripts directory")
        return

    host_props = _get_host_properties()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Only copy the scripts that actually match this host.
        _clone_repo('scripts', tmpdir)
        _selectively_copy_files(
            os.path.join(tmpdir, 'scripts', 'src'),
            DESTINATIONS[host_props['platform']],
            host_props)

        # Copy the entire pythonpath filetree, overwriting the current one
        _clone_repo('pythonpath', tmpdir)
        pythonpath_target = os.path.join(DESTINATIONS[host_props['platform']], 'pythonpath')
        if os.path.exists(pythonpath_target):
            print(" Deleting existing PYTHONPATH at {}".format(pythonpath_target))
            shutil.rmtree(pythonpath_target)
        print(" Copying PYTHONPATH to {}".format(pythonpath_target))
        shutil.copytree(
            os.path.join(tmpdir, 'pythonpath', 'src'),
            pythonpath_target)


if __name__ == "__main__":
    main()
