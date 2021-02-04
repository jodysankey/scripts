#!/usr/bin/python3

"""Wrapper for the ClassifyDir class to allow command line
investigation of the current backup configuration for a
directory structure, as determined by .classify files."""

#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

# TODO(jody): Move the basedir on create login inside classifydir (what does this mean?)

import collections
import os
import operator
import sys
import time

from table import Table, Cell
from classifydir import ClassifiedDir, PROTECTIONS, VOLUMES, PROTECTION_COLORS, VOLUME_COLORS

GREY = '\033[90m'
WHITE = '\033[97m'
RESET_COLOR = '\033[m'

LEADER = '  '
MAX_EXTRA_DEPTH = 100

def print_summary(classdir, include_undefined, extra_levels):
    """Print a nested tree of all directories given a ClassifiedDir object."""
    max_depth = classdir.deepest_explicit + extra_levels
    data = []
    for desc in (desc for desc in classdir.descendants() if
                 desc.depth <= max_depth and desc.recursion_depth <= extra_levels
                 and (include_undefined or desc.deepest_explicit >= 0)):
        at_recursion_limit = desc.recurse and desc.recursion_depth == extra_levels
        data.append(_list_row(desc, desc.depth == max_depth or at_recursion_limit))
    if not data:
        print("NO SUITABLE DIRECTORIES WERE FOUND")
    else:
        widths = [max([len(x) for x in y]) for y in zip(*data)]
        fmt = "{{}}{{:<{}s}}  {{:^{}s}}  {{:^{}s}} {{}}{{:^{}s}} {{}}".format(*widths[1:5])
        for datum in data:
            print(fmt.format(*datum))
        print(RESET_COLOR)


def print_grid(classdir):
    """Print a grid of file/dir count by classification and volume."""
    totals = {v: {p: [0, 0, 0] for p in PROTECTIONS} for v in VOLUMES}
    for archive in classdir.descendant_roots():
        total = totals[archive.volume][archive.protection]
        total[0] += 1
        total[1] += archive.archive_file_count()
        total[2] += archive.archive_size()

    table = Table(len(VOLUMES) + 2, len(PROTECTIONS) + 2)
    for x, volume in zip(range(1, 100), VOLUMES):
        volume_color = VOLUME_COLORS[volume]
        volume_total = [sum(t[i] for t in totals[volume].values()) for i in range(3)]
        table.cells[0][x] = Cell(volume.upper(), 1, '^', volume_color)
        table.cells[-1][x] = _cell_for_totals(*volume_total, color=volume_color)
    for y, protection in zip(range(1, 100), PROTECTIONS):
        protection_col = PROTECTION_COLORS[protection]
        protection_total = [sum(d[protection][i] for d in totals.values()) for i in range(3)]
        table.cells[y][0] = Cell(protection.upper(), 1, '>', protection_col)
        table.cells[y][-1] = _cell_for_totals(*protection_total, color=protection_col)
        for x, volume in zip(range(1, 100), VOLUMES):
            table.cells[y][x] = _cell_for_totals(*totals[volume][protection])
    grand_total = [sum(dd[i] for d in totals.values() for dd in d.values()) for i in range(3)]
    table.cells[-1][0] = Cell('TOTAL', 1, '>', WHITE)
    table.cells[0][-1] = Cell('TOTAL', 1, '^', WHITE)
    table.cells[-1][-1] = _cell_for_totals(*grand_total)

    table.print()


def print_archives(classdir):
    """print a grid of information for all archives ordered by classification and volume"""
    archives = {volume: {protection: [] for protection in PROTECTIONS} for volume in VOLUMES}
    for archive in classdir.descendant_roots():
        archives[archive.volume][archive.protection].append(archive)

    cells = [[Cell(heading) for heading in ('Protection', 'Volume', 'Name', 'FileCount', 'Size',
                                            'LastChange', 'Hash', 'Recurse', 'Compress')]]
    for volume in VOLUMES:
        for protection in PROTECTIONS:
            lines = []
            for archive in sorted(archives[volume][protection], key=operator.attrgetter('name')):
                lines.append([archive.archive_root().name,
                              str(archive.archive_file_count()),
                              _human_size(archive.archive_size()),
                              _filetime_string(archive.archive_last_change()),
                              archive.archive_hash(),
                              str(archive.recurse),
                              str(archive.compress)])
            if lines:
                texts = ([protection.capitalize(), volume.capitalize()] +
                         ['\n'.join(c) for c in zip(*lines)])
                aligns = ['<' if i == 2 else '^' for i in range(9)]
                colors = [PROTECTION_COLORS[protection] if i == 0
                          else VOLUME_COLORS[volume] for i in range(9)]
                cells.append([Cell(s[0], 1, s[1], s[2]) for s in zip(texts, aligns, colors)])
    table = Table(1, 1)
    table.cells = cells
    table.print()


def _cell_for_totals(archives, files, size, color=WHITE):
    """Returns a new cell object to describe a quantity of files and archives."""
    if archives == 0:
        return Cell('-', color=GREY)
    return Cell('\n'.join((_pluralize(archives, 'archive'), _pluralize(files, 'file'),
                           _human_size(size))), color=color)


def _list_row(class_dir, would_hide_children):
    """Returns (color, path, archive, protection, volume) tuple for printing a ClassifiedDir."""
    archive = class_dir.archive_root().name if class_dir.archive_root() else None
    pad = LEADER * class_dir.depth

    name = pad + class_dir.base_name
    if would_hide_children and class_dir.children:
        name += " ..."     # indicates there may be are more directories not shown

    size = '' if class_dir.size is None else (pad + _human_size(class_dir.total_size()))

    if archive is None:
        row = (GREY, name, '', '-',
               GREY, class_dir.volume.upper() if class_dir.volume else '-', size)
    elif archive == _list_row.last_archive:
        row = (class_dir.protection_color(), name, _ditto(archive), _ditto(class_dir.protection),
               class_dir.volume_color(), _ditto(class_dir.volume), size)
    else:
        row = (class_dir.protection_color(), name, archive, class_dir.protection.upper(),
               class_dir.volume_color(), class_dir.volume.upper(), size)
    _list_row.last_archive = archive
    return row
_list_row.last_archive = None


def _filetime_string(timestamp):
    """Return a string representation of a time since epoch."""
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp))


def _pluralize(number, singular_text):
    """Return a trivial plural (add 's' if not one) of a text string."""
    return '{} {}{}'.format(number, singular_text, 's' if number != 1 else '')


def _human_size(size_bytes):
    """Return number of bytes rounded to a sensible scale."""
    # TODO(jody): put this in a standard library somewhere
    size = size_bytes
    for unit in ['B', 'kB', 'MB', 'GB', 'TB']:
        if size < 10 and unit != 'B ':
            return "{0:.1f} {1}".format(size, unit)
        if size < 1024:
            return "{0:.0f} {1}".format(size, unit)
        size /= 1024
    return "err"


def _ditto(original):
    """Return a ditto string of the same length as original."""
    pad = ' ' * ((len(original) - 1) // 2)
    return pad  + '"' + pad


def print_usage():
    """Print standard help string."""
    version = sys.version_info
    print("Usage: {} MODE [path]".format(os.path.basename(sys.argv[0])))
    print("where MODE is one of:")
    for mode_name in MODES:
        print("  {:<10} = {}".format(mode_name, MODES[mode_name][3]))
    print("Script (c)2010-2020 Jody Sankey currently running in Python v{}.{}.{}".format(*version))


def parse_command_line():
    """Parses the command line from sys.argv, printing an error and exiting on failure
    or returning a tuple (function, arguments_to_function) on success."""
    # Note: I did consider using argparse here in 2020, but the output just wasn't going to be as
    #       nice a help output, and would still need a separate layer to convert the output of
    #       argparser to input argments for the classified dir.
    if len(sys.argv) not in range(2, 4):
        print_usage()
        sys.exit(1)
    # Validate the path, using current dir if not supplied.
    path = os.path.abspath('.' if len(sys.argv) == 2 else sys.argv[2])
    if not os.path.exists(path):
        print("Path does not exist: " + path)
        sys.exit(2)
    # Validate the mode.
    mode_name = sys.argv[1].lower()
    if mode_name not in MODES:
        print_usage()
        sys.exit(2)
    # Use the mode to (usually) build a classified_dir, and return the function and arguments.
    (function, cd_args, function_args, _) = MODES[mode_name]
    if cd_args is None:
        return (function, function_args)
    class_dir = ClassifiedDir(path, *cd_args)
    return (function, (class_dir,) + function_args)


MODES = collections.OrderedDict([
    #ModeName: (function, classDirArgs, functionArgs, helpString)
    ("grid", (print_grid, (True, MAX_EXTRA_DEPTH), (),
              "Tabulate total archive and file count and archive size in each category")),
    ("archives", (print_archives, (True, MAX_EXTRA_DEPTH), (),
                  "Tabulate summary information for each archive")),
    ("listshort", (print_summary, (False, 1), (False, 0),
                   "List directory hierarchy without sizes, excluding undefined directories")),
    ("list", (print_summary, (False, 1), (True, 0),
              "List basic directory hierarchy without sizes")),
    ("list+", (print_summary, (False, 2), (True, 1),
               "List directory hierarchy without sizes, one extra level")),
    ("list++", (print_summary, (False, 3), (True, 2),
                "List directory hierarchy without sizes, two extra levels")),
    ("list+++", (print_summary, (False, 4), (True, 3),
                 "List directory hierarchy without sizes, three extra levels")),
    ("listall", (print_summary, (False, MAX_EXTRA_DEPTH), (True, MAX_EXTRA_DEPTH),
                 "List complete directory hierarchy without sizes")),
    ("sizeshort", (print_summary, (True, 1), (False, 0),
                   "List directory hierarchy with sizes, excluding undefined directories")),
    ("size", (print_summary, (True, 1), (True, 0),
              "List basic directory hierarchy with sizes")),
    ("size+", (print_summary, (True, 2), (True, 1),
               "List directory hierarchy with sizes, one extra level")),
    ("size++", (print_summary, (True, 3), (True, 2),
                "List directory hierarchy with sizes, two extra levels")),
    ("size+++", (print_summary, (True, 4), (True, 3),
                 "List directory hierarchy with sizes, three extra levels")),
    ("sizeall", (print_summary, (True, MAX_EXTRA_DEPTH), (True, MAX_EXTRA_DEPTH),
                 "List complete directory hierarchy with sizes")),
    ("help", (print_usage, None, (),
              "Print this usage information")),
    ])


if __name__ == "__main__":
    (FUNCTION, ARGS) = parse_command_line()
    FUNCTION(*ARGS)
