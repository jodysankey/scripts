#!/usr/bin/python3

"""Python script  to translate a Standard Bank formatted
CSV file into QIF suitable for import to GnuCash.

CSV file should be supplied as a parameter. Mapping
definitions for each bank account are stored in a XML
file along with the signature for detecting that account
and the output filename (which is always placed in the
same location as the input). For convenience a set of
possible locations for each XML files is hardcoded in
this script, rather than the cleaner solution of
defining them in an environment variable."""

#========================================================
# Copyright Jody M Sankey 2010-2013
#========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import argparse
import datetime
import os.path
import re
import sys
import xml.etree.ElementTree


class Colors(object):
    """A collection of Linux terminal formatting strings."""
    BOLD = '\033[1m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'


def _fatal(message, retcode):
    """Prints the message in red then exits with the supplied error code"""
    print(Colors.RED + message + Colors.ENDC)
    sys.exit(retcode)

def _info(message):
    """Prints the message in green"""
    print(Colors.GREEN + message + Colors.ENDC)

def _act(message):
    """Prints the message in white"""
    print(Colors.BOLD + message + Colors.ENDC)


class AccountMap:
    """A decription of changes to apply to an input transaction file. An AccountMap is created from
    instructions in an XML file."""

    def __init__(self, filename):
        """Initializes an object from an xml file, returning true on success."""
        if not os.path.exists(filename):
            _fatal('Could not read mapping file {}'.format(filename), 1)
        print("Parsing {}".format(filename))
        tree = xml.etree.ElementTree.parse(filename)
        root = tree.getroot()
        self.name = root.attrib['name']
        # Define the filename to use as the output, optionally containing a `%` to replace with
        # the input filename.
        self.outfile_pattern = root.attrib['outfile']
        # Whether to track prior transactions in a standard previous transactions file and
        # exclude any transactions that have already been recorded.
        self.track_previous = (
            'trackprevious' in root.attrib and root.attrib['trackprevious'] == 'true')
        self.account = root.attrib['account']
        # Define a set of regular expression that, if found in an input filename or file contents,
        # indicate the AccountMap should be applied to the input.
        self.signatures = [x.attrib['pattern'] for x in root.iter('Signature')]
        # Define regular expressions to replace in the input.
        self.replacements = [
            (x.attrib['before'], x.attrib['after']) for x in root.iter('Replace')]
        # Define regular expressions that cause a transaction to be marked as an account.
        self.classifications = [
            (x.attrib['pattern'], x.attrib['account']) for x in root.iter('Classify')]


    def outfile(self, infile):
        """Returns the expected output filename, replacing any `%` with the basename of the
        supplied input filename."""
        basename = os.path.splitext(os.path.basename(infile))[0]
        # Dirty to embed this BoA specific rename but difficult to define this generically in the
        # XML file is worth the cost/probability of usage
        basename = basename.replace('currentTransaction', datetime.date.today().strftime('%B%Y'))
        return self.outfile_pattern.replace('%', basename)


    def matches(self, filename, contents):
        """Return true if one of our signatures is found in the contents line array or in the
        filename itself."""
        for signature in [re.compile(s) for s in self.signatures]:
            if signature.search(filename):
                return True
            for line in contents.split('\n'):
                if signature.search(line):
                    return True
        return False


    def transcribe_csv(self, contents):
        """Translates the specified CSV contents to a QIF header and list of QIF transactions."""
        header = '!Account\nN{}\nTBank\n^\n!Type:Bank'.format(self.account)
        transactions = []
        # Now go through each line
        for line in contents.split('\n'):
            # Perform each replacement
            for replacement in self.replacements:
                line = re.sub(replacement[0], replacement[1], line)
            # Split the CSV
            cpt = [c.strip('\"\n\r') for c in re.split(r'"\s*,\s*"', line)]
            # Write the components
            if len(cpt) != 5:
                continue
            transaction = 'D{}\nT{}\nC{}\n'.format(cpt[0], cpt[1], cpt[2])
            if len(cpt[3]) > 0:
                transaction += 'N{}\n'.format(cpt[3])
            transaction += 'M{}\n'.format(cpt[4])
            # And match the account if possible
            for classification in self.classifications:
                if re.search(classification[0], cpt[4]):
                    _act('Assign {} to {}'.format(cpt[4], classification[1]))
                    transaction += 'L{}\n'.format(classification[1])
                    break
            transactions.append(transaction)
        return (header, transactions)

    def transcribe_qif(self, contents):
        """Translates the specified QIF contents to standard QIF form, as a header and list of
        transactions."""
        # Split the supplied QIF
        (header, transactions) = _qif_contents_to_header_and_transactions(contents)
        new_header = '\n'.join(['!Account\nN{}\n^'.format(self.account), header])
        new_transactions = [self._transcribe_qif_transaction(t) for t in transactions]
        return (new_header, new_transactions)

    def _transcribe_qif_transaction(self, transaction):
        """Performs our mapping function on the specified transaction text."""
        new_lines = []
        for line in transaction.split("\n"):
            # The Payee lines go through our processing logic, anything else is output verbatim
            if line.startswith("P"):
                # Perform each replacement.
                for replacement in self.replacements:
                    line = line[0] + re.sub(replacement[0], replacement[1], line[1:])
                # And match the account if possible.
                for classification in self.classifications:
                    if re.search(classification[0], line[1:]):
                        _act('Assign {} to {}'.format(line[1:], classification[1]))
                        new_lines.append('L{}'.format(classification[1]))
                        break
            new_lines.append(line)
        return '\n'.join(new_lines)

    def __str__(self):
        out = 'Account Map {}\n   OutFile={}\n   Account={}\n   TrackPrevious={}\n'.format(
            self.name, self.outfile_pattern, self.account, self.track_previous)
        out += ('   {} Signatures:\n'.format(len(self.signatures)) +
                '\n'.join(['      ' + s for s in self.signatures]))
        out += ('\n   {} Replacements:\n'.format(len(self.replacements)) +
                '\n'.join(['      {}=>{}'.format(r[0], r[1]) for r in self.replacements]))
        out += ('\n   {} Classifications:\n'.format(len(self.classifications)) +
                '\n'.join(['      {}=>{}'.format(c[0], c[1]) for c in self.classifications]))
        return out


def _remove_duplicate_transactions(transactions, reference_transactions):
    """Returns a list of transactions that are not present in reference_transactions."""
    return [t for t in transactions if t not in reference_transactions]


def _qif_contents_to_header_and_transactions(contents):
    """Given a QIF file, split into a header block and a list of transaction blocks."""
    # Split header at the first new date line
    res = re.match(r'\A(.*?)\n(D.*)\Z', contents, re.DOTALL)
    header = res.group(1)
    # Split transactions at a ^, and discard empties
    transactions = [x.strip() for x in res.group(2).split('\n^') if len(x)]
    return (header, transactions)


def _qif_header_and_transactions_to_contents(header, transactions):
    """Given a QIF header block and a list of transaction blocks, combine into one text block."""
    return header + '\n' + ''.join([t + '\n^\n' for t in transactions])


def _read_file(filepath):
    """Returns the contents of a file, exiting if it does not exist."""
    if not os.path.isfile(filepath):
        _fatal('File {} does not exist'.format(filepath), 2)
    with open(filepath, 'r') as f:
        return f.read()


def _write_file(filepath, contents):
    """Writes the specified contents to the specified filename, overwriting if it exists."""
    with open(filepath, 'w') as f:
        f.write(contents)


def _parse_args():
    """Defines and parses command line arguments."""
    parser = argparse.ArgumentParser(
        description='''Converts an input CSV or QIF file to a QIF file, applying the
                    transformations defined by whichever of the supplied AccountMap
                    files matches the input.''',
        epilog='''Copyright 2020 Jody Sankey, published under the MIT licence''')
    parser.add_argument('-m', '--map', help='AccountMap XML file', action='append', required=True)
    parser.add_argument('input_file', help='CVS or QIF file to convert')
    return parser.parse_args()


def main(args):
    """Processes an input file as defined by the supplied arguments."""
    # Partition, verify, and read the input filepath
    in_path = args.input_file
    (in_dir, in_file) = os.path.split(in_path)
    in_ext = os.path.splitext(in_file)[1]
    contents = _read_file(in_path)

    # Load each classifier and see whether it wants the file
    match_account_maps = []
    for amx in args.map:
        if not os.path.exists(amx):
            _fatal('Could not find AccountMap: {}'.format(amx), 3)
        else:
            account_map = AccountMap(amx)
            if account_map.matches(in_file, contents):
                match_account_maps.append(account_map)
                _info('AccountMap matched signature: {}'.format(amx))
    if len(match_account_maps) != 1:
        _fatal('Did not find exactly one matching AccountMap', 4)
    match_account_map = match_account_maps[0]

    # Determine the output
    out_file = match_account_map.outfile(in_file)
    out_path = os.path.join(in_dir, out_file)

    # Ask the account map to do the work, then close
    if in_ext.lower() == '.csv':
        (header, transactions) = match_account_map.transcribe_csv(contents)
    elif in_ext.lower() == '.qif':
        (header, transactions) = match_account_map.transcribe_qif(contents)
    else:
        _fatal('Unknown file extension on input, {} is not csv or qif.'.format(in_ext), 5)

    # Remove any already recorded transactions and update the previous transactions file.
    if match_account_map.track_previous:
        prev_path = out_path + 'prev'
        if os.path.exists(prev_path):
            (_, prev_transactions) = _qif_contents_to_header_and_transactions(_read_file(prev_path))
        else:
            (_, prev_transactions) = (None, [])
        transactions = _remove_duplicate_transactions(transactions, prev_transactions)
        prev_transactions.extend(transactions)
        _write_file(prev_path, _qif_header_and_transactions_to_contents(header, prev_transactions))


    # Write the output
    _act('Writing output to {}'.format(out_path))
    _write_file(out_path, _qif_header_and_transactions_to_contents(header, transactions))


if __name__ == '__main__':
    main(_parse_args())
