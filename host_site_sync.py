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

import svnauthorization
import sitemgt

from sitemgt.software import RepoApplication, NonRepoApplication, CmComponent
from sitemgt.paths import SITE_XML_FILE, CM_WORKING_DIR, getDeploymentFile

import os
import subprocess
import sys
import socket
import shutil


auth = svnauthorization.SvnAuthorization()


def prompt(text, options):
    """Prompts the user to enter one of a set of options (either in full or first char) and returns first char"""
    option_string = "({} or {}) ".format(', '.join(options[:-1]),options[-1])
    response = input(text + " " + option_string)
    while len(response)==0 or response[0].lower() not in [op[0].lower() for op in options]:
        response = input("Invalid response " + option_string)
    return response[0].lower()


def runCommand(command):
    """Runs the specified command using the shell and prints the return code"""
    #print("<<{}>>".format(command))
    ret_code = subprocess.call(command,shell=True)
    print("<<Returned {}>>".format(ret_code))
    return ret_code


def addSvnWorkingFile(source_file,target):
    """Copies source file to target and adds to svn, making parent directories and adding them as necessary"""
    dirs = []
    d = os.path.dirname(target)
    while not os.path.exists(d):
        dirs.append(d)
        d = os.path.dirname(d)
    for d in reversed(dirs):
        os.mkdir(d)
        if runCommand('svn {} add "{}"'.format(auth.subversionParams(),d)) != 0:
            return
    print("<<Copy {} to {}>>".format(source_file,target))
    shutil.copy2(source_file, target)
    runCommand('svn {} add "{}"'.format(auth.subversionParams(),target))
    commitSvn()


def updateSvnWorkingFile(source_file,target):
    """Copies source file to target then prompts for a log message and performs a commit"""
    print("<<Copy {} to {}>>".format(source_file,target))
    shutil.copyfile(source_file, target)
    commitSvn()


def commitSvn():
    """Prompts for a log message and performs a commit"""
    message = input("Please enter log message (or return to skip): ")
    runCommand('svn {} commit {} -m "{}"'.format(auth.subversionParams(), CM_WORKING_DIR, message))


def outputToXml(host):
    """Writes the state of all components in the provided host to a standard file location as XML"""
    host.saveDeploymentStatusToXmlFile()


def outputToText(host):
    """Writes the state of abnormal components in the provided host to stdout as text"""

    if len(host.upgradable_packages)>0:
        print("The following {} packages are upgradable:".format(len(host.upgradable_packages)))
        for t in host.upgradable_packages:
            print("\t{} := {}".format(t[0],t[1]))
    if len(host.unexpected_packages)>0:
        print("The following {} packages are orphan installations but not expected:".format(len(host.unexpected_packages)))
        for t in host.unexpected_packages:
            print("\t{} := {}".format(t[0],t[1]))

    for failure_mode in (("Missing","are not installed"),
                         ("PartiallyInstalled","have some but not all packages installed"),
                         ("NotConfigured","are present locally but not registered in CM"),
                         ("ModifiedLocally","are newer than the CM copy"),
                         ("OutOfDate","are older than the CM copy"),
                         ("Unknown","are in an indeterminate state")):
        problems = []
        for name in sorted(host.expected_deployments.keys()):
            depl = host.expected_deployments[name]
            if depl.status == failure_mode[0]:
                problem = name
                if hasattr(depl,'location'):
                    problem += " @ " + depl.location
                if hasattr(depl,'error'):
                    problem += " ; " + depl.error
                if failure_mode == 'PartiallyInstalled':
                    problem += " " + str(depl.missingPackages)
                problems.append(problem)

        if len(problems)>0:
            print("The following {} components {}:".format(len(problems),failure_mode[1]))
            for p in problems:
                print("\t" + p)


def interactivelyCorrect(host):
    """Interacts with the user to try and correct component configuration problems with host"""

    if len(host.upgradable_packages)>0:
        print("{} packages are upgradable, and should be upgraded using a standard package management tool".format(len(host.upgradable_packages)))

    if len(host.unexpected_packages)>0:
        if prompt("{} packages are unexpected orphan installations. Would you like to review these?".format(len(host.unexpected_packages)),['Yes','No']) == 'y':
            for t in host.unexpected_packages:
                resp = prompt("Purge {} ({})?".format(t[0],t[1]),['Yes','No','Cancel'])
                if resp=='c':
                    return
                elif resp=='y':
                    runCommand("aptitude purge {}".format(t[0])) #TODO

    # For a better user experience, correct problems by failure mode
    for failure_mode in (("Missing","are not installed"),
                         ("PartiallyInstalled","have some but not all packages installed"),
                         ("NotConfigured","are present locally but not registered in CM"),
                         ("ModifiedLocally","are newer than the CM copy"),
                         ("OutOfDate","are older than the CM copy"),
                         ("Unknown","are in an indeterminate state")):

        for name in sorted(host.expected_deployments.keys()):
            depl = host.expected_deployments[name]
            if depl.status == failure_mode[0]:

                # Exactly what we do depends on the component type and failure mode
                if isinstance(depl.component, RepoApplication):

                    # Don't attempt to do any repo applications outside of the default repository
                    if hasattr(depl.component,'repo_distribution'):
                        print("{} is {}, but in a non-standard repository, please correct manually".format(name,depl.status))
                    else:
                        for pkg in depl.missingPackages():
                            resp = prompt("Install {} for component {}?".format(pkg,name),['Yes','No','Cancel'])
                            if resp=='c':
                                return
                            elif resp=='y':
                                runCommand("aptitude install {}".format(pkg)) #TODO

                elif isinstance(depl.component, NonRepoApplication):

                    # Can't actually ever fix a non-repo application
                    print("{} is {}, but is a non-repo application, please correct manually".format(name,depl.status))

                elif isinstance(depl.component, CmComponent):

                    # If the input contains error we could be asked to deploy a component without having a deployment path
                    if not hasattr(depl,'location'):
                        print("{} does not have a deployment path specified for this host, please correct manually".format(name))
                    else:
                        # Build the local and cm paths and correct by failure mode
                        local_path = depl.location
                        cm_working_path = os.path.join(CM_WORKING_DIR, depl.component.cm_location, depl.component.cm_filename)

                        if depl.status == "NotConfigured":
                            resp = prompt("Add {} to CM?".format(name),['Yes','No','Cancel'])
                            if resp=='c':
                                return
                            elif resp=='y':
                                addSvnWorkingFile(local_path, cm_working_path)
                        elif depl.status == "Missing":
                            resp = prompt("Use {} from CM?".format(name),['Yes','No','Cancel'])
                            if resp=='c':
                                return
                            elif resp=='y':
                                print("<<Copy {} to {}>>".format(cm_working_path,local_path))
                                shutil.copy2(cm_working_path, local_path)
                        elif depl.status == "ModifiedLocally" or depl.status == "OutOfDate":
                            while True:
                                resp = prompt("Use local file or repository file for {} ({} appears newer)?".format(
                                                name, 'local' if depl.status=="ModifiedLocally" else 'repo'),
                                                ['Local','Repo','Diff','Skip','Cancel'])
                                if resp=='c':   return
                                elif resp=='d':
                                    print("DIFF (< is repository file, > is local file)")
                                    subprocess.call(['diff',cm_working_path,local_path])
                                elif resp=='l':
                                    updateSvnWorkingFile(local_path, cm_working_path)
                                    break
                                elif resp=='r':
                                    print("<<Copy {} to {}>>".format(cm_working_path,local_path))
                                    shutil.copy2(cm_working_path, local_path)
                                    break
                                else:
                                    break


if __name__ == '__main__':
    # Validate command line parameters to either set mode or print help
    mode = None

    if len(sys.argv)==2:
        arg = sys.argv[1]
        if arg=='-t' or arg=='--text':            mode = 'text'
        elif arg=='-x' or arg=='--xml':           mode = 'xml'
        elif arg=='-i' or arg=='--interactive':   mode = 'interactive'

    if mode is None:
        v = sys.version_info
        print("\nSite management synchronization script (c)2011 Jody Sankey")
        print("Currently running in Python v{}.{}.{}".format(*v))
        print("\n Usage: {} MODE\n".format(os.path.basename(sys.argv[0])))
        print(" Where MODE is one of:")
        print("   -i, --interactive  Interact with user to resolve errors")
        print("   -t, --text         Output errors in simple text format")
        print("   -x, --xml          Output XML to standard location")
        sys.exit()

    # Get local host name and determine if we have root privileges
    is_root = (os.geteuid()==0)
    host = socket.gethostname().lower()

    # Won't be able to do interactive unless running as root
    if not is_root and mode == 'interactive':
        print("Interactive mode won't effectively unless run as root, sorry")
        sys.exit()


    # Check we find the site definition
    if not os.path.exists(SITE_XML_FILE):
        print("ERROR: Could not find SiteDescription at {}".format(SITE_XML_FILE))
        sys.exit(1)

    # Gather authorization for subversion
    if not auth.readFromFile():
        if mode == 'interactive':
            auth.readFromTerminal()
        else:
            print("ERROR: Could not find a valid authorization in {}".format(auth.filename))
            sys.exit(1)

    # Make sure the working copy of subversion is up to date with the repository
    if len(subprocess.check_output("svn {} stat {}".format(auth.subversionParams(), CM_WORKING_DIR),shell=True))>1:
        print("ERROR: Working directory is not up to date with repository. Please correct before continuing")
        print("       (e.g. from oberon: svn commit /home/systems/site/svn)")
        sys.exit(1)

    # If root, fetch new package definitions
    if is_root:
        # Debian is still < Python 3.3 so can't use subprocess.DEVNULL :-(
        with open(os.devnull, "w") as fnull:
            subprocess.call(['aptitude','update'], stdout=fnull)


    # Build a site description object and check we're in it
    sd = sitemgt.SiteDescription(SITE_XML_FILE)
    if host not in sd.hosts.keys():
        print("ERROR: Could not find host {} in site description")
        sys.exit(1)

    # Ask the host to gather its current status of all deployment objects
    sd.hosts[host].gatherDeploymentStatus(CM_WORKING_DIR)

    # Take the next step based on mode
    if mode=='text':
        outputToText(sd.hosts[host])
    elif mode=='xml':
        outputToXml(sd.hosts[host])
    elif mode=='interactive':
        interactivelyCorrect(sd.hosts[host])
