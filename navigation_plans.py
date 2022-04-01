#!/bin/python3

"""Script to generate paper navigation plans from a set of GPX
routes, typcially output by OpenCPN. Run with --help to see
the command line options."""

#==============================================================
# Copyright Jody M Sankey 2022
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENCE.md file for details.
#==============================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#==============================================================


import argparse
from datetime import datetime
import math
import xml.etree.ElementTree as ElementTree
import os
import sys
import textwrap

import matplotlib
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties
import matplotlib.pyplot as plt

# Script version
VERSION = '0.1.1'

# Paper dimensions.
LETTER_W = 11
LETTER_H = 8.5
MARGIN = 0.3
TOP_MARGIN = 0.7

# Table dimensions, last remarks column uses all remaining space.
COL_W = [0.045, 0.2, 0.11, 0.045, 0.045, 0.05, 0.05, 0.05, 0.05, 0.06]
COL_W.append(1 - sum(COL_W))
ROW_H = 0.08
REMARK_WRAP_CHARS = 39  # Hacky manual wrapping of the remarks column, dependent on its width.
ROWS_PER_PAGE = int(1/ROW_H)

# Colors and fonts
HEADER = '#cccccc'
LIGHT_ROW = '#ffffff'
DARK_ROW = '#f4f4f4'
FONTS = ['Overpass', 'Roboto', 'sans-serif']

# Namespaces in a GPX file.
NS = {'': 'http://www.topografix.com/GPX/1/1'}

# Various conversion factors
M_PER_DEGREE_LAT = 1852 * 60
M_PER_NM = 1852


class Waypoint:
    """A waypoint on a route."""
    def __init__(self, name, description, lat, lng):
        self.name = name
        self.description = description
        self.lat = lat
        self.lng = lng

    @property
    def position(self):
        """Returns a string describing the position of this waypoint."""
        return "{}° {:05.2f}' {}\n{}° {:05.2f}' {}".format(
            int(abs(self.lat)), (abs(self.lat)%1)*60, 'N' if self.lat > 0 else 'S',
            int(abs(self.lng)), (abs(self.lng)%1)*60, 'E' if self.lng > 0 else 'W')

    @property
    def full_name(self):
        """Returns a string containing the name and description of this waypoint."""
        return '{}{}'.format(self.name, '' if self.description is None else f'\n{self.description}')

    def _offset_from(self, other):
        """Returns the (lat, long) offset of this point from other in meters, assuming the distance
        is small enough to ignore curvature of the earth."""
        avg_lat = (self.lat + other.lat)/2
        dlat_m = (self.lat - other.lat) * M_PER_DEGREE_LAT
        dlong_m = (self.lng - other.lng) * M_PER_DEGREE_LAT * math.cos(math.radians(avg_lat))
        return (dlat_m, dlong_m)

    def distance_from(self, other):
        """Returns the distance of this waypoint from other in nm, assuming the distance is
        small enough to ignore curvature of the earth."""
        (dlat_m, dlong_m) = self._offset_from(other)
        return math.sqrt(math.pow(dlat_m, 2) + math.pow(dlong_m, 2)) / M_PER_NM

    def bearing_from(self, other):
        """Returns the true bearing of this point from other in degrees, assuming the distance is
        small enough to ignore curvature of the earth."""
        (dlat_m, dlong_m) = self._offset_from(other)
        return (math.degrees(math.atan2(dlong_m, dlat_m)) + 360) % 360


class Leg:
    """One leg of a route. Leg 0 has no start and is used to describe the initial location."""
    def __init__(self, number, start, destination, remarks):
        self.number = number
        self.start = start
        self.destination = destination
        if start is None:
            self.distance = 0.0
            self.true_heading = None
        else:
            self.distance = destination.distance_from(start)
            self.true_heading = destination.bearing_from(start)
        self.remarks = remarks if remarks is not None else ''

    @property
    def color(self):
        """Returns the face color to use for this leg on a table."""
        return LIGHT_ROW if self.number % 2 == 0 else DARK_ROW

    @staticmethod
    def _font(bold):
        """Returns the standard FontProperties for table cells."""
        return FontProperties(family=FONTS, size=11, weight='bold' if bold else 'normal')

    @staticmethod
    def write_header(table):
        """Writes a header for the data table in the supplied table."""
        for col, text in enumerate(['Leg', 'Destination', 'Latitude\nLongitude', 'Hdg\nM', 'Hdg\nC',
                                    'Leg\nDist', 'Cum.\nDist', 'Log', 'Leg\nTime', 'Rem.\nTime',
                                    'Remarks']):
            table.add_cell(0, col, width=COL_W[col], height=ROW_H, text=text, loc='center',
                           facecolor=HEADER, fontproperties=Leg._font(bold=True))

    @staticmethod
    def write_footer(table, row, route):
        """Writes a header for the data table in the supplied table."""
        var = '{:.0f}° {}'.format(abs(route.variation), 'West' if route.variation >= 0 else 'East')
        for col, text in [[3, f'Variation\n{var}'],
                          [5, 'Distances in\nnautical miles'],
                          [8, f'Times assume\nSOG = {int(route.speed)}kt']]:
            cell = table.add_cell(row, col, width=COL_W[col], height=ROW_H, text=text, loc='left',
                                  fontproperties=Leg._font(bold=False))
            cell.visible_edges = 'open'

    def write_line(self, table, row, route):
        """Writes this leg as cells in the supplied table."""
        def add_cell(column, text, alignment, bold=False):
            cell = table.add_cell(
                row, column, width=COL_W[column], height=ROW_H, text=text,
                facecolor=self.color, loc=alignment, fontproperties=Leg._font(bold))
            # PAD is annoyingly interpreted as a fraction of cell width
            cell.PAD = 0.008/COL_W[column]
            # Matplotlib text wrapping is annoyingly inaccurate, use hacky textwrap instead
            # cell.set_text_props(wrap=True)

        def distance_to_time(distance):
            hours, minutes = divmod(round(60*distance/route.speed), 60)
            return '{:d}:{:02d}'.format(hours, minutes)

        dist_before, dist_after = route.distance_before_and_after(self)

        # Many columns work the same for the start leg and subsequent legs.
        add_cell(1, self.destination.full_name, 'left')
        add_cell(2, self.destination.position, 'center')
        add_cell(6, f'{dist_before+self.distance:.1f}', 'center', bold=(dist_after < 0.001))
        add_cell(7, '', 'center')
        add_cell(9, distance_to_time(dist_after), 'center', bold=(self.number == 0))
        add_cell(10, textwrap.fill(self.remarks, REMARK_WRAP_CHARS), 'left')
        # Some columns are different or empty in the initial start leg.
        if self.start is None:
            add_cell(0, 'Start', 'center')
            for col in [3, 4, 5, 8]:
                add_cell(col, '-', 'center')
        else:
            mag_heading = (self.true_heading + route.variation + 360) % 360
            add_cell(0, str(self.number), 'center')
            add_cell(3, f'{mag_heading:03.0f}', 'center')
            add_cell(4, '', 'center')
            add_cell(5, f'{self.distance:.1f}', 'center')
            add_cell(8, distance_to_time(self.distance), 'center')


class Route:
    """A navigation route, comprising a list of legs, an author, and a date."""
    def __init__(self, name, author, date, legs, args):
        self.name = name
        self.author = author
        self.date = date
        self.legs = legs
        self.variation = args.variation
        self.speed = args.speed

    @property
    def page_count(self):
        """Returns the number of pages required to print this route."""
        # Use one less than rows per page because header.
        return math.ceil(len(self.legs) / (ROWS_PER_PAGE - 1))

    @property
    def distance(self):
        """Returns the total route distance in nm."""
        return sum([l.distance for l in self.legs if l.distance is not None])

    def distance_before_and_after(self, search_leg):
        """Returns the route distance before and after the supplied leg."""
        distance = 0
        for leg in self.legs:
            if leg is search_leg:
                return (distance, self.distance - distance - leg.distance)
            distance += leg.distance
        sys.exit('Could not find requested leg.')

    def _write_titles(self, page_num):
        """Writes the description of this route onto the current matplotlib figure."""
        title_left = MARGIN / LETTER_W
        title_right = (LETTER_W - MARGIN)/ LETTER_W
        title_top = (LETTER_H - TOP_MARGIN) / LETTER_H
        title_bottom = MARGIN / LETTER_H
        subtitle = '' if self.author is None else 'Prepared by: ' + self.author
        plt.figtext(title_left, title_top, self.name,
                    va='top', family=FONTS, size='xx-large', weight='bold')
        plt.figtext(title_left, title_top - 0.032, subtitle, family=FONTS, va='top', size='medium')
        if self.page_count > 1:
            plt.figtext(title_right, title_top, f'{page_num + 1} of {self.page_count}',
                        va='top', ha='right', family=FONTS, size='xx-large', weight='bold')
        plt.figtext(title_left, title_bottom,
                    self.date.strftime('Last modified: %Y-%m-%d %H:%M:%S'), family=FONTS,
                    va='bottom', size='medium')
        plt.figtext(title_right, title_bottom,
                    "PDF generated by Jody Sankey's GPX conversion script, v{}".format(VERSION),
                    family=FONTS, va='bottom', ha='right', color='#cccccc', size='small')

    def write_page(self, page_num):
        """Describes this route as a matplotlib figure."""
        fig = plt.figure(dpi=300)
        fig.set_size_inches(LETTER_W, LETTER_H)
        axes = plt.subplot(111)
        axes.set_position([MARGIN/LETTER_W, MARGIN/LETTER_H+0.02,
                           1-2*MARGIN/LETTER_W, 1-(MARGIN+TOP_MARGIN)/LETTER_H-0.08])
        axes.axis('off')
        table = matplotlib.table.Table(axes, loc='upper center')
        table.auto_set_font_size(False)

        page_legs = self.legs[page_num*(ROWS_PER_PAGE-1):(page_num+1)*(ROWS_PER_PAGE-1)]
        Leg.write_header(table)
        for i, leg in enumerate(page_legs):
            leg.write_line(table, i+1, self)
        # Assume there is always room for a footer below the last leg.
        if page_legs[-1] is self.legs[-1]:
            Leg.write_footer(table, len(page_legs)+1, self)
        axes.add_table(table)
        self._write_titles(page_num)


def parse_route_description(xml):
    """Interpret a route description as a dict of key:value pairs, ignoring other lines."""
    if xml is None:
        return dict()
    key_values = [l.split(':', maxsplit=1) for l in xml.text.splitlines() if ':' in l]
    return {kv[0].strip(): kv[1].strip() for kv in key_values}


def load_gpx_file(filename, args):
    """Constructs a route from the supplied GPX file."""
    if not os.path.exists(filename):
        sys.exit(f'File does not exist: {filename}')
    date = datetime.fromtimestamp(os.path.getmtime(filename))
    xml_route = ElementTree.parse(filename).getroot().find('rte', NS)
    name = xml_route.find('name', NS).text
    desc = parse_route_description(xml_route.find('desc', NS))

    waypoints = []
    for xml_point in xml_route.findall('rtept', NS):
        xml_desc = xml_point.find('desc', NS)
        waypoints.append(Waypoint(
            xml_point.find('name', NS).text,
            xml_desc.text if xml_desc is not None else None,
            float(xml_point.get('lat')),
            float(xml_point.get('lon'))))
    if len(waypoints) < 2:
        sys.exit('Route must contain at least two waypoints.')

    legs = [Leg(0, None, waypoints[0], desc.get('0'))]
    for i in range(1, len(waypoints)):
        legs.append(Leg(i, waypoints[i-1], waypoints[i], desc.get(str(i))))
    return Route(name, desc.get('author'), date, legs, args)


def create_parser():
    """Creates the definition of the expected command line flags."""
    def file_if_valid(parser, arg):
        if not os.path.exists(arg):
            parser.error(f'{arg} does not exist')
        return arg

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Script to build a set of printable PDF navigation plans from the supplied\n'
                    'GPX route files.\n\n'
                    'The name and description of each waypoint in the GPX are used to populate\n'
                    'the "Destination" column while the description of the *route* may be used\n'
                    'to populate the "Remarks" column. Any line in the description starting with\n'
                    'a number and colon will be used as the remark for that leg number,\n'
                    'e.g. "3: This is the remark for leg 3". A line in the description starting\n'
                    'with "author:" will be used to set a "Prepared by" heading on the output.\n\n'
                    'NOTE: This uses the Python ElementTree parser which is not secure against\n'
                    'malicious inputs. Please be sure you trust whatever generated your input\n'
                    'track files.',
        epilog='Copyright Jody Sankey 2022')
    parser.add_argument('-v', '--variation', metavar='MAGVAR', default=-13, type=int,
                        help='Magnetic variation in degrees, positive West, negative East.')
    parser.add_argument('-s', '--speed', metavar='SPEED', default=5, type=int,
                        help='Speed in knots, used for time calculations.')
    parser.add_argument('-o', '--output', metavar='OUTPUT_FILE', default='Navigation Plans.pdf',
                        help='The path for the output PDF file.')
    parser.add_argument('files', nargs='+', metavar='GPX_FILE',
                        type=lambda x: file_if_valid(parser, x), help='Input GPX files.')
    return parser


def main():
    """Executes the script using command line arguments."""
    args = create_parser().parse_args()
    #route = load_gpx_file("/mnt/jody/tmp/one/Golden Gate to Pillar Point (N of channel).gpx")

    pdf_pages = PdfPages(args.output)
    pdf_pages.infodict()['Title'] = 'Navigation Plans'
    pdf_pages.infodict()['CreationDate'] = datetime.today()
    for file in args.files:
        print(f'Reading {file}')
        route = load_gpx_file(file, args)
        if route.author is not None:
            pdf_pages.infodict()['Author'] = route.author
        for page_num in range(route.page_count):
            route.write_page(page_num)
            pdf_pages.savefig()
    pdf_pages.close()
    print('Wrote ' + args.output)



if __name__ == '__main__':
    main()
