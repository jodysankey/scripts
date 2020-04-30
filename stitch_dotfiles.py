#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""Script for linux to build links between configuation files in the
user's standard home directory locations and a git clone."""

#========================================================
# Copyright Jody M Sankey 2020
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import argparse
import filecmp
import os
from os import path
import pwd
import shutil
import subprocess
import sys


# Map from username to upstream repo
REMOTE_URLS = {'jody': {
                  'https': 'https://github.com/jodysankey/dotfiles.git',
                  'ssh': 'git@github.com:jodysankey/dotfiles.git',
              }}

# Path (relative to the user's home directory) for the git clone
CLONE_PATH = 'git-dotfiles'

# Paths to exclude from the repo walk
EXCLUDES = {'.git', 'README.md'}


class Colors(object):
    """A collection of Linux terminal formatting strings."""
    BOLD = '\033[1m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'


class Repo(object):
    """A representation of a git repository on local disk and an associated remote."""

    def __init__(self, location, remote_https, remote_ssh):
        self.location = location
        self.remote_https = remote_https
        self.remote_ssh = remote_ssh

    def is_valid(self):
        """Returns a tuple of a boolean that is True iff location is a valid git repo pointing to
        the desired remote (either over https or ssh) and a string describing the failure mode,
        if any."""
        if not path.exists(self.location):
            return (False, 'Path does not exist')
        elif not path.isdir(self.location):
            return (False, 'Path is not a directory')
        elif subprocess.check_output(['git', 'rev-parse', '--is-inside-work-tree'],
                                     cwd=self.location).decode('utf-8').strip() != 'true':
            return (False, 'Path is not a git working directory')
        elif (subprocess.check_output(['git', 'remote', 'get-url', 'origin', '--push'],
                                     cwd=self.location).decode('utf-8').strip()
                                     not in [self.remote_https, self.remote_ssh]):
            return (False, 'Path is not using the expected remote repository')
        else:
            return (True, 'Path is a valid clone of the expected repository')

    def create(self):
        """Performs a clone of the named git repo into a directory in target_dir."""
        if path.exists(self.location):
            raise Exception('Repo path already exists, cannot create')
        # Initially try to clone with the more functional but authenticated ssh,
        # if that fails drop back to https.
        if subprocess.call(['git', 'clone', self.remote_ssh, self.location]) == 0:
            return
        if subprocess.call(['git', 'clone', self.remote_https, self.location]) != 0:
            raise Exception(("Error cloning git repo on both ssh and https. Maybe check permissions"
                             "with\n'git clone {} /tmp/test' or 'git clone {} /tmp/test'"
                             ).format(self.remote_ssh, self.remote_https))

    def files(self):
        """Returns a list of the relative paths to be linked in the repo."""
        ret = []
        for root, dirs, files in os.walk(self.location):
            # Exclude hidden files and directories, in particular ".git".
            dirs[:] = [d for d in dirs if d not in EXCLUDES]
            files = [f for f in files if f not in EXCLUDES]
            for f in files:
                ret.append(path.relpath(path.join(root, f), self.location))
        return ret

    def has_unstaged_changes(self):
        """Returns true if the local repo has unstaged changes."""
        return len(subprocess.check_output(['git', 'status', '--porcelain'],
                                           cwd=self.location).decode('utf-8').strip()) > 0

    def rebase(self):
        """Perform a rebase on the local repo."""
        subprocess.check_output(['git', 'pull', '--rebase'], cwd=self.location)


class Link(object):
    """A representation of a symlink that can manage its creation/deletion."""

    def __init__(self, location, target):
        self.location = location
        self.target = target

    def __str__(self):
        return "'{}' => '{}'".format(self.location, self.target)

    def is_valid(self):
        """Returns a tuple of a boolean that is True iff path is a valid link pointing to the
        intended target and a string describing the failure mode, if any."""
        if not path.exists(self.location):
            return (False, '{} does not exist'.format(self.location))
        elif not path.islink(self.location):
            return (False, '{} is not a symlink'.format(self.location))
        elif os.readlink(self.location) != self.target:
            return (False, '{} points to {}, not {}'.format(
                self.location, os.readlink(self.location), self.target))
        else:
            return (True, 'Location is a valid link to the correct location')

    def create(self):
        """Physically creates the symlink, replacing any existing file."""
        if path.exists(self.location):
            os.remove(self.location)
        os.symlink(self.target, self.location)

    def delete(self):
        """Physically deletes the symlink"""
        if path.lexists(self.location):
            if path.isdir(self.location):
                shutil.rmtree(self.location)
            else:
                os.remove(self.location)


def _parse_args():
    """Defines and parses command line arguments."""
    parser = argparse.ArgumentParser(
        description='''Maintains a set of symlinks in the current user's home directory to a git
                    repository containing configuration files.''',
        epilog='''Copyright 2020 Jody Sankey, published under the MIT licence''')
    parser.add_argument('mode', help='mode of operation', choices=['auto', 'manual', 'status'])
    parser.add_argument('-v', '--verbose', help='increase output verbosity', action='store_true')
    return parser.parse_args()


def _user_approval(action, yes_fn=None, no_fn=None):
    """Returns true iff the user approves an action by typing y"""
    while True:
        response = input(Colors.BLUE + action + '? (y/n) ' + Colors.ENDC)
        if response.lower() == 'y':
            if yes_fn:
                yes_fn()
            return True
        elif response.lower() == 'n':
            if no_fn:
                no_fn()
            return False

def _fatal(message, retcode):
    """Prints the message in red then exits with the supplied error code"""
    print(Colors.RED + message + Colors.ENDC)
    sys.exit(retcode)

def _warn(message):
    """Prints the message in yellow"""
    print(Colors.YELLOW + message + Colors.ENDC)

def _info(message):
    """Prints the message in green"""
    print(Colors.GREEN + message + Colors.ENDC)

def _act(message):
    """Prints the message in white"""
    print(Colors.BOLD + message + Colors.ENDC)


def _validate_repo(repo, args):
    """Ensures the supplied `repo` object is valid and up to date, according to the execution
    settings supplied in `args`."""
    if not path.exists(repo.location):
        if args.mode == 'status':
            _fatal('git dir at {} not present, no further checks possible'.format(repo.location), 0)
        else:
            # Even in auto mode ask to create the clone directory. Its a big deal.
            _user_approval('Clone {} to {}'.format(repo.remote_git, repo.location),
                           no_fn=lambda: sys.exit(0))
    repo_valid = repo.is_valid()
    if not repo_valid[0]:
        _fatal('git clone at {} not valid: {}'.format(repo.location, repo_valid[1]), 3)
    elif args.verbose:
        _info('git clone at {} is valid'.format(repo.location))
    if repo.has_unstaged_changes():
        if args.mode != 'status':
            _warn('git clone at {} has unstaged changes'.format(repo.location))
        else:
            _warn('git clone at {} has unstaged changes, cannot rebase'.format(repo.location))
    elif args.mode != 'status':
        _act('Rebasing git clone at {}'.format(repo.location))
        repo.rebase()


def _restitch_link(link, args):
    """Reports and if necessary corrects the supplied `link` object according to the execution
    settings supplied in `args`. Returns true if the git repo was modified."""
    if not path.lexists(link.location):
        # The path in the location direction does not exist, create it if we can.
        if args.mode == 'status':
            _warn('File does not exist: {}'.format(link.location))
        elif args.mode == 'auto':
            _act('Creating link {}'.format(link))
            link.create()
        elif args.mode == 'manual':
            _user_approval('Create link {}'.format(link), yes_fn=link.create())
        return False

    if path.islink(link.location):
        # The location is a symlink, check its to the right place. If not we don't attempt a fix.
        link_valid = link.is_valid()
        if link_valid[0]:
            if args.verbose:
                _info('Valid link {}'.format(link))
        else:
            _warn('Existing link is invalid: {}'.format(link_valid[1]))
        return False

    if filecmp.cmp(link.location, link.target, shallow=False):
        # The location is an existing file with the same content as the thing it should link to.
        if args.mode == 'status':
            _warn('File exists with same content as intended target: {}'.format(link.location))
        elif args.mode == 'auto':
            _act('Replacing {} with link to identical {}'.format(link.location, link.target))
            link.create()
        elif args.mode == 'manual':
            _user_approval('Replace {} with link to identical {}'.format(
                link.location, link.target), yes_fn=link.create())
        return False

    # The location is an existing file different content to the thing it should link to.
    if args.mode == 'status':
        _warn('File exists with different content to intended target: {}'.format(link.location))
    elif args.mode == 'auto':
        _act('Updating git clone with contents of {}'.format(link.location))
        shutil.copyfile(link.location, link.target)
        _act('Replacing {} with link to {}'.format(link.location, link.target))
        link.create()
        return True
    elif args.mode == 'manual':
        if _user_approval('Replace {} with link to modified {}'.format(link.location, link.target)):
            shutil.copyfile(link.location, link.target)
            link.create()
            return True
    return False


def main(args):
    """Sets or checks all home links correctly for the current user."""

    # Run some basic checks and gather paths.
    user = pwd.getpwuid(os.geteuid())[0]
    user_home = path.join('/home', user)
    if not path.exists(user_home):
        _fatal('{} does not have a home directory, cannot stitch dotfiles'.format(user), 1)
    if user not in REMOTE_URLS:
        _fatal('{} not listed in REMOTE_URLS, cannot determine remote url'.format(user), 2)
    user_clone = path.join(user_home, CLONE_PATH)

    # Check the git clone is in a healthy state and pointing to the right remote.
    repo = Repo(user_clone, REMOTE_URLS[user]['https'], REMOTE_URLS[user]['ssh'])
    _validate_repo(repo, args)

    # Walk through each link in the repo and action it.
    modified_clone = False
    for rel_path in repo.files():
        link = Link(os.path.join(user_home, rel_path), os.path.join(user_clone, rel_path))
        modified_clone |= _restitch_link(link, args)

    if modified_clone:
        print('One or more files were updated in the local git repo to reflect the original')
        print('that was replaced by a link to git. You probably want to compare the diff')
        print('and either discard the changes or commit them')
        print('  git checkout -- <filename>')
        print('  git add -i; git commit; git push')


if __name__ == '__main__':
    main(_parse_args())
