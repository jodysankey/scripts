#!/usr/bin/python3
#========================================================
# BackupView.py
#========================================================
# $HeadURL:                                             $
# Last $Author: jody $
# $Revision: 742 $
# $Date: 2009-12-28 02:23:37 -0600 (Mon, 28 Dec 2009) $
#========================================================
# Wrapper for the ClassifyDir class to allow command line
# perspectives of the current backup configuration for a
# directory structure, as determined by .classify files
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

# TODO(jody): Consider using ArgParser instead of this hardcoded version - flags would be useful
# TODO(jody): Move the basedir on create loginc inside classifydir

__author__="Jody"

from table import Table, Cell
from classifydir import ClassifiedDir, PROTECTIONS, VOLUMES, PROTECTION_COLORS, VOLUME_COLORS

import collections
import os
import operator
import sys
import time

GREY = '\033[90m'
WHITE = '\033[97m'
RESET_COLOR = '\033[m'

LEADER = '  '
MAX_EXTRA_DEPTH = 100


def printCommandLineUsage():
    """Print standard help string then quit"""
    v = sys.version_info
    print("Usage: {} MODE [path]".format(os.path.basename(sys.argv[0])))
    print("where MODE is one of:")
    for mode_name in MODES:
        print("  {:<10} = {}".format(mode_name, MODES[mode_name][3]))
    print("Script (c)2010-2015 Jody Sankey currently running in Python v{}.{}.{}".format(*v))

    sys.exit()

def printSummary(classdir, include_undefined, extra_levels):
    """print a nested tree of all directories given a ClassifiedDir object"""
    max_depth = classdir.deepest_explicit + extra_levels
    data = []
    for d in (d for d in classdir.descendants() if
              d.depth <= max_depth and d.recursion_depth <= extra_levels
              and (include_undefined or d.deepest_explicit >= 0)):
        at_recursion_limit = d.recurse and d.recursion_depth == extra_levels
        data.append(_listRow(d, d.depth == max_depth or at_recursion_limit))
    if not data:
        print("NO SUITABLE DIRECTORIES WERE FOUND")
    else:
        widths = [max([len(x) for x in y]) for y in zip(*data)] 
        fmt = "{{}}{{:<{}s}}  {{:^{}s}}  {{:^{}s}} {{}}{{:^{}s}} {{}}".format(*widths[1:5]) 
        for d in data:
            print(fmt.format(*d))
        print(RESET_COLOR)


def printGrid(classdir):
    """print a grid of file/dir count by classification and volume"""
    totals = {v: {p: [0,0,0] for p in PROTECTIONS} for v in VOLUMES}
    for archive in classdir.descendantRoots():
        total = totals[archive.volume][archive.protection]
        total[0] += 1
        total[1] += archive.archiveFileCount()
        total[2] += archive.archiveSize()
            
    table = Table(len(VOLUMES) + 2, len(PROTECTIONS) + 2)
    for x, v in zip(range(1,100), VOLUMES):
        volume_col = VOLUME_COLORS[v]
        volume_total = [sum(t[i] for t in totals[v].values()) for i in range(3)]
        table.cells[0][x] = Cell(v.upper(), 1, '^', volume_col)
        table.cells[-1][x] = _cellForTotals(*volume_total, color=volume_col)
    for y, p in zip(range(1,100), PROTECTIONS):
        protection_col = PROTECTION_COLORS[p]
        protection_total = [sum(d[p][i] for d in totals.values()) for i in range(3)]
        table.cells[y][0] = Cell(p.upper(), 1, '>', protection_col)
        table.cells[y][-1] = _cellForTotals(*protection_total, color=protection_col)
        for x, v in zip(range(1,100), VOLUMES):
            table.cells[y][x] = _cellForTotals(*totals[v][p])
    grand_total = [sum(dd[i] for d in totals.values() for dd in d.values()) for i in range(3)]
    table.cells[-1][0] = Cell('TOTAL', 1, '>', WHITE)
    table.cells[0][-1] = Cell('TOTAL', 1, '^', WHITE)
    table.cells[-1][-1] = _cellForTotals(*grand_total)

    table.print()
        
 
def printArchives(classdir):
    """print a grid of information for all archives ordered by classification and volume"""
    archives = {v: {p: [] for p in PROTECTIONS} for v in VOLUMES}
    for archive in classdir.descendantRoots():
        archives[archive.volume][archive.protection].append(archive)
        
    cells = [[Cell(heading) for heading in ('Protection', 'Volume', 'Name', 'FileCount', 'Size',
                                            'LastChange', 'Hash', 'Recurse', 'Compress')]]
    for v in VOLUMES:
        for p in PROTECTIONS:
            lines = []
            for archive in sorted(archives[v][p], key = operator.attrgetter('name')):
                lines.append([archive.archiveRoot().name,
                              str(archive.archiveFileCount()),
                              _humanSize(archive.archiveSize()), 
                              _filetimeString(archive.archiveLastChange()),
                              archive.archiveHash(),
                              str(archive.recurse), 
                              str(archive.compress)])
            if len(lines):
                texts = [p.capitalize(), v.capitalize()] + ['\n'.join(c) for c in zip(*lines)]
                aligns = ['<' if i == 2 else '^' for i in range(9)]
                colors = [PROTECTION_COLORS[p] if i == 0 else VOLUME_COLORS[v] for i in range(9)]
                cells.append([Cell(s[0], 1, s[1], s[2]) for s in zip(texts, aligns, colors)])
    table = Table(1,1)
    table.cells = cells
    
    table.print()
               
def _cellForTotals(archives, files, size, color=WHITE):
    """Returns a new cell object to describe a quantity of files and archives."""
    if archives == 0:
        return Cell('-', color=GREY)
    else:
        return Cell('\n'.join((_pluralize(archives, 'archive'), _pluralize(files, 'file'),
                              _humanSize(size))), color=color)
 
def _listRow(cd, would_hide_children):
    """Returns (color, path, archive, protection, volume) tuple for printing a ClassifiedDir"""
    archive = None if not cd.archiveRoot() else cd.archiveRoot().name
    name = (LEADER * cd.depth) + cd.base_name
    if would_hide_children and len(cd.children):
        name += " ..."     # indicates there may be are more directories not shown
        
    size = '' if cd.size is None else (LEADER * cd.depth) + _humanSize(cd.totalSize())

    if archive is None:
        row = (GREY, name, '', '-', GREY, cd.volume.upper() if cd.volume else '-', size)
    elif archive == _listRow.lastArchive:
        row = (cd.protectionColor(), name, _ditto(archive), _ditto(cd.protection),
                cd.volumeColor(), _ditto(cd.volume), size)
    else:
        row = (cd.protectionColor(), name, archive, cd.protection.upper(),
                cd.volumeColor(), cd.volume.upper(), size)
    _listRow.lastArchive = archive
    return row
_listRow.lastArchive = None


def _filetimeString(timestamp):
    """return a string representation of a time since epoch"""
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp))

def _pluralize(number, singular_text):
    """return a trivial plural (add 's' if not one) of a text string"""
    return '{} {}{}'.format(number, singular_text, 's' if number != 1 else '')

def _humanSize(size_bytes):
    """return number of bytes rounded to a sensible scale"""
    # TODO(jody): put this in a standard library somewhere
    sz = size_bytes
    for ut in ['B','kB','MB','GB','TB']:
        if sz < 10 and ut != 'B ':
            return "{0:.1f} {1}".format(sz, ut)
        elif sz < 1024:
            return "{0:.0f} {1}".format(sz, ut)
        sz /= 1024
    return "err"

def _ditto(string_length):
    """return a ditto string of the same length as the input"""
    pad = ' ' * ((len(string_length) - 1) // 2)
    return pad  + '"' + pad
            

MODES = collections.OrderedDict([
    #ModeName: (function, classDirArgs, functionArgs, helpString)
    ("grid", (printGrid, (True, MAX_EXTRA_DEPTH), (),
              "Tabulate total archive and file count and archive size in each category")),
    ("archives", (printArchives, (True, MAX_EXTRA_DEPTH), (),
              "Tabulate summary information for each archive")),
    ("listshort", (printSummary, (False, 1), (False, 0),
              "List directory hierarchy without sizes, excluding undefined directories")),
    ("list", (printSummary, (False, 1), (True, 0),
              "List basic directory hierarchy without sizes")),
    ("list+", (printSummary, (False, 2), (True, 1),
              "List directory hierarchy without sizes, one extra level")),
    ("list++", (printSummary, (False, 3), (True, 2),
              "List directory hierarchy without sizes, two extra levels")),
    ("list+++", (printSummary, (False, 4), (True, 3),
              "List directory hierarchy without sizes, three extra levels")),
    ("listall", (printSummary, (False, MAX_EXTRA_DEPTH), (True, MAX_EXTRA_DEPTH),
              "List complete directory hierarchy without sizes")),
    ("sizeshort", (printSummary, (True, 1), (False, 0),
              "List directory hierarchy with sizes, excluding undefined directories")),
    ("size", (printSummary, (True, 1), (True, 0),
              "List basic directory hierarchy with sizes")),
    ("size+", (printSummary, (True, 2), (True, 1),
              "List directory hierarchy with sizes, one extra level")),
    ("size++", (printSummary, (True, 3), (True, 2),
              "List directory hierarchy with sizes, two extra levels")),
    ("size+++", (printSummary, (True, 4), (True, 3),
              "List directory hierarchy with sizes, three extra levels")),
    ("sizeall", (printSummary, (True, MAX_EXTRA_DEPTH), (True, MAX_EXTRA_DEPTH),
              "List complete directory hierarchy with sizes")),
    ("help", (printCommandLineUsage, None, (),
              "Print this usage information")),
    ])

if __name__ == "__main__":
    
    if len(sys.argv) not in range(2, 4):
        printCommandLineUsage()
    mode_name = sys.argv[1].lower()
    path = os.path.abspath('.' if len(sys.argv) == 2 else sys.argv[2])
    if not os.path.exists(path):
        print("Path does not exist: " + path)
        sys.exit(1)
    else:
        print()
        
    if mode_name in MODES:
        mode_settings = MODES[mode_name]
        if mode_settings[1] is None:
            mode_settings[0](*mode_settings[2])
        else:
            cd = ClassifiedDir(path, *mode_settings[1])
            mode_settings[0](cd, *mode_settings[2])
    else:
        printCommandLineUsage()
