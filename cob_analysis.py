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

import matplotlib
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import matplotlib.dates
import numpy as np
from scipy.signal import savgol_filter


#matplotlib.use('Agg') # Use before the pyplot import to run on a machine without graphical UI

VERSION = '0.1.0'

# Assorted conversion constants.
HALF_SECOND = dt.timedelta(milliseconds=500)
M_PER_DEGREE_LAT = 1852 * 60
FT_PER_M = 3.281
KT_PER_MS = 1.94384

# Savgol motion filter windows, note this assumes points are roughly one second apart.
BOAT_FILTER_W = 15
BOB_FILTER_W = 9

# Marker intervals
MARKER_T = 30

# Paper dimensions.
LETTER_W = 11
LETTER_H = 8.5
MARGIN = 0.4

# All colors are taken from https://flatuicolors.com/palette/defo
GREEN = '#2ecc71'
BLUE = '#3498db'
RED = '#e74c3c'
BLACK = '#000000'


class Point:
    """A single point on a track segment."""
    def __init__(self, time, lat, long, speed):
        self.time = time
        self.lat = lat
        self.long = long
        self.speed = speed

    def __str__(self):
        return f'{self.time} lat={self.lat}/long={self.long} speed={self.speed}'

    def offset_from(self, other):
        """Returns the (lat, long) offset of this point from other in meters."""
        dlat_m = (self.lat - other.lat) * M_PER_DEGREE_LAT
        dlong_m = (self.long - other.long) * M_PER_DEGREE_LAT * m.cos(m.radians(other.lat))
        return (dlat_m, dlong_m)

    def range_and_bearing_from(self, other):
        """Returns the (range, bearing) of this point from other in meters and degrees."""
        (dlat_m, dlong_m) = self.offset_from(other)
        range_m = m.sqrt(m.pow(dlat_m, 2) + m.pow(dlong_m, 2))
        bearing = (m.degrees(m.atan2(dlong_m, dlat_m)) + 360) % 360
        return (range_m, bearing)

    def plus_range_and_bearing(self, range, bearing):
        """Returns a new point range (in meters) and bearing (in degrees) away from this point."""
        dlat = (range * m.cos(m.radians(bearing))) / M_PER_DEGREE_LAT
        dlong = (range * m.sin(m.radians(bearing))) / M_PER_DEGREE_LAT / m.cos(m.radians(self.lat))
        return Point(self.time, self.lat+dlat, self.long+dlong, self.speed)


class PointPair:
    """A pair of points measured at the same time."""
    def __init__(self, datum, object):
        self.datum = datum
        self.object = object
        self.range_m = object.range_and_bearing_from(datum)[0]

    def __str__(self):
        return (f'{self.datum.time} lat={self.datum.lat:.3f}/long={self.datum.long:.3f} '
                f'rng={self.range_m:.1f}m')

    @property
    def time(self):
        """Returns the time of this PointPair"""
        return self.datum.time


class Track:
    """The motion of an object over time, including smoothing."""
    def __init__(self, points, filter_window):
        self.raw = points
        time = [p.time for p in points]
        rel_time = [t - time[0] for t in time]
        lat = savgol_filter([p.lat for p in points], filter_window, 3)
        long = savgol_filter([p.long for p in points], filter_window, 3)
        speed = savgol_filter([p.speed for p in points], filter_window, 3)
        self.smooth = [Point(time[i], lat[i], long[i], speed[i]) for i in range(len(points))]
        self.marker_idxs = []
        self.marker_names = []
        marker_t = dt.timedelta(seconds=0)
        for i in range(len(rel_time) - 1):
            if abs(rel_time[i] - marker_t) < abs(rel_time[i+1] - marker_t):
                self.marker_idxs.append(i)
                self.marker_names.append('{:.0f}s'.format(marker_t.total_seconds()))
                marker_t += dt.timedelta(seconds=MARKER_T)


    def __len__(self):
        return len(self.smooth)

    @property
    def start_time(self):
        """Returns the time at which the Track starts."""
        return self.smooth[0].time

    @property
    def end_time(self):
        """Returns the time at which the Track ends."""
        return self.smooth[-1].time

    @property
    def elapsed_time(self):
        """Returns the duration of this Track."""
        return self.end_time - self.start_time

    def offset_from(self, origin):
        """Returns the (lat, long) offsets of points in this track from an origin, in meters."""
        return [p.offset_from(origin) for p in self.smooth]

    def range_and_bearing_from(self, other):
        """Returns a list of (range, bearing) of points in this track from another, in m and deg."""
        return [self.smooth[i].range_and_bearing_from(other.smooth[i]) for i in range(len(self))]


class RecoveryPass:
    """A single pass at recovering an overboard Bob, defined as a list of PointPairs."""
    def __init__(self, recovered, recovery_num, pass_num, pairs):
        self.recovered = recovered
        self.recovery_num = recovery_num
        self.pass_num = pass_num
        self.boat = Track([p.object for p in pairs], BOAT_FILTER_W)
        self.bob = Track([p.datum for p in pairs], BOB_FILTER_W)

    def __str__(self):
        return(f'recovery #{self.recovery_num} pass #{self.pass_num}   recovered={self.recovered} '
               f'  elapsed time={int(self.boat.elapsed_time.total_seconds())}s'
               f'  max range={self.max_range:.1f}m')

    @property
    def max_range(self):
        """Returns the maximum distance between the boat and bob, in meters."""
        return max([rb[0] for rb in self.boat.range_and_bearing_from(self.bob)])

    @property
    def title(self):
        """Returns a string summarizing this RecoveryPass."""
        return '{}  Overboard: {}, Pass: {}, Start: {}'.format(
            self.boat.start_time.strftime('%Y-%m-%d'), self.recovery_num, self.pass_num,
            self.boat.start_time.strftime('%H:%M:%S'))

    @staticmethod
    def set_defaults():
        """Sets global matplotlib properties suitable for a PDF output."""
        #print(matplotlib.rcParams.keys())
        matplotlib.rcParams['xtick.labelsize'] = 'small'
        matplotlib.rcParams['ytick.labelsize'] = 'small'
        matplotlib.rcParams['axes.edgecolor'] = 'black'

    def plot_relative_position(self, axes):
        """Plots the relative positions using the supplied Matplotlib axes."""
        (ranges, bearings) = zip(*self.boat.range_and_bearing_from(self.bob))
        # Long winded way to find an unoccupied sector to place the range numbers
        sectors = {int(b / 30) for (r, b) in zip(ranges, bearings) if r > 25}
        best_sector = 0
        while len(sectors) > 0 and len(sectors) < 12:
            best_sector = (set(range(12)) - sectors).pop()
            neighbors = {(s-1)%12 for s in sectors} | {(s+1)%12 for s in sectors}
            sectors |= neighbors

        axes.plot([m.radians(b) for b in bearings], to_ft(ranges), linestyle='-', color=RED)
        axes.plot([m.radians(bearings[i]) for i in self.boat.marker_idxs],
                  to_ft([ranges[i] for i in self.boat.marker_idxs]),
                  marker='o', linestyle='', fillstyle='none', color=RED)
        for i, name in zip(self.boat.marker_idxs, self.boat.marker_names):
            axes.annotate(name, (m.radians(bearings[i]), to_ft(ranges[i])), color=RED,
                          ha='left', va='center', xytext=(8, 0), textcoords='offset points',
                          fontsize='small')
        axes.set_theta_zero_location("N")
        axes.set_rlabel_position(best_sector*30+20)
        axes.set_theta_direction(-1)
        axes.set_thetagrids(angles=np.arange(0, 359, 30),
                            labels=['{:03d}°'.format(x) for x in range(0, 360, 30)])
        axes.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(50))
        axes.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('{x:.0f}ft'))
        axes.grid(which='major', axis='both', linestyle='-', color='#cccccc')

    def plot_absolute_position(self, axes):
        """Plots the absolute positions using the supplied Matplotlib axes."""
        origin = self.bob.smooth[0]
        (bob_lat, bob_long) = zip(*self.bob.offset_from(origin))
        (bob_m_lat, bob_m_long) = zip(*[self.bob.smooth[i].offset_from(origin)
                                        for i in self.bob.marker_idxs])
        (boat_lat, boat_long) = zip(*self.boat.offset_from(origin))
        (boat_m_lat, boat_m_long) = zip(*[self.boat.smooth[i].offset_from(origin)
                                          for i in self.bob.marker_idxs])
        axes.plot(to_ft(bob_long), to_ft(bob_lat), linestyle='-', color=BLUE)
        axes.plot(to_ft(bob_m_long), to_ft(bob_m_lat),
                  marker='o', linestyle='', fillstyle='none', color=BLUE)
        for lat, long, name in zip(bob_m_lat, bob_m_long, self.bob.marker_names):
            axes.annotate(name, (to_ft(long), to_ft(lat)), color=BLUE,
                          ha='left', va='center', xytext=(8, 0), textcoords='offset points',
                          fontsize='small')
        axes.plot(to_ft(boat_long), to_ft(boat_lat), linestyle='-', color=RED)
        axes.plot(to_ft(boat_m_long), to_ft(boat_m_lat),
                  marker='o', linestyle='', fillstyle='none', color=RED)
        for lat, long, name in zip(boat_m_lat, boat_m_long, self.boat.marker_names):
            axes.annotate(name, (to_ft(long), to_ft(lat)), color=RED,
                          ha='left', va='center', xytext=(8, 0), textcoords='offset points',
                          fontsize='small')
        axes.axis('equal')
        for ax in [axes.xaxis, axes.yaxis]:
            ax.set_major_locator(matplotlib.ticker.FixedLocator([0]))
            ax.set_minor_locator(matplotlib.ticker.MultipleLocator(100))
            ax.set_minor_formatter(matplotlib.ticker.ScalarFormatter())
        axes.grid(which='major', axis='both', linestyle='-', color='black')
        axes.grid(which='minor', axis='both', linestyle='-', color='#cccccc')
        axes.tick_params(which='both', axis='y', labelrotation=90)
        axes.set_xlabel('Longitude Offset (ft)', fontsize='small')
        axes.set_ylabel('Latitude Offset (ft)', fontsize='small')

    def plot_speeds(self, axes):
        """Plots the absolute speeds using the supplied Matplotlib axes."""
        start_t = min(self.bob.smooth[0].time, self.boat.smooth[0].time)
        bob_s = [p.speed * KT_PER_MS for p in self.bob.smooth]
        bob_t = [(p.time - start_t).total_seconds() for p in self.bob.smooth]
        boat_s = [p.speed * KT_PER_MS for p in self.boat.smooth]
        boat_t = [(p.time - start_t).total_seconds() for p in self.boat.smooth]

        axes.plot(boat_t, boat_s, linestyle='-', color=RED)
        axes.plot(bob_t, bob_s, linestyle='-', color=BLUE)
        axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(30))
        axes.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(1))
        axes.grid(which='major', axis='both', linestyle='-', color='#cccccc')
        axes.xmargin = 0
        axes.set_xlim(left=0)
        axes.set_ylim(bottom=0)
        axes.set_ylabel('Speed (kt)', fontsize='small')
        axes.set_xlabel('Time (sec)', fontsize='small')

    def add_statistics(self):
        """Adds summary statistics to the current figure."""
        baseline_pos = [0.06, 0.25]
        def write_block(index, heading, text):
            pos = [baseline_pos[0] + int(index/3)*0.09, baseline_pos[1] - index%3*0.05]
            plt.figtext(pos[0], pos[1], heading, va='top', fontsize='x-small')
            plt.figtext(pos[0], pos[1]-0.015, text, va='top', fontsize='large')

        minutes, seconds = divmod(self.boat.elapsed_time.total_seconds(), 60)
        # Ignore the first and last few seconds when calculating set and drift
        drift_r, drift_b = self.bob.smooth[-10].range_and_bearing_from(self.bob.smooth[10])
        drift_s = drift_r/(self.bob.smooth[-10].time - self.bob.smooth[10].time).total_seconds()
        bob_dist = self.bob.smooth[-1].range_and_bearing_from(self.bob.smooth[0])[0]
        write_block(0, 'Total Duration', '{} m {} s'.format(int(minutes), int(seconds)))
        write_block(1, 'Current Set', '{:03.0f}°'.format(drift_b))
        write_block(2, 'Current Drift', '{:0.1f} kt'.format(drift_s * KT_PER_MS))
        write_block(3, 'Drift Distance', '{:.0f} ft'.format(bob_dist * FT_PER_M))
        write_block(4, 'Max Separation', '{:.0f} ft'.format(self.max_range * FT_PER_M))
        if self.recovered:
            # Calculate pick up speed from the vector between where we'd end up drifting for the
            # final ~10sec and the where the boat actually ended up.
            end_t = (self.boat.smooth[-1].time - self.boat.smooth[-10].time).total_seconds()
            drift_end = self.boat.smooth[-10].plus_range_and_bearing(drift_s*end_t, drift_b)
            boat_end = self.boat.smooth[-1]
            end_r, _ = boat_end.range_and_bearing_from(drift_end)
            write_block(5, 'Pick Up Speed', '{:0.1f} kt'.format(end_r/end_t))
        else:
            # Calculate closest approach as the min range in the last half of the run.
            ranges = [rb[0] for rb in self.boat.range_and_bearing_from(self.bob)]
            min_r = min(ranges[int(len(ranges)/2):-1])
            write_block(5, 'Closest Approach', '{:.0f} ft'.format(min_r * FT_PER_M))

    def create_figure(self):
        """Plots the recovery pass as a new figure, heavily optimized to print nicely using PDF
        on letter paper."""
        fig = plt.figure(dpi=300)
        fig.set_size_inches(LETTER_W, LETTER_H)
        fig.tight_layout()

        # Add the title
        plt.figtext(MARGIN/LETTER_W, (LETTER_H-MARGIN)/LETTER_H, self.title,
                    va='top', fontsize='x-large', fontweight='bold')
        plt.figtext((LETTER_W-MARGIN)/LETTER_W, (LETTER_H-MARGIN)/LETTER_H,
                    "Recovered" if self.recovered else "Not Picked Up",
                    color=(GREEN if self.recovered else BLACK),
                    va='top', ha='right', fontsize='x-large', fontweight='bold')

        # Create the subplots, each with its own y-axis formatting
        relative_axes = plt.subplot(131, polar=True)
        absolute_axes = plt.subplot(132)
        speed_axes = plt.subplot(133)
        self.plot_relative_position(relative_axes)
        self.plot_absolute_position(absolute_axes)
        self.plot_speeds(speed_axes)

        # Manually position the axes, adding padding to account for the axis ticks, labels, and
        # titles that fall outside the rectangle used for positioning.
        relative_axes.set_position([MARGIN/LETTER_W-0.02, 0.37, 0.49, 0.49])
        absolute_axes.set_position([0.55, 0.38, 0.4, 0.48])
        speed_axes.set_position([0.3, MARGIN/LETTER_H+0.05, 0.65, 0.2])

        # Add additional statistics
        self.add_statistics()


def to_ft(input):
    """Converts a list supplied in meters to feet."""
    if isinstance(input, (list, tuple)):
        return [m * FT_PER_M for m in input]
    return input * FT_PER_M


def points_from_gpx_file(filename):
    """Returns a list of points extracted from the supplied GPX file."""
    root = ElementTree.parse(filename).getroot()
    xml_track = root.find('{http://www.topografix.com/GPX/1/1}trk')
    points = []
    for xml_segment in xml_track.findall('{http://www.topografix.com/GPX/1/1}trkseg'):
        for xml_point in xml_segment.findall('{http://www.topografix.com/GPX/1/1}trkpt'):
            xml_time = xml_point.find('{http://www.topografix.com/GPX/1/1}time')
            xml_speed = (xml_point.find('{http://www.topografix.com/GPX/1/1}extensions')
                         .find('{http://www.topografix.com/GPX/1/1}navionics_speed'))
            points.append(Point(
                time=dt.datetime.fromisoformat(xml_time.text[:-1]+'+00:00').astimezone(),
                lat=float(xml_point.attrib['lat']),
                long=float(xml_point.attrib['lon']),
                speed=float(xml_speed.text)))
    return points


def filter_points_by_time(points, args):
    """Returns the subset of points in the supplied list that comply with any start or end times
    in args."""
    def point_with_time(point, naive_time):
        time = dt.time(hour=naive_time.hour, minute=naive_time.minute, second=naive_time.second,
                       tzinfo=point.time.tzinfo)
        return dt.datetime.combine(point.time.date(), time)

    start = points[0].time if not args.start_time else point_with_time(points[0], args.start_time)
    end = points[-1].time if not args.end_time else point_with_time(points[-1], args.end_time)
    return [p for p in points if p.time >= start and p.time <= end]


def match_point_pairs(datums, objects):
    """Given two time ordered lists of Point objects, returns a list of PointPairs created from the
    entries in each list that occured at the same time."""
    pairs = []
    idx_d = idx_o = 0
    while idx_d < len(datums) and idx_o < len(objects):
        if datums[idx_d].time < objects[idx_o].time - HALF_SECOND:
            # If the first index is earlier than we're waiting for in the second list increment it.
            idx_d += 1
        elif objects[idx_o].time < datums[idx_d].time - HALF_SECOND:
            # If the second index is earlier than we're waiting for in the first list increment it.
            idx_o += 1
        else:
            # They must be within half a second, treat it as a match and increment both
            pairs.append(PointPair(datums[idx_d], objects[idx_o]))
            idx_d += 1
            idx_o += 1
    return pairs


def find_recovery_passes(pairs, args):
    """Given a time ordered list of PointPair objects detect when Bob went overboard and was
    recovered or was passed at close range, returning a list of all passes at recovery."""
    passes = []

    def start_of_increase(end_i):
        """Returns the earliest index at which the range mononically increases until end_i."""
        for i in range(end_i, 0, -1):
            if pairs[i-1].range_m > pairs[i].range_m:
                return i

    def earliest_in_range(start_i, end_i):
        """Returns the earliest index at which the range is within some nominal small number that
        means we're on boat. Note we're not relying on only this small range to determine recovery,
        but if recovery did occur this is where we stop the pass to avoid 15 seconds on being on
        the boat waiting for the recovery timer to trigger."""
        for i in range(start_i, end_i):
            if pairs[i].range_m < 2.0:
                return i
        return end_i

    # Assume Bob starts off on the boat!
    overboard = False
    over_distance = False
    overboard_count = pass_count = 0
    transition_i = 0
    for i, pair in enumerate(pairs):
        pair_over_distance = pair.range_m > args.distance
        time_since_transition = pair.time - pairs[transition_i].time
        if pair_over_distance != over_distance:
            # Track any transition from under to over distance or visa versa.
            over_distance = pair_over_distance
            transition_i = i
            if overboard and over_distance and (pair.time - pairs[pass_start_i].time
                                                > args.overboard_time):
                # If we're moving from in range to out of range while overboard treat (and if the
                # previous pass hasn't just started), treat it as a new pass.
                passes.append(
                    RecoveryPass(recovered=False, recovery_num=overboard_count, pass_num=pass_count,
                                 pairs=pairs[pass_start_i:i+1]))
                pass_start_i = i+1
                pass_count += 1
        elif not overboard and over_distance and time_since_transition > args.overboard_time:
            # If we've been over distance for a while potentially that causes us to go overboard.
            overboard = True
            overboard_count += 1
            pass_start_i = start_of_increase(i) # Start when the range began increasing.
            pass_count = 1
        elif overboard and not over_distance and time_since_transition > args.recovery_time:
            # If we've been under distance for a while potentially that causes us to be recovered.
            overboard = False
            pass_end_i = earliest_in_range(transition_i, i) # End once we're really close
            passes.append(
                RecoveryPass(recovered=True, recovery_num=overboard_count, pass_num=pass_count,
                             pairs=pairs[pass_start_i:pass_end_i+1]))
    # We assume if we got a track from Bob we managed to recover it eventually, so don't worry
    # about completing any recovery that might have still been in progress at the end of the file.
    return passes


def create_parser():
    """Creates the definition of the expected command line flags."""
    def file_if_valid(parser, arg):
        if not os.path.exists(arg):
            parser.error(f'{arg} does not exist')
        return arg

    def seconds(arg):
        return dt.timedelta(seconds=arg)

    def time(arg):
        return dt.time.fromisoformat(arg)

    def ft_to_m(arg):
        return int(arg / FT_PER_M)


    parser = argparse.ArgumentParser(
        description='Script to analyze two Navionics GPS tracks during crew overboard manoeuvres, '
                    'one from the boat, one from the overboard object: "Bob".\n'
                    'NOTE: This uses the Python ElementTree parser which is not secure against '
                    'malicious inputs. Please be sure you trust whatever generated your input '
                    'track files.',
        epilog='Copyright Jody Sankey 2022')
    parser.add_argument('boat_track', metavar='BOAT_TRACK', type=lambda x: file_if_valid(parser, x),
                        help='A GPX file describing the track of the boat during manoeuvres.')
    parser.add_argument('bob_track', metavar='BOB_TRACK', type=lambda x: file_if_valid(parser, x),
                        help='A GPX file describing the track of the overboard object during '
                             'manoeuvres.')
    parser.add_argument('output', metavar='OUTPUT_FILE', help='The path for the output PDF file.')
    parser.add_argument('-s', '--start_time', metavar='HH:MM', action='store', type=time,
                        help='Optional maneouvre start time as a 24hr string in the local time '
                             'zone. All data prior to this time will be ignored.')
    parser.add_argument('-e', '--end_time', metavar='HH:MM', action='store', type=time,
                        help='Optional maneouvre end time as a 24hr string in the local time '
                             'zone. All data after this time will be ignored.')
    # Note we ask the user to supply the distance in FT to match our UI, but internally use meters.
    parser.add_argument('-d', '--distance', metavar='FT', action='store', default=10, type=ft_to_m,
                        help='Distance between tracks (in feet) to determine overboard/recovery.')
    parser.add_argument('-to', '--overboard_time', metavar="SEC", action='store', type=seconds,
                        default=dt.timedelta(seconds=10),
                        help='Time (in seconds) to detect overboard. If distance between tracks '
                             'remains above `distance` for this time bob is considered overboard.')
    parser.add_argument('-tr', '--recovery_time', metavar="SEC", action='store', type=seconds,
                        default=dt.timedelta(seconds=20),
                        help='Time (in seconds) to detect recovery. If distance between tracks '
                             'remains below `distance` for this time bob is considered recovered.')
    return parser


def main():
    """Executes the script using command line arguments."""
    args = create_parser().parse_args()

    print('Parsing boat track...')
    boat_points = points_from_gpx_file(args.boat_track)
    print('Parsing bob track...')
    bob_points = points_from_gpx_file(args.bob_track)
    print('  Found {} boat points and {} bob points'.format(len(boat_points), len(bob_points)))

    if args.start_time or args.end_time:
        print('Filtering points by start/end time...')
        boat_points = filter_points_by_time(boat_points, args)
        bob_points = filter_points_by_time(bob_points, args)

    print('Finding matching points...')
    pairs = match_point_pairs(bob_points, boat_points)
    print('  Found {} pairs'.format(len(pairs)))
    print('Finding recovery passes...')
    passes = find_recovery_passes(pairs, args)
    print('  Found {} passes'.format(len(passes)))

    datestr = passes[0].boat.start_time.strftime('%Y-%m-%d')
    print('Generating {} pages...'.format(len(passes)))
    pdf_pages = PdfPages(args.output)
    RecoveryPass.set_defaults()
    for rp in passes:
        rp.create_figure()
        pdf_pages.savefig()
    pdf_pages.infodict()['Title'] = '{} Crew Overboard Analysis'.format(datestr)
    pdf_pages.infodict()['Author'] = "Jody Sankey's cob_analysis script, version {}".format(VERSION)
    pdf_pages.infodict()['CreationDate'] = dt.datetime.today()
    pdf_pages.close()
    print('Wrote ' + args.output)


if __name__ == '__main__':
    main()
