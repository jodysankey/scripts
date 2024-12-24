#!/usr/bin/python3

"""Script for debian based linux distributions to determine or enforce
synchronization of the local host with the software components defined
by a central site definition."""

#========================================================
# Copyright Jody M Sankey 2010-2020
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import argparse
import os
import shutil
import socket
import subprocess
from subprocess import DEVNULL
import sys

import git_validation
import sitemgt
from sitemgt.software import RepoApplication, NonRepoApplication, CmComponent
from sitemgt.paths import SITE_XML_FILE, CM_WORKING_DIR, CM_UPSTREAM_DIR



FAILURE_MODES = (('Missing', 'are not installed'),
                 ('PartiallyInstalled', 'have some but not all packages installed'),
                 ('NotConfigured', 'are present locally but not registered in CM'),
                 ('ModifiedLocally', 'are newer than the CM copy'),
                 ('OutOfDate', 'are older than the CM copy'),
                 ('Unknown', 'are in an indeterminate state'))

CM_OWNER_UID = os.stat(os.path.join(CM_WORKING_DIR, '.git')).st_uid


class InteractiveStatus(object):
    """Simple data object to track the overall status of an interactive run."""
    def __init__(self):
        self.cm_changes = 0
        self.cancelled = False


def prompt(text, options):
    """Prompts the user to enter one of a set of options (either in full or first char) and
    returns first char."""
    option_string = '({} or {}) '.format(', '.join(options[:-1]), options[-1])
    response = input(text + ' ' + option_string)
    while not response or response[0].lower() not in [op[0].lower() for op in options]:
        response = input('Invalid response ' + option_string)
    return response[0].lower()


def run_command(command, cwd=None, uid=None):
    """Runs the specified command, optionally in the specified working directory and as the
    specified user, and returns True on success."""
    #print('<<{}>>'.format(command))

    def run_as_user():
        """Subprocess delegation function."""
        os.setgid(uid)
        os.setuid(uid)

    ret_code = (subprocess.call(command, cwd=cwd, preexec_fn=run_as_user, stderr=DEVNULL)
                if uid else subprocess.call(command, cwd=cwd, stderr=DEVNULL))
    if ret_code != 0:
        print('<<Error: {} returned {}>>'.format(' '.join(command), ret_code))
    return ret_code == 0


def add_cm_working_file(source_file, target):
    """Copies source file to target and stages in git, creating parent directories as necessary.
    Returns True on success."""
    directory = os.path.dirname(target)
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
        print('<<Copy2 {} to {}>>'.format(source_file, target))
        shutil.copy2(source_file, target)
    except OSError as ex:
        print('Exception copying file: {}'.format(ex))
        return False
    return run_command(['git', 'add', target], cwd=CM_WORKING_DIR, uid=CM_OWNER_UID)


def update_cm_working_file(source_file, target):
    """Copies source file to target and stages in git. Returns True on success."""
    print('<<Copy {} to {}>>'.format(source_file, target))
    try:
        shutil.copyfile(source_file, target)
    except OSError as ex:
        print('Exception copying file: {}'.format(ex))
        return False
    return run_command(['git', 'add', target], cwd=CM_WORKING_DIR, uid=CM_OWNER_UID)


def commit_cm_changes(status):
    """Prompts for a log message and performs a commit if the supplied status made cm changes."""
    if status.cm_changes:
        message = input(('Please enter commit message for the {} staged files (or return to skip):'
                         ' ').format(status.cm_changes))
        if message:
            if run_command(['git', 'commit', '-m', message], cwd=CM_WORKING_DIR, uid=CM_OWNER_UID):
                print('Now please push this commit to the upstream on the local server')


def output_to_xml(host):
    """Writes the state of all components in the provided host to a standard file location
    as XML."""
    host.saveDeploymentStatusToXmlFile()


def output_to_text(host):
    """Writes the state of abnormal components in the provided host to stdout as text."""
    if host.upgradable_packages:
        print('The following {} packages are upgradable:'.format(len(host.upgradable_packages)))
        for pkg in host.upgradable_packages:
            print('\t{} := {}'.format(pkg[0], pkg[1]))
    if host.unexpected_packages:
        print('The following {} packages are orphan installations but not expected:'.format(
            len(host.unexpected_packages)))
        for pkg in host.unexpected_packages:
            print('\t{} := {}'.format(pkg[0], pkg[1]))

    for failure_mode in FAILURE_MODES:
        problems = []
        for name in sorted(host.expected_deployments.keys()):
            depl = host.expected_deployments[name]
            if depl.status == failure_mode[0]:
                problem = name
                if hasattr(depl, 'location'):
                    problem += ' @ ' + depl.location
                if hasattr(depl, 'error'):
                    problem += ' ; ' + depl.error
                if failure_mode == 'PartiallyInstalled':
                    problem += ' ' + str(depl.missingPackages)
                problems.append(problem)
        if problems:
            print('The following {} components {}:'.format(len(problems), failure_mode[1]))
            for problem in problems:
                print('\t' + problem)


def interactively_correct(host):
    """Interacts with the user to try and correct component configuration problems with host."""
    if host.upgradable_packages:
        print(('{} packages are upgradable, and should be upgraded using a standard package '
               'management tool').format(len(host.upgradable_packages)))

    if host.unexpected_packages:
        if prompt(('{} packages are unexpected orphan installations. Would you like to review '
                   'these?').format(len(host.unexpected_packages)), ['Yes', 'No']) == 'y':
            for pkg in host.unexpected_packages:
                resp = prompt('Purge {} ({})?'.format(pkg[0], pkg[1]), ['Yes', 'No', 'Cancel'])
                if resp == 'c':
                    return
                if resp == 'y':
                    run_command(['aptitude', 'purge', pkg[0]])

    # For a better user experience, correct problems by failure mode
    status = InteractiveStatus()
    for failure_mode in FAILURE_MODES:
        for name in sorted(host.expected_deployments.keys()):
            depl = host.expected_deployments[name]
            if depl.status == failure_mode[0]:
                # Exactly what we do depends on the component type and failure mode
                if isinstance(depl.component, RepoApplication):
                    correct_repo_application(depl, status)
                elif isinstance(depl.component, NonRepoApplication):
                    print(('{} is {}, but is a non-repo application, please correct '
                           'manually').format(name, depl.status))
                elif isinstance(depl.component, CmComponent):
                    correct_cm_component(depl, status)
                if status.cancelled:
                    commit_cm_changes(status)
                    return
    commit_cm_changes(status)


def correct_repo_application(depl, status):
    """Interacts with the user to try and correct configuration problems for the supplied
    deployment of a RepoApplication on host. Updates the supplied InteractiveStatus if needed."""
    if not isinstance(depl.component, RepoApplication):
        raise Exception('Correction method called on wrong component type')

    # Don't attempt to do any repo applications outside of the default repository.
    name = depl.component.name
    if hasattr(depl.component, 'repo_distribution'):
        print(('{} is {}, but in a non-standard repository, please correct '
               'manually').format(name, depl.status))
        return

    for pkg in depl.missingPackages():
        resp = prompt('Install {} for component {}?'.format(pkg, name), ['Yes', 'No', 'Cancel'])
        if resp == 'c':
            status.cancelled = True
        elif resp == 'y':
            run_command(['aptitude', '-y', 'install', pkg])


def correct_cm_component(depl, status):
    """Interacts with the user to try and correct configuration problems for the supplied
    deployment of a CM component on host. Updates the supplied InteractiveStatus if needed."""
    if not isinstance(depl.component, CmComponent):
        raise Exception('Correction method called on wrong component type')

    # If the input contains errors we could be asked to deploy a component without
    # having a deployment path
    name = depl.component.name
    if not hasattr(depl, 'location'):
        print(('{} does not have a deployment path specified for this host, please '
               'correct manually').format(name))
        return

    # Build the local and cm paths and correct by failure mode
    name = depl.component.name
    local_path = depl.location
    cm_working_path = os.path.join(CM_WORKING_DIR, depl.component.cm_location,
                                   depl.component.cm_filename)

    if depl.status == 'NotConfigured':
        resp = prompt('Add {} to CM?'.format(name), ['Yes', 'No', 'Cancel'])
        if resp == 'c':
            status.cancelled = True
        elif resp == 'y':
            if add_cm_working_file(local_path, cm_working_path):
                status.cm_changes += 1
    elif depl.status == 'Missing':
        resp = prompt('Use {} from CM?'.format(name), ['Yes', 'No', 'Cancel'])
        if resp == 'c':
            status.cancelled = True
        elif resp == 'y':
            if not os.path.exists(local_path):
                print('<<Creating {}>>'.format(local_path))
                os.makedirs(local_path)
            print('<<Copy2 {} to {}>>'.format(cm_working_path, local_path))
            shutil.copy2(cm_working_path, local_path)
    elif depl.status == 'ModifiedLocally' or depl.status == 'OutOfDate':
        while True:
            resp = prompt(('Use local file or repository file for {} ({} appears newer)?'
                          ).format(name, 'local' if depl.status == 'ModifiedLocally' else 'repo'),
                          ['Local', 'Repo', 'Diff', 'Skip', 'Cancel'])
            if resp == 'c':
                status.cancelled = True
                return
            if resp == 's':
                return
            if resp == 'l':
                if update_cm_working_file(local_path, cm_working_path):
                    status.cm_changes += 1
                return
            if resp == 'r':
                print('<<Copy {} to {}>>'.format(cm_working_path, local_path))
                shutil.copy2(cm_working_path, local_path)
                return
            if resp == 'd':
                print('DIFF (< is repository file, > is local file)')
                subprocess.call(['diff', cm_working_path, local_path])


def create_parser():
    """Creates the definition of the expected command line flags."""
    parser = argparse.ArgumentParser(
        description='Site management synchronization script.',
        epilog='Copyright Jody Sankey 2011-2020')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-i', '--interactive', action='store_true',
                       help="Interact with the user to resolve errors.")
    group.add_argument('-t', '--text', action='store_true',
                       help="Output errors in simple text format")
    group.add_argument('-x', '--xml', action='store_true',
                       help="Output XML to standard location")
    return parser


def perform_sync(parsed_args):
    """Attempts a sychronization using the supplied mode."""
    # Get local host name and determine if we have root privileges
    is_root = (os.geteuid() == 0)
    host = socket.gethostname().lower()

    # Won't be able to do interactive unless running as root
    if not is_root and parsed_args.interactive:
        print("Interactive mode can't work effectively unless run as root, sorry")
        sys.exit()

    # Check we find the site definition
    if not os.path.exists(SITE_XML_FILE):
        print('ERROR: Could not find SiteDescription at {}'.format(SITE_XML_FILE))
        sys.exit(1)

    # Check that the working site matches the master
    validation = git_validation.check_repo(CM_WORKING_DIR, CM_UPSTREAM_DIR)
    if not validation['is_valid']:
        print('ERROR: {} is not a valid git repo ({})'.format(CM_WORKING_DIR,
                                                              validation['problem']))
        sys.exit(1)
    if not validation['is_synchronized']:
        print('ERROR: {} is not in sync with upstream ({})'.format(CM_WORKING_DIR,
                                                                   validation['problem']))
        if parsed_args.interactive:
            resp = prompt('Continue using the unverified working directory?', ['Yes', 'No'])
            if resp == 'n':
                sys.exit(2)
        else:
            sys.exit(1)

    # If root, fetch new package definitions
    if is_root:
        subprocess.call(['aptitude', 'update'], stdout=DEVNULL)

    # Build a site description object and check we're in it
    site_desc = sitemgt.SiteDescription(SITE_XML_FILE)
    if host not in site_desc.hosts.keys():
        print('ERROR: Could not find host {} in site description')
        sys.exit(1)

    # Ask the host to gather its current status of all deployment objects
    site_desc.hosts[host].gatherDeploymentStatus(CM_WORKING_DIR)

    # Take the next step based on mode
    if parsed_args.text:
        output_to_text(site_desc.hosts[host])
    elif parsed_args.xml:
        output_to_xml(site_desc.hosts[host])
    else:
        interactively_correct(site_desc.hosts[host])


if __name__ == '__main__':
    perform_sync(create_parser().parse_args())
