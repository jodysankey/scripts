#!/usr/bin/python3

""" Python script for linux to manage a connection and
disconnection of a non-fixed host from the site. This
script is far simpler now that caching is managed by a
separate sync process.
"""

#========================================================
# Copyright Jody M Sankey 2011-2016
#========================================================
# AppliesTo: linux
# AppliesTo: sasha,scarlett
# RemoveExtension: True
# PublicPermissions: True
#========================================================


import os
import subprocess
import sys


CONNECT_OPTION = 'x-jms.connect'
SITE_MOUNTPOINT = os.environ['SITEPATH']
BACKUP_SCRIPT = '/etc/backup-system'
SITE_SYNC_SCRIPT = ['host_site_sync', '-x']


class MountableDirectory(object):
    """A class to manage a mount in fstab in terms of the local mount point."""

    def __init__(self, mount_path):
        """Initialize given a mount point."""
        if not os.path.exists(mount_path):
            raise IOError('MountableDirectory error: {} does not exist'.format(mount_path))
        self.path = mount_path
        self.performed_mount = False

    def is_mounted(self):
        """Returns true if point is currently mounted."""
        return subprocess.call(['findmnt', '-mln', self.path]) == 0

    def mount(self):
        """Mounts the point, returning true on success and remembering if we needed to act"""
        self.performed_mount = False
        if self.is_mounted():
            return True
        pprint("Mounting {}".format(self.path))
        success = run_and_report(['mount', self.path])
        if success:
            self.performed_mount = True
        return success

    def unmount(self, force):
        """(Optionally force) unmounts the point if currently mounted, returning true on success"""
        if not self.is_mounted():
            return True
        pprint("Unmounting {}".format(self.path))
        return run_and_report(['umount', '-f', self.path] if force else ['umount', self.path])

    def restore(self, force):
        """Unmounts the point iff the most recent mount did mounting, returning true on success."""
        if self.performed_mount:
            return self.unmount(force)
        return True


def run_and_report(command):
    """Runs a command, returning True on success and printing retcode on error."""
    ret_code = subprocess.call(command)
    if ret_code != 0:
        eprint("{} failed with code {}".format(command[0], ret_code))
    return ret_code == 0


def pprint(string):
    """Prints a string with a standard prefix."""
    print('  ' + string)


def eprint(string):
    """Prints a string with a standard error prefix."""
    print("ERROR: " + string)


def print_usage():
    """Print standard help string then quit"""
    print("\n  Usage: {} connect|disconnect [force]|backup\n".format(sys.argv[0]))
    print("  connect     Mount connectable network mounts")
    print("  disconnect  [Forcibly] unmount connectable network mounts")
    print("  backup      (Root only) Backup machine configuration, user homes, and logs to")
    print("              network and sync site status, temporarily mounting if necessary")
    print("Script (c)2011-2020 Jody Sankey")
    print("Currently running in Python v{}.{}.{}\n".format(*sys.version_info))
    sys.exit()


def do_backup():
    """Perform a standard backup operation, mounting as necessary."""
    if os.geteuid() != 0:
        eprint('Only root can perform a backup')
        return

    pprint("Executing backup script {}...".format(BACKUP_SCRIPT))
    run_and_report(BACKUP_SCRIPT)

    site_mount = MountableDirectory(SITE_MOUNTPOINT)
    if not site_mount.mount():
        eprint('Could not mount ' + SITE_MOUNTPOINT)
    else:
        pprint("Executing site status script {}...".format(SITE_SYNC_SCRIPT))
        run_and_report(SITE_SYNC_SCRIPT)
        site_mount.restore(False)


def connectable_mounts():
    """Returns a list of MountableDirectory s for all mounts marked as connectable."""
    # Findmnt can output dirs of everything in fstab with the magic option, allow non-zero
    # return codes since there might not be any matching mountpoints.
    try:
        mount_dirs = subprocess.check_output(
            ['findmnt', '-sn', '-O', CONNECT_OPTION, '-o', 'TARGET']).decode('utf-8').split('\n')
        return [MountableDirectory(mnt) for mnt in mount_dirs]
    except subprocess.CalledProcessError:
        return []


if __name__ == '__main__':
    # If run as a script take parameters to feed the function from the command line
    if not (len(sys.argv) == 2 or (len(sys.argv) == 3 and sys.argv[2] == "force")):
        print_usage()
        sys.exit(1)

    if sys.argv[1] == "connect":
        for mnt in connectable_mounts():
            mnt.mount()
    elif sys.argv[1] == "disconnect":
        for mnt in connectable_mounts():
            mnt.unmount(len(sys.argv) == 3 and sys.argv[2] == "force")
    elif sys.argv[1] == "backup":
        do_backup()
    else:
        print_usage()
        sys.exit(1)
