#!/bin/python3

"""Script to analyze two Navionics GPS tracks during crew overboard
manoeuvres, one from the boat, one from the 'crew'. Run with --help
to see the command line options."""

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
import datetime as dt
import math as m
import os.path
import xml.etree.ElementTree as ElementTree


NS = {'': 'http://www.topografix.com/GPX/1/1'}

# Assorted conversion constants.
M_PER_DEGREE_LAT = 1852 * 60
FT_PER_M = 3.281



class Point:
    """A single point on a track segment."""
    def __init__(self, xml_point):
        xml_time = xml_point.find('time', NS)
        self.time = dt.datetime.fromisoformat(xml_time.text[:-1]+'+00:00').astimezone()
        self.lat = float(xml_point.attrib['lat'])
        self.long = float(xml_point.attrib['lon'])
        self.xml = xml_point

    def __str__(self):
        return f'{self.time} lat={self.lat}/long={self.long}'

    def pos_string(self):
        """Returns a string describing the position of this point."""
        return "{}°{:06.3f}'{} {}°{:06.3f}'{}".format(
            int(abs(self.lat)), (abs(self.lat)%1)*60, 'N' if self.lat > 0 else 'S',
            int(abs(self.long)), (abs(self.long)%1)*60, 'E' if self.long > 0 else 'W')

    def date_pos_string(self):
        """Returns a string describing the datetime and position of this point."""
        return '{} at {}'.format(self.time.strftime('%Y-%m-%d %H%M'), self.pos_string())

    def distance_from(self, other):
        """Returns the distance of this point from other in meters."""
        dlat_m = (self.lat - other.lat) * M_PER_DEGREE_LAT
        dlong_m = (self.long - other.long) * M_PER_DEGREE_LAT * m.cos(m.radians(other.lat))
        return m.sqrt(m.pow(dlat_m, 2) + m.pow(dlong_m, 2))

    def rounded_lat_long(self):
        """Returns the (lat, long) of this point rounded to a ~1 meter resolution."""
        return (round(self.lat, 5), round(self.long, 5))



class PointRange:
    """A start and end index into a list of points."""
    def __init__(self, points, start, end):
        self.points = points
        self.start = start
        self.end = end
        self.rounded = {p.rounded_lat_long() for p in points[start:end+1]}

    def __str__(self):
        return '{}-{} near {}'.format(self.points[self.start].time.strftime('%H%M'),
                                      self.points[self.end].time.strftime('%H%M'),
                                      self.points[self.start].pos_string())

    @property
    def duration(self):
        """Returns the duration between the first and last points in this range."""
        return self.points[self.end].time - self.points[self.start].time

    def point_within_distance(self, point, distance):
        """Returns True if the point (rounded) is within distance of all points in this range."""
        point_rounded = point.rounded_lat_long()
        for range_rounded in self.rounded:
            dlat_m = (range_rounded[0] - point_rounded[0]) * M_PER_DEGREE_LAT
            dlong_m = ((range_rounded[1] - point_rounded[1]) * M_PER_DEGREE_LAT
                       * m.cos(m.radians(point_rounded[0])))
            if m.sqrt(m.pow(dlat_m, 2) + m.pow(dlong_m, 2)) > distance:
                return False
        return True

    def last_index_where_point_is_outside_distance(self, point, distance):
        """Returns the last index in this range at which the supplied point is outside distance,
        or None is its within distance of the entire range."""
        for compare_idx in range(self.end, self.start-1, -1):
            if point.distance_from(self.points[compare_idx]) > distance:
                return compare_idx
        return None

    def increment_end(self):
        """Increases the size of this range by one point at the end."""
        self.end += 1
        self.rounded.add(self.points[self.end].rounded_lat_long())

    def overlaps(self, other):
        """Returns true if this range overlaps other."""
        return not (self.start > other.end or self.end < other.start)


class Track:
    """The interpreted contexts of a GPX file."""
    def __init__(self, filename):
        self.tree = ElementTree.parse(filename)
        self.points = []
        xml_track = self.tree.getroot().find('trk', NS)
        self.xml_segment = xml_track.find('trkseg', NS)
        for xml_point in self.xml_segment.findall('trkpt', NS):
            self.points.append(Point(xml_point))

    def get_stationary_ranges(self, args):
        """Returns a list of PointRange objects for times in the track where we appear stationery
        based on thresholds supplied in args."""
        ranges = []
        potential = None
        current = PointRange(self.points, 0, 0)
        for idx, point in enumerate(self.points):
            # If the new point is inside the current range just extend the range and we're done.
            if current.point_within_distance(point, args.distance):
                current.increment_end()
                continue

            # This point is not close to the set of rounded values in the current range, find
            # the latest place in the range we're in disagreement with.
            outside_idx = current.last_index_where_point_is_outside_distance(point, args.distance)
            if outside_idx is not None:
                if current.duration > args.time:
                    # We're about to forget a current range that was potentially viable.
                    if not potential:
                        # If we didn't have a previous viable range use this.
                        potential = current
                    elif not current.overlaps(potential):
                        # If this doesn't touch the previous viable range we found, that previous
                        # viable range should be included in the output.
                        ranges.append(potential)
                        potential = current
                    elif current.duration > potential.duration:
                        # If this is longer than an the previous one and overlaps the previous one
                        # it is a better candidate to be potentially included in the results.
                        potential = current
                # The new current range is everything we matched after the first mismatch.
                current = PointRange(self.points, outside_idx+1, idx)
            else:
                # Is it technically possible to not be outside and point because we used rounded
                # positions before for speed. If so just extend the range.
                current.increment_end()

        # After the loop, include any eligible range we've not yet added
        if potential:
            ranges.append(potential)
        return ranges

    def trim(self, start, end):
        """Delete all points outside the supplied indices and update times to match."""
        # Update the custom Navionics time propertied if they exist.
        ext = self.xml_segment.find('extensions', NS)
        if ext and ext.find('navionics_start_time', NS):
            ext.find('navionics_start_time', NS).text = self.points[start].xml.find('time', NS).text
        if ext and ext.find('navionics_end_time', NS):
            ext.find('navionics_end_time', NS).text = self.points[end].xml.find('time', NS).text
        # Delete any points outside the time range.
        start_time = self.points[start].time
        end_time = self.points[end].time
        for point in self.points:
            if point.time < start_time or point.time > end_time:
                self.xml_segment.remove(point.xml)

    def save(self, filename):
        """Outputs the track to the supplied filename."""
        ElementTree.register_namespace('', NS[''])
        self.tree.write(filename, xml_declaration=True, encoding='UTF-8')


def output_filename(input_filename):
    """Returns the default output filename to use for the supplied input filename."""
    base, ext = os.path.splitext(input_filename)
    return base + '_trimmed' + ext


def create_parser():
    """Creates the definition of the expected command line flags."""
    def file_if_valid(parser, arg):
        if not os.path.exists(arg):
            parser.error(f'{arg} does not exist')
            return None
        return arg

    def seconds(arg):
        return dt.timedelta(seconds=arg)

    def ft_to_m(arg):
        return int(arg / FT_PER_M)


    parser = argparse.ArgumentParser(
        description='Script to interactively trim a Navionics GPS tracks to the time of motion.'
                    'NOTE: This uses the Python ElementTree parser which is not secure against '
                    'malicious inputs. Please be sure you trust whatever generated your input '
                    'track files.',
        epilog='Copyright Jody Sankey 2022')
    parser.add_argument('input', metavar='TRACK_FILE', type=lambda x: file_if_valid(parser, x),
                        help='A GPX track file.')
    parser.add_argument('output', metavar='OUT_FILE', nargs='?', default=None, help='The output '
                        'filename, if omitted filename will be derived from the input.')
    # Note we ask the user to supply the distance in FT to match our UI, but internally use meters.
    parser.add_argument('-d', '--distance', metavar='FT', action='store', default=50, type=ft_to_m,
                        help='Distance threshold to determine stationary.')
    parser.add_argument('-t', '--time', metavar="SEC", action='store', type=seconds,
                        default=dt.timedelta(seconds=300),
                        help='Time (in seconds) to determine stationary.')
    return parser



def main():
    """Executes the script using command line arguments."""
    args = create_parser().parse_args()

    print('Parsing track...')
    track = Track(args.input)
    ranges = track.get_stationary_ranges(args)

    print('Track contains the following events:')
    print('  0: Track starts {}'.format(track.points[0].date_pos_string()))
    for i, rng in enumerate(ranges):
        print('  {}: Stationary {}'.format(i+1, rng))
    print('  {}: Track ends {}'.format(len(ranges)+1, track.points[-1].date_pos_string()))

    start_evt = int(input('Which of these events should be the new start of the file? '))
    start_idx = 0 if start_evt == 0 else ranges[start_evt-1].end
    end_evt = int(input('Which of these events should be the new end of the file? '))
    end_idx = len(track.points)-1 if start_evt == len(ranges)+1 else ranges[end_evt-1].start

    output = output_filename(args.input) if args.output is None else args.output
    track.trim(start_idx, end_idx)
    track.save(output)
    print('Wrote modified track to {}'.format(output))

if __name__ == '__main__':
    main()
