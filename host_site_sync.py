#!/usr/bin/python3
#========================================================
# Python script for debian based linux distributions to
# determine or enforce synchronization of the local host
# with the software components defined by a central
# site definition
#========================================================
# Copyright Jody M Sankey 2010
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import os
import shutil
import socket
import subprocess
import sys

import sitemgt
from sitemgt.software import RepoApplication, NonRepoApplication, CmComponent
from sitemgt.paths import SITE_XML_FILE, CM_WORKING_DIR, getDeploymentFile
import svnauthorization


FAILURE_MODES = (('Missing', 'are not installed'),
                 ('PartiallyInstalled', 'have some but not all packages installed'),
                 ('NotConfigured', 'are present locally but not registered in CM'),
                 ('ModifiedLocally', 'are newer than the CM copy'),
                 ('OutOfDate', 'are older than the CM copy'),
                 ('Unknown', 'are in an indeterminate state'))


def prompt(text, options):
    """Prompts the user to enter one of a set of options (either in full or first char) and
    returns first char."""
    option_string = '({} or {}) '.format(', '.join(options[:-1]), options[-1])
    response = input(text + ' ' + option_string)
    while not response or response[0].lower() not in [op[0].lower() for op in options]:
        response = input('Invalid response ' + option_string)
    return response[0].lower()


def run_command(command):
    """Runs the specified command using the shell and prints the return code."""
    #print('<<{}>>'.format(command))
    ret_code = subprocess.call(command, shell=True)
    print('<<Returned {}>>'.format(ret_code))
    return ret_code


def add_svn_working_file(source_file, target):
    """Copies source file to target and adds to svn, making parent directories and adding
    them as necessary."""
    dirs = []
    d = os.path.dirname(target)
    while not os.path.exists(d):
        dirs.append(d)
        d = os.path.dirname(d)
    for d in reversed(dirs):
        os.mkdir(d)
        if run_command('svn {} add "{}"'.format(auth.subversionParams(), d)) != 0:
            return
    print('<<Copy {} to {}>>'.format(source_file, target))
    shutil.copy2(source_file, target)
    run_command('svn {} add "{}"'.format(auth.subversionParams(), target))
    commit_svn()


def update_svn_working_file(source_file, target):
    """Copies source file to target then prompts for a log message and performs a commit."""
    print('<<Copy {} to {}>>'.format(source_file, target))
    shutil.copyfile(source_file, target)
    commit_svn()


def commit_svn():
    """Prompts for a log message and performs a commit."""
    message = input('Please enter log message (or return to skip): ')
    run_command('svn {} commit {} -m "{}"'.format(auth.subversionParams(), CM_WORKING_DIR, message))


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
                elif resp == 'y':
                    run_command('aptitude purge {}'.format(pkg[0]))

    # For a better user experience, correct problems by failure mode
    for failure_mode in FAILURE_MODES:
        for name in sorted(host.expected_deployments.keys()):
            depl = host.expected_deployments[name]
            if depl.status == failure_mode[0]:
                # Exactly what we do depends on the component type and failure mode
                if isinstance(depl.component, RepoApplication):
                    if interactively_correct_repo_application(depl):
                        return
                elif isinstance(depl.component, NonRepoApplication):
                    # Can't actually ever fix a non-repo application
                    print(('{} is {}, but is a non-repo application, please correct '
                           'manually').format(name, depl.status))
                elif isinstance(depl.component, CmComponent):
                    if interactively_correct_cm_component(depl):
                        return


def interactively_correct_repo_application(depl):
    """Interacts with the user to try and correct configuration problems for the supplied
    deployment of a RepoApplication on host. Returns True if synchronization should be cancelled."""
    if not isinstance(depl.component, RepoApplication):
        raise Exception('interactive correction method called on wrong component type')

    # Don't attempt to do any repo applications outside of the default repository
    name = depl.component.name
    if hasattr(depl.component, 'repo_distribution'):
        print(('{} is {}, but in a non-standard repository, please correct '
               'manually').format(name, depl.status))
        return False

    for pkg in depl.missingPackages():
        resp = prompt('Install {} for component {}?'.format(pkg, name), ['Yes', 'No', 'Cancel'])
        if resp == 'c':
            return True
        elif resp == 'y':
            run_command('aptitude install {}'.format(pkg))
    return False


def interactively_correct_cm_component(depl):
    """Interacts with the user to try and correct configuration problems for the supplied
    deployment of a CM component on host. Returns True if synchronization should be cancelled."""
    if not isinstance(depl.component, CmComponent):
        raise Exception('interactive correction method called on wrong component type')

    # If the input contains errors we could be asked to deploy a component without
    # having a deployment path
    name = depl.component.name
    if not hasattr(depl, 'location'):
        print(('{} does not have a deployment path specified for this host, please '
               'correct manually').format(name))
        return False

    # Build the local and cm paths and correct by failure mode
    name = depl.component.name
    local_path = depl.location
    cm_working_path = os.path.join(CM_WORKING_DIR, depl.component.cm_location,
                                   depl.component.cm_filename)

    if depl.status == 'NotConfigured':
        resp = prompt('Add {} to CM?'.format(name), ['Yes', 'No', 'Cancel'])
        if resp == 'c':
            return True
        elif resp == 'y':
            add_svn_working_file(local_path, cm_working_path)
        return False
    if depl.status == 'Missing':
        resp = prompt('Use {} from CM?'.format(name), ['Yes', 'No', 'Cancel'])
        if resp == 'c':
            return True
        elif resp == 'y':
            print('<<Copy {} to {}>>'.format(cm_working_path, local_path))
            shutil.copy2(cm_working_path, local_path)
        return False
    # depl.status == 'ModifiedLocally' or depl.status == 'OutOfDate'
    while True:
        resp = prompt(('Use local file or repository file for {} ({} appears newer)?'
                      ).format(name, 'local' if depl.status == 'ModifiedLocally' else 'repo'),
                      ['Local', 'Repo', 'Diff', 'Skip', 'Cancel'])
        if resp == 'c':
            return True
        elif resp == 'd':
            print('DIFF (< is repository file, > is local file)')
            subprocess.call(['diff', cm_working_path, local_path])
        elif resp == 'l':
            update_svn_working_file(local_path, cm_working_path)
            return False
        elif resp == 'r':
            print('<<Copy {} to {}>>'.format(cm_working_path, local_path))
            shutil.copy2(cm_working_path, local_path)
            return False


def get_mode(argv):
    """Returns the mode based on the supplied command line arguments, or None if a mode could
    not be determined."""
    # TODO: Move over to argparse.
    if len(argv) == 2:
        if argv[1] in ['-t', '--text']:
            return 'text'
        elif argv[1] in ['-x', '--xml']:
            return 'xml'
        elif argv[1] in ['-i', '--interactive']:
            return 'interactive'
    return None


def print_usage():
    """Prints the correct syntax for the script to stdout."""
    version = sys.version_info
    print('\nSite management synchronization script (c)2011-2020 Jody Sankey')
    print('Currently running in Python v{}.{}.{}'.format(*version))
    print('\n Usage: {} MODE\n'.format(os.path.basename(sys.argv[0])))
    print(' Where MODE is one of:')
    print('   -i, --interactive  Interact with user to resolve errors')
    print('   -t, --text         Output errors in simple text format')
    print('   -x, --xml          Output XML to standard location')


def perform_sync(mode):
    """Attempts a sychronization using the supplied mode."""
    # Get local host name and determine if we have root privileges
    is_root = (os.geteuid() == 0)
    host = socket.gethostname().lower()

    # Won't be able to do interactive unless running as root
    if not is_root and mode == 'interactive':
        print("Interactive mode can't work effectively unless run as root, sorry")
        sys.exit()

    # Check we find the site definition
    if not os.path.exists(SITE_XML_FILE):
        print('ERROR: Could not find SiteDescription at {}'.format(SITE_XML_FILE))
        sys.exit(1)

    # Gather authorization for subversion
    auth = svnauthorization.SvnAuthorization()
    if not auth.readFromFile():
        if mode == 'interactive':
            auth.readFromTerminal()
        else:
            print('ERROR: Could not find a valid authorization in {}'.format(auth.filename))
            sys.exit(1)

    # Make sure the working copy of subversion is up to date with the repository
    if len(subprocess.check_output('svn {} stat {}'.format(
            auth.subversionParams(), CM_WORKING_DIR), shell=True)) > 1:
        print('ERROR: Working directory is not up to date with repository. Please correct '
              'before continuing.\n    (e.g. from oberon: svn commit /home/systems/site/svn)')
        sys.exit(1)

    # If root, fetch new package definitions
    if is_root:
        subprocess.call(['aptitude', 'update'], stdout=subprocess.DEVNULL)

    # Build a site description object and check we're in it
    site_desc = sitemgt.SiteDescription(SITE_XML_FILE)
    if host not in site_desc.hosts.keys():
        print('ERROR: Could not find host {} in site description')
        sys.exit(1)

    # Ask the host to gather its current status of all deployment objects
    site_desc.hosts[host].gatherDeploymentStatus(CM_WORKING_DIR)

    # Take the next step based on mode
    if mode == 'text':
        output_to_text(site_desc.hosts[host])
    elif mode == 'xml':
        output_to_xml(site_desc.hosts[host])
    elif mode == 'interactive':
        interactively_correct(site_desc.hosts[host])


if __name__ == '__main__':
    MODE = get_mode(sys.argv)
    if MODE is None:
        print_usage()
        sys.exit()
    perform_sync(MODE)
