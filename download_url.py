#!/usr/bin/python3
#========================================================
# Downloads a file from a url, and saves with a
# timestamped copy if the content has changed from the
# most recent copy.
#========================================================
# Copyright Jody M Sankey 2019
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import argparse
import base64
from datetime import datetime
import hashlib
import os.path
import re
import shutil
import sys
import urllib.error
import urllib.request

BLOCK_SIZE = 1024*1024
TIMESTAMP_PLACEHOLDER = '%'
TIMESTAMP_FORMAT = '%Y-%m-%d_%H%M'
TIMESTAMP_REGEX = r'\d{4}-\d{2}-\d{2}_\d{4}'


def _create_arg_parser():
    """Returns a configured ArgumentParser."""
    parser = argparse.ArgumentParser(
        description='Downloads a file from a url and saves a timestamped copy '
        + 'if the content has changed from the most recent copy')
    parser.add_argument('--url', required=True, action='store', dest='url',
                        help='url to download file from')
    parser.add_argument('--output', required=True, action='store', dest='output',
                        help='path to output files, including a % to replace with timestamp')
    return parser


def last_matching_file(output_dir, output_template):
    """Returns the filename of the lexicographically greatest file in the supplied
    directory matching regex, or None if no matching files are found."""
    regex = re.compile(output_template.replace(TIMESTAMP_PLACEHOLDER, TIMESTAMP_REGEX))
    matches = [f for f in os.listdir(output_dir)
               if os.path.isfile(os.path.join(output_dir, f))
               and regex.match(f)]
    return os.path.join(output_dir, max(matches)) if matches else None


def hash_file(path):
    """Returns a base64 encoded hash of the input file."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        buffer = f.read(BLOCK_SIZE)
        while len(buffer) > 0:
            hasher.update(buffer)
            buffer = f.read(BLOCK_SIZE)
    return base64.urlsafe_b64encode(hasher.digest()[:12]).decode('utf-8')


def download_url(args):
    """Downloads a url using the supplied command line arguments."""
    # Validate arguments.
    output_dir, output_template = os.path.split(args.output)
    if not os.path.exists(output_dir):
        print("{} does not exist".format(output_dir))
        sys.exit(1)
    if output_template.count(TIMESTAMP_PLACEHOLDER) != 1:
        print("{} does not contain exactly one {}".format(output_template, TIMESTAMP_PLACEHOLDER))
        sys.exit(1)
    time_string = datetime.now().strftime(TIMESTAMP_FORMAT)
    output_file = os.path.join(output_dir, output_template.replace('%', time_string))
    if os.path.exists(output_file):
        print("Output file {} already exists".format(output_file))
        sys.exit(1)

    # Download the url into a tempfile.
    try:
        temp_file, _ = urllib.request.urlretrieve(args.url)
    except urllib.error.URLError as ex:
        print("Exception fetching {}:\n{}".format(args.url, ex))
        sys.exit(2)
    temp_hash = hash_file(temp_file)

    # Compare hash to the last file and act accordingly.
    last_file = last_matching_file(output_dir, output_template)
    last_hash = hash_file(last_file) if last_file else None
    if not last_hash:
        print("Saving first content hash {} to {}".format(temp_hash, output_file))
        shutil.move(temp_file, output_file)
    elif last_hash != temp_hash:
        print("Saving new content hash {} to {}".format(temp_hash, output_file))
        shutil.move(temp_file, output_file)
    else:
        print("Skipping duplicate content hash {}".format(temp_hash))
        os.unlink(temp_file)

if __name__ == '__main__':
    download_url(_create_arg_parser().parse_args())
