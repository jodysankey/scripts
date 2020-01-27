#!/usr/bin/python3
#========================================================
# Python script for linux to build a set of user archives
# on the primary server.
#--------------------------------------------------------
# Depends on the classifydir python module, and scans
# supplied paths for a user, outputting tar files to a
# archive subdirectory with compression and or encryption
# as specified by attributes of .classify files.
#--------------------------------------------------------
# Archives can be decrpyted using gpg:
#   gpg --cipher-algo AES256 --output <> --decrypt <>
#========================================================
# Copyright Jody M Sankey 2010-2018
#========================================================
# AppliesTo: linux
# AppliesTo: oberon
# RemoveExtension: True
#========================================================


from os import path

import argparse
import classifydir
import datetime
import grp
import os
import pwd
import subprocess
import sys
import tarfile
 

# Set VERBOSE to see added freshened archives and skipped files in stdout
VERBOSE = False  


def freshenArchiveSets(search_paths, output_path, sizes, key_file):
    """Updates all tar files for archives of the specified sizes located on any of the supplied
    search paths. tars are created or freshened in size based directories in the output_path, and
    any unrecognized files in output_path will be deleted on completion.  Where encryption is
    required, the contents of key_file will be used as the key."""

    if not path.exists(output_path):
        _writeError('Archive output directory does not exist: ' + output_path)
        return
    if not path.exists(key_file):
        _writeError('Key file does not exist: ' + key_file)
        return

    cds = [classifydir.ClassifiedDir(s, True) for s in search_paths if path.exists(s)]
    for size in sizes:
        size_output_path  = path.join(output_path, size)
        if not path.exists(size_output_path):
            _writeStatus('Creating archive size output directory: ' + size_output_path)
            os.makedirs(size_output_path)
        freshenArchives([a for cd in cds for a in cd.descendantRoots() if a.volume == size],
                        size_output_path,
                        key_file)


def freshenArchives(archives, output_path, key_file):
    """Updates all tar files for a collection of archives in the same output directory.
    tars are created or freshened in output_path, and any unrecognized files in output_path will
    be deleted on completion.  Where encryption is required, the contents of key_file will be used
    as the key."""
    created_archive_names = set()
    existing_tars = set(os.listdir(output_path))
    for archive in archives:
        # Handle and report the case where two archives were given the same name.
        if archive.name in created_archive_names:
            _writeError('Additional archive with same name ({}) in dir {}, skipping'.format(
                        archive.name, output_path))
            continue
        else:
            created_archive_names.add(archive.name)

        # Create or update the archive timestamp
        tar_name = _archiveTarFilename(archive)
        if tar_name in existing_tars:
            freshenTimestamp(path.join(output_path, tar_name), 'existing tar')
            existing_tars.remove(tar_name)    
        else:
            createTar(archive, output_path)
            if _shouldEncryptArchive(archive): encryptTar(archive, output_path, key_file)

    # Anything else remaining in the archive directory is no longer needed
    for tar_name in existing_tars:
        removeFile(path.join(output_path, tar_name), 'unwanted existing tar')


def createTar(archive, output_path):
    """Creates an optionally compressed tarfile in the specified directory containing the contents
    of an classified directory object at an archive root."""
    unencrypted_path = path.join(output_path, _archiveTarFilename(archive, before_encryption=True))
    _writeStatus('Creating new tar: ' + unencrypted_path)

    tar_file = tarfile.open(unencrypted_path, 'w:gz' if archive.compress else 'w')
    for f in archive.archiveFilenames():
        try:
            tar_file.add(f, path.relpath(f, archive.full_path), recursive=False)
        except IOError as e:
            if VERBOSE: _writeStatus('Skipping unreadable file {}'.format(f))
    tar_file.close()


def encryptTar(archive, output_path, key_file):
    """Creates an encrypted tarfile in the specified directory using an existing unencrypted
    version and a supplied key file. The unencrypted archive is removed after encryption."""
    unencrypted_path = path.join(output_path, _archiveTarFilename(archive, before_encryption=True))
    encrypted_path = path.join(output_path, _archiveTarFilename(archive, before_encryption=False))

    _writeStatus('Encrypting archive to {}'.format(encrypted_path))
    result = subprocess.run(['gpg',
                             '--no-options',
                             '--batch',
                             '--cipher-algo', 'AES256', 
                             '--passphrase-file', key_file,
                             '--output', encrypted_path,
                             '--symmetric', unencrypted_path],
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.STDOUT)
    if result.returncode != 0:
        _writeError('Non zero return code {} from PGP encrypting to {}: {}'.format(
                     result.returncode, encrypted_path, result.stdout.decode('utf-8')))
    removeFile(unencrypted_path, 'pre-encryption tar')


def freshenTimestamp(filename, role):
    """Touches the specified file to freshen its timestamp."""
    if VERBOSE:
        _writeStatus('Freshen timestamp on {}: {}'.format(role, filename))
    try:
        os.utime(filename, None)
    except IOError:
        _writeError('Could not update timestamp on {}: {}'.format(role, filename))


def removeFile(filename, role):
    """Deletes the specified file."""
    _writeStatus('Removing {}: {}'.format(role, filename))
    try:
        os.remove(filename)
    except (IOError, OSError):
        _writeError('Could not delete {}: {}'.format(role, filename))


def _writeStatus(text):
    """Record an informational note, complete with timestamp."""
    print(datetime.datetime.now().isoformat() + '  ' + text, file=sys.stdout)

def _writeError(text):
    """Record an problem, complete with timestamp."""
    global errors_found
    errors_found = True
    print(datetime.datetime.now().isoformat() + ' ERROR ' + text, file=sys.stdout)
    print(datetime.datetime.now().isoformat() + '  ' + text, file=sys.stderr)

def _shouldEncryptArchive(archive):
    """Returns true iff the output of the supplied classified directory should be encrypted"""
    return archive.protection in ('secret', 'confidential', 'restricted')

def _archiveTarFilename(archive, before_encryption=False):
    """Returns the expected filename for a classified directory, including hash."""
    return '{}_{}{}.tar{}{}'.format(
        archive.name,
        archive.archiveHash(),
        '.secret' if archive.protection == 'secret' else '',
        '.gz' if archive.compress else '',
        '.aes' if _shouldEncryptArchive(archive) and not before_encryption else '')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Builds tar archives with appropriate encryption '
            'and compression based on .classify files found in a set of search directories.')
    parser.add_argument('-k', '--keyfile', required=True, help='Path of encryption keyfile')
    parser.add_argument('-s', '--search_dirs', nargs='+', required=True, 
                        help='Paths to be searched for .classify files')
    parser.add_argument('-z', '--sizes', default='small,medium,large',
                        help='Comma separated list of archive sizes')
    parser.add_argument('-a', '--archive_dir', required=True, help='Path to output archive files')
    parser.add_argument('-u', '--user', help='Username to run operations as')
    parser.add_argument('-g', '--group', help='Group name to run operations as')
    args = parser.parse_args()

    if args.group:
        os.setgid(grp.getgrnam(args.group).gr_gid)
    if args.user:
        os.setuid(pwd.getpwnam(args.user).pw_uid)
        os.environ['HOME'] = os.path.expanduser('~' + args.user)

    freshenArchiveSets(args.search_dirs, args.archive_dir, args.sizes.split(','), args.keyfile)
    sys.exit(0)
