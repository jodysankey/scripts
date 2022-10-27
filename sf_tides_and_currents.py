#!/usr/bin/python3

"""Script to gather tide and current predictions for the San Fransico Bay area
using NOAA APIs and produce PDFs to display the predictions from multiple
stations on the dame day, along with basic sun and moon data. Run with --help to
see the command line options."""

#==============================================================
# Copyright Jody M Sankey 2020-2022
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
import math
import os.path
import re
import sys
import tempfile
import textwrap

from dateutil import tz
import matplotlib
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import matplotlib.dates
import requests

import astronomy

#matplotlib.use('Agg') # Use before the pyplot import to run on a machine without graphical UI

VERSION = '0.1.5'

BASE_URL = 'https://tidesandcurrents.noaa.gov/api/datagetter'

STANDARD_PARAMS = {'units': 'english',
                   'time_zone': 'lst_ldt',
                   'format': 'json'}

# Use midspan of the Golden Gate bridge for astronomical calculations.
LOCATION = astronomy.SphericalCoordinate((37 + 49.184/60) * astronomy.DEG_TO_RAD,
                                         (122 + 28.712/60) * astronomy.DEG_TO_RAD)
TIMEZONE = tz.gettz('America/Los_Angeles')

# All colors are taken from https://flatuicolors.com/palette/defo
PURPLE = '#9b59b6'
GREEN = '#2ecc71'
BLUE = '#3498db'
RED = '#e74c3c'
ORANGE = '#f39c12'

# The actual sets of tide and current stations to plot are defined lower in the file, after
# we've defined the classes we need to represent them. Search for 'LOCATIONS'

ONE_DAY = dt.timedelta(days=1)
ONE_HOUR = dt.timedelta(hours=1)
SIX_MIN = dt.timedelta(minutes=6)
SPREADSHEET_ZERO_DATE = dt.datetime(1899, 12, 30, 0, 0, 0, 0, TIMEZONE)
SECONDS_PER_DAY = ONE_DAY.total_seconds()

LETTER_W = 11
LETTER_H = 8.5
TOP_MARGIN = 0.6
MARGIN = 0.4

class RequestError(Exception):
    """Exception raised for problems requesting external data."""
    def __init__(self, params, description):
        param_str = '&'.join(['{}={}'.format(k, v) for k, v in params.items()])
        msg = 'Error requesting data with {}: {}'.format(param_str, description)
        super(RequestError, self).__init__(msg)


class InterpolationError(Exception):
    """Exception raised for problems interpolating data."""
    def __init__(self, description):
        msg = 'Error interpolating data with: {}'.format(description)
        super(InterpolationError, self).__init__(msg)


class Logger:
    """Trivial class to output message to stdout respecting a quiet mode. Want per-level
    formatting which isn't really supported in python's logging module."""
    def __init__(self, quiet):
        self.quiet = quiet

    def warn(self, msg):
        """Output a warning message, which will be displayed even when quiet."""
        print('WARNING: ' + msg)

    def info(self, msg):
        """Output an info message, which will not be displayed when quiet."""
        if not self.quiet:
            print(msg)


def static_vars(**kwargs):
    """A decorator to declare static variables for a function."""
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate


def parse_time(timestamp):
    """Parses a string in the standard NOAA format to a datetime object."""
    return dt.datetime.strptime(timestamp, '%Y-%m-%d %H:%M').replace(tzinfo=TIMEZONE)


def round_to_minute(datetime):
    """Returns the supplied datetime.datetime rounded to the nearest minute."""
    return (datetime + dt.timedelta(seconds=30)).replace(second=0, microsecond=0)


def tide_sinusoidal_interpolate(highs_lows, start_time, end_time, interval):
    """Consumes an iterable of highs and lows as (datetime, 'H'/'L', value) tuples and generates
    a sequence of sinusoidally interpolated (time, value) tuples between start_date and end_date,
    with each point being a timedelta of interval apart."""
    if start_time > end_time:
        raise InterpolationError("start time was after end time")
    gen_time = start_time
    highs_lows_it = iter(highs_lows)
    try:
        (last_time, _, last_value) = next(highs_lows_it)
        (next_time, _, next_value) = next(highs_lows_it)
        while gen_time < end_time:
            if last_time >= next_time:
                raise InterpolationError("high_low data wasn't in ascending time order")
            if next_time < gen_time:
                # If the end of current hi_lo interval is earlier that the time we want to generate
                # skip forward to the next one.
                (last_time, last_value) = (next_time, next_value)
                (next_time, _, next_value) = next(highs_lows_it)
                continue
            # At this stage we know next_time is later than the time we want to generate and
            # last_time is earlier (or we wouldn't have moved past it), interpolation go brrrrrrr.
            time_step = (next_time - last_time)
            value_step = (next_value - last_value)
            time_fraction = (gen_time - last_time).total_seconds() / time_step.total_seconds()
            value_fraction = (math.cos(math.pi * (1 + time_fraction)) + 1) / 2
            yield (gen_time, last_value + value_fraction * value_step)
            gen_time += interval
    except StopIteration:
        return

def current_sinusoidal_interpolate(maxs_and_slacks, start_time, end_time, interval):
    """Consumes an iterable of maximums and approximate slacks as (datetime, value) tuples and
    generates a sequence of sinusoidally interpolated (time, value) tuples between start_date and
    end_date, with each point being a timedelta of interval apart."""
    if start_time > end_time:
        raise InterpolationError("start time was after end time")
    gen_time = start_time
    maxs_and_slacks_it = iter(maxs_and_slacks)
    try:
        (last_time, last_value) = next(maxs_and_slacks_it)
        (next_time, next_value) = next(maxs_and_slacks_it)
        while gen_time < end_time:
            if last_time >= next_time:
                raise InterpolationError("maxs_and_slacks data wasn't in ascending time order")
            if next_time < gen_time:
                # If the end of current hi_lo interval is earlier that the time we want to generate
                # skip forward to the next one.
                (last_time, last_value) = (next_time, next_value)
                (next_time, next_value) = next(maxs_and_slacks_it)
                continue
            # At this stage we know next_time is later than the time we want to generate and
            # last_time is earlier (or we wouldn't have moved past it), interpolation go brrrrrrr.
            time_step = (next_time - last_time)
            value_step = (next_value - last_value)
            time_fraction = (gen_time - last_time).total_seconds() / time_step.total_seconds()
            if abs(last_value) < 0.1:
                value_fraction = math.sin(math.pi * time_fraction/2)
            elif abs(next_value) < 0.1:
                value_fraction = 1 - math.cos(math.pi * time_fraction/2)
            else:
                raise InterpolationError(f"neither segment end slack: {last_value}, {next_value}")
            yield (gen_time, last_value + value_fraction * value_step)
            gen_time += interval
    except StopIteration:
        return


def find_highs_lows(periodic):
    """Consumes an iterable of perodic data as (datetime, value) tuples and generates a sequence
    of (time, 'H'/'L', value) tuples containing the maximums and minimums in the data. The first
    and last points are never eligible to be considered a maximum or minimum."""
    if len(periodic) < 3:
        return
    # Find if the range starts on ascending or descending.
    for i in range(1, len(periodic)):
        if periodic[0][1] != periodic[i][1]:
            ascending = periodic[i][1] > periodic[0][1]
            break
    # Now look for places where the following point will be a change in direction
    for i in range(1, len(periodic) - 1):
        if ascending and periodic[i+1][1] < periodic[i][1]:
            ascending = False
            yield (periodic[i][0], 'H', periodic[i][1])
        elif not ascending and periodic[i+1][1] > periodic[i][1]:
            ascending = True
            yield (periodic[i][0], 'L', periodic[i][1])


class TideStation:
    """A NOAA station used to gather tide predictions, and format options to display data."""
    def __init__(self, name, sid, color, line='-', annotate=False):
        self.name = name
        self.sid = sid
        self.color = color
        self.linestyle = line
        self.linewidth = 2.0 if annotate else 1.0
        self.annotate = annotate

    def params(self):
        """Returns paramaters to append to a query string to request data from this station."""
        return {'station': self.sid}

    def cache_key(self, start_date, end_date):
        """Returns a string suitable for use as a key when caching data for the station."""
        return '{}/{}/{}'.format(self.sid, start_date.isoformat(), end_date.isoformat())


class CurrentStation:
    """A NOAA station used to gather current predictions, and format options to display data."""
    def __init__(self, name, sid, sbin, color, line='-', annotate=False):
        self.name = name
        self.sid = sid
        self.sbin = sbin
        self.color = color
        self.linestyle = line
        self.linewidth = 2.0 if annotate else 1.0
        self.annotate = annotate

    def params(self):
        """Returns paramaters to append to a query string to request data from this station."""
        return {'station': self.sid, 'bin': self.sbin}

    def cache_key(self, start_date, end_date):
        """Returns a string suitable for use as a key when caching data for the station."""
        return '{}/{}/{}/{}'.format(self.sid, self.sbin,
                                    start_date.isoformat(), end_date.isoformat())


class DataSet:
    """A collection of places and a date range with the ability to query and return the
    corresponding NOAA tide and current predictions."""

    def __init__(self, location, abbr, begin_date, end_date, tide_stations, current_stations):
        self.location = location
        self.abbr = abbr
        self.begin_date = begin_date
        self.end_date = end_date
        begin_datetime = dt.datetime.combine(begin_date, dt.time.min).replace(tzinfo=TIMEZONE)
        end_datetime = dt.datetime.combine(end_date, dt.time.max).replace(tzinfo=TIMEZONE)

        self.tides = list()
        for station in tide_stations:
            # Unfortunately some tide stations don't support periodic estimates. Need to request
            # a wider range of high/low data so that we can interpolate ourselves
            extended_high_low = DataSet._get_high_low_tides(station, begin_date - ONE_DAY,
                                                            end_date + ONE_DAY)
            try:
                periodic = DataSet._get_periodic_tides(station, begin_date, end_date)
            except RequestError:
                DataSet.logger.warn(
                    'Falling back to tide interpolation for {}'.format(station.name))
                periodic = list(tide_sinusoidal_interpolate(extended_high_low, begin_datetime,
                                                            end_datetime, SIX_MIN))
            self.tides.append({
                'station': station,
                'high_low': [t for t in extended_high_low if begin_date <= t[0].date() <= end_date],
                'periodic': periodic,
            })
        self.currents = list()
        for station in current_stations:
            periodic = DataSet._get_periodic_currents(station, begin_date, end_date)
            if (periodic[1][0] - periodic[0][0]) / ONE_HOUR > 1.0:
                DataSet.logger.warn(
                    'Falling back to current interpolation for {}'.format(station.name))
                extended = DataSet._get_periodic_currents(station, begin_date - ONE_DAY,
                                                          end_date + ONE_DAY)
                periodic = list(current_sinusoidal_interpolate(extended, begin_datetime,
                                                               end_datetime, SIX_MIN))
            self.currents.append({
                'station': station,
                'high_low': list(find_highs_lows(periodic)),
                'periodic': periodic
            })
        self.astronomical_events = DataSet._get_astronomical_events(begin_date, end_date)
        self.moon_phases = DataSet._get_moon_phases(begin_date, end_date)

    def tide_limits(self, start_time, end_time):
        """Returns a tuple of the lowest and highest time between start_time and end_time for
        any station."""
        return (
            min(min((tup[1] for tup in tide['periodic'] if start_time < tup[0] <= end_time))
                for tide in self.tides),
            max(max((tup[1] for tup in tide['periodic'] if start_time < tup[0] <= end_time))
                for tide in self.tides))

    def current_limits(self, start_time, end_time):
        """Returns a tuple of the lowest and highest current between start_time and end_time for
        any station."""
        return (
            min(min((tup[1] for tup in current['periodic'] if start_time < tup[0] <= end_time))
                for current in self.currents),
            max(max((tup[1] for tup in current['periodic'] if start_time < tup[0] <= end_time))
                for current in self.currents))

    @staticmethod
    @static_vars(cache=dict())
    def _get_high_low_tides(station, begin_date, end_date):
        """Returns a list of (timestamp, H/L, height) tuples for the requested station. Provide
        explicit input date so that we can request the wider date range needed for interpolation."""
        params = dict(STANDARD_PARAMS)
        params['begin_date'] = begin_date.strftime("%Y%m%d")
        params['end_date'] = end_date.strftime("%Y%m%d")
        params['product'] = 'predictions'
        params['datum'] = 'MLLW'
        params['interval'] = 'hilo'
        params.update(station.params())

        cache_key = station.cache_key(begin_date, end_date)
        if cache_key in DataSet._get_high_low_tides.cache:
            return DataSet._get_high_low_tides.cache[cache_key]

        DataSet.logger.info('Fetching high/low tides for {}'.format(cache_key))
        resp = requests.get(BASE_URL, params=params)
        if resp.status_code != 200:
            raise RequestError(params, 'Non successful HTTP response {}'.format(resp.status_code))
        json_resp = resp.json()
        if 'predictions' not in json_resp:
            raise RequestError(params, 'No data in response: {}'.format(resp.text))
        result = [(parse_time(i['t']), i['type'], float(i['v'])) for i in json_resp['predictions']]
        DataSet._get_high_low_tides.cache[cache_key] = result
        return result

    @staticmethod
    @static_vars(cache=dict())
    def _get_periodic_tides(station, begin_date, end_date):
        """Returns a list of (timestamp, height) tuples for the requested station, with one
        datapoint every 6 minutes."""
        params = dict(STANDARD_PARAMS)
        params['begin_date'] = begin_date.strftime("%Y%m%d")
        params['end_date'] = end_date.strftime("%Y%m%d")
        params['product'] = 'predictions'
        params['datum'] = 'MLLW'
        params.update(station.params())

        cache_key = station.cache_key(begin_date, end_date)
        if cache_key in DataSet._get_periodic_tides.cache:
            return DataSet._get_periodic_tides.cache[cache_key]

        DataSet.logger.info('Fetching periodic tides for {}'.format(cache_key))
        resp = requests.get(BASE_URL, params=params)
        if resp.status_code != 200:
            raise RequestError(params, 'Non successful HTTP response {}'.format(resp.status_code))
        json_resp = resp.json()
        if 'predictions' not in json_resp:
            raise RequestError(params, 'No data in response: {}'.format(resp.text))
        result = [(parse_time(i['t']), float(i['v'])) for i in json_resp['predictions']]
        DataSet._get_periodic_tides.cache[cache_key] = result
        return result

    @staticmethod
    @static_vars(cache=dict())
    def _get_periodic_currents(station, begin_date, end_date):
        """Returns a list of (timestamp, velocity) tuples for the requested station, with one
        datapoint every 6 minutes."""
        params = dict(STANDARD_PARAMS)
        params['begin_date'] = begin_date.strftime("%Y%m%d")
        params['end_date'] = end_date.strftime("%Y%m%d")
        params['product'] = 'currents_predictions'
        params.update(station.params())

        cache_key = station.cache_key(begin_date, end_date)
        if cache_key in DataSet._get_periodic_currents.cache:
            return DataSet._get_periodic_currents.cache[cache_key]

        DataSet.logger.info('Fetching periodic currents for {}'.format(cache_key))
        resp = requests.get(BASE_URL, params=params)
        if resp.status_code != 200:
            raise RequestError(params, 'Non successful HTTP response {}'.format(resp.status_code))
        json_resp = resp.json()
        if 'current_predictions' not in json_resp:
            raise RequestError(params, 'No data in response: {}'.format(resp.text))
        result = [(parse_time(i['Time']), float(i['Velocity_Major']))
                  for i in json_resp['current_predictions']['cp']]
        DataSet._get_periodic_currents.cache[cache_key] = result
        return result

    @staticmethod
    def _get_astronomical_events(begin_date, end_date):
        """Returns a list of (local_datetime, body, event_type) tuples for the sun and moon within
        the supplied local date range."""
        # Astonomical events are always calculated for UTC days so may not contain everything in
        # the same local date. In the Western hemisphere the UTC day finishes earlier than ours so
        # add a day after, in the Eastern hemisphere add a day before.
        request_dates = [begin_date, end_date]
        if LOCATION.lng >= 0:
            request_dates[1] += dt.timedelta(days=1)
        else:
            request_dates[0] -= dt.timedelta(days=1)
        raw_events = (
            [(tup[0], 'sun', tup[1]) for tup
             in astronomy.Sun().events(request_dates[0], request_dates[1], LOCATION)] +
            [(tup[0], 'moon', tup[1]) for tup
             in astronomy.Moon().events(request_dates[0], request_dates[1], LOCATION)])
        rounded_events = [(round_to_minute(tup[0].astimezone(TIMEZONE)), tup[1], tup[2])
                          for tup in raw_events]
        filtered_events = [tup for tup in rounded_events if begin_date <= tup[0].date() <= end_date]
        filtered_events.sort(key=lambda tup: tup[0])
        return filtered_events

    @staticmethod
    def _get_moon_phases(begin_date, end_date):
        """Returns a list of (phase description, fraction illuminated) tuples describing the moon
        phase at midday on each day in the supplied local date range."""
        output = []
        moon = astronomy.Moon()
        request_time = dt.datetime.combine(begin_date, dt.time(12, 0, 0), tzinfo=TIMEZONE)
        while request_time.date() <= end_date:
            _, desc, fraction = moon.phase(request_time)
            output.append((desc, fraction))
            request_time += dt.timedelta(days=1)
        return output


def generate_tide_csv(dataset, path):
    """Creates a CSV file of the tide data in the supplied dataset at path."""
    with open(path, "w") as f:
        for tide in sorted(dataset.tides, key=lambda tide: tide['station'].name):
            station = tide['station'].name
            data = (tide['high_low'] +
                    [(tup[0], 'hour', tup[1]) for tup in tide['periodic'] if tup[0].minute == 0])
            for tup in data:
                # Fractional day as used by most spreadsheets.
                spreadsheet_day = (tup[0] - SPREADSHEET_ZERO_DATE).total_seconds() / SECONDS_PER_DAY
                f.write('{},{},{},{}\n'.format(station, tup[1], spreadsheet_day, tup[2]))


def generate_current_csv(dataset, path):
    """Creates a CSV file of the current data in the supplied dataset at path."""
    with open(path, "w") as f:
        for current in sorted(dataset.currents, key=lambda s: s['station'].name):
            station = current['station'].name
            data = [(tup[0], tup[1]) for tup in current['periodic']]
            for tup in data:
                # Fractional day as used by most spreadsheets.
                spreadsheet_day = (tup[0] - SPREADSHEET_ZERO_DATE).total_seconds() / SECONDS_PER_DAY
                f.write('{},{},{}\n'.format(station, spreadsheet_day, tup[1]))


def annotate_high_low(axes, text, datetime, high_low, height, color):
    """Annotates a high or low tide on the supplied axes, being smart about positioning."""
    delta_y = 8 if high_low == 'H' else -14
    alignment = ('left' if datetime.time() < dt.time(2, 0) else
                 'right' if datetime.time() > dt.time(22, 0) else
                 'center')
    axes.annotate(text, (datetime, height), zorder=100, color=color, ha=alignment,
                  xytext=(0, delta_y), textcoords='offset points', fontsize='small')


class Plot:
    """A visualization of a single date in a dataset, with the help of matplotlib."""

    def __init__(self, dataset, date):
        self.dataset = dataset
        self.date = date
        self.date_index = date.toordinal() - dataset.begin_date.toordinal()
        self.start_time = dt.datetime.combine(date, dt.time.min, tzinfo=TIMEZONE)
        self.end_time = dt.datetime.combine(date, dt.time.max, tzinfo=TIMEZONE)
        self.title = '{} Tides & Currents, {}'.format(
            self.dataset.location, self.date.strftime('%A %-d %B %Y'))
        self.properties = {
            'Title': self.title,
            'Author': "Jody Sankey's sf_tides_and_currents script, version {}".format(VERSION),
            'CreationDate': dt.datetime.today()
        }

    @staticmethod
    def set_defaults():
        """Sets global matplotlib properties suitable for a PDF output."""
        #print(matplotlib.rcParams.keys())
        matplotlib.rcParams['legend.fontsize'] = 'x-small'
        matplotlib.rcParams['legend.loc'] = 'lower left'
        matplotlib.rcParams['xtick.labelsize'] = 'small'
        matplotlib.rcParams['ytick.labelsize'] = 'small'

    @staticmethod
    def _z_order(inp):
        """Returns a range suitable for painting some input range from front to back."""
        return range(len(inp)+10, 10, -1)

    def plot_tides(self, axes):
        """Plots the tide data using the supplied Matplotlib axes, formatting that is common to
        tides and currents is performed outside this method."""
        (min_tide, max_tide) = self.dataset.tide_limits(self.start_time, self.end_time)
        for tide, zorder in zip(self.dataset.tides, Plot._z_order(self.dataset.tides)):
            station = tide['station']
            # Optionally plot and annotate high and low markers.
            if station.annotate:
                high_low = [tup for tup in tide['high_low']
                            if self.start_time <= tup[0] <= self.end_time]
                axes.plot([tup[0] for tup in high_low],
                          [tup[2] for tup in high_low],
                          zorder=zorder, marker='o', linestyle='', color=station.color)
                for tup in high_low:
                    text = '{:.2f} @ {}'.format(tup[2], tup[0].strftime('%H%M'))
                    annotate_high_low(axes, text, tup[0], tup[1], tup[2], station.color)
            # Plot a line for the periodic data
            periodic = [tup for tup in tide['periodic']
                        if self.start_time <= tup[0] <= self.end_time]
            axes.plot([tup[0] for tup in periodic],
                      [tup[1] for tup in periodic],
                      zorder=zorder, linestyle=station.linestyle, linewidth=station.linewidth,
                      color=station.color, label=textwrap.fill(station.name, 18))

        axes.set_ylabel('Height above MLLW (ft)')
        axes.set_ylim(math.floor(min_tide - 0.5), math.ceil(max_tide + 0.5))
        axes.yaxis.set_major_locator(matplotlib.ticker.FixedLocator([0]))
        axes.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
        axes.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
        axes.yaxis.set_minor_formatter(matplotlib.ticker.ScalarFormatter())

    def plot_currents(self, axes):
        """Plots the current data using the supplied Matplotlib axes."""
        def unsigned(value, _):
            """A function to format current ticks without sign."""
            return '{:.0f}'.format(abs(value))

        (min_current, max_current) = self.dataset.current_limits(self.start_time, self.end_time)
        for current, zorder in zip(self.dataset.currents, Plot._z_order(self.dataset.currents)):
            station = current['station']
            # Optionally plot and annotate high and low markers.
            if station.annotate:
                high_low = [tup for tup in current['high_low']
                            if self.start_time <= tup[0] <= self.end_time]
                axes.plot([tup[0] for tup in high_low],
                          [tup[2] for tup in high_low],
                          zorder=zorder, marker='o', linestyle='', color=station.color)
                for tup in high_low:
                    text = '{:.1f}{} @ {}'.format(abs(tup[2]), 'F' if tup[1] == 'H' else 'E',
                                                  tup[0].strftime('%H%M'))
                    annotate_high_low(axes, text, tup[0], tup[1], tup[2], station.color)

            # Plot a line for the periodic data.
            periodic = [tup for tup in current['periodic']
                        if self.start_time <= tup[0] <= self.end_time]
            axes.plot([tup[0] for tup in periodic],
                      [tup[1] for tup in periodic],
                      zorder=zorder, linestyle=station.linestyle, linewidth=station.linewidth,
                      color=station.color, label=textwrap.fill(station.name, 18))

        axes.set_ylabel('Ebb (kt)                Flood(kt)')
        axes.set_ylim(math.floor(min_current - 0.5), math.ceil(max_current + 0.5))
        axes.yaxis.set_major_locator(matplotlib.ticker.FixedLocator([0]))
        axes.yaxis.set_major_formatter(matplotlib.ticker.FixedFormatter(['slack']))
        axes.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
        axes.yaxis.set_minor_formatter(matplotlib.ticker.FuncFormatter(unsigned))

    def add_titles(self):
        """Add a title block to the current figure."""
        title_left = MARGIN / LETTER_W
        title_top = (LETTER_H - TOP_MARGIN) / LETTER_H
        subtitle = '{}. NOAA data gathered {}'.format(
            self.properties['Author'], self.properties['CreationDate'].strftime('%Y-%m-%d'))
        plt.figtext(title_left, title_top, self.title,
                    va='top', fontsize='large', fontweight='bold')
        plt.figtext(title_left, title_top - 0.025, subtitle,
                    va='top', fontsize='x-small', color='#cccccc')

    def add_astronomical_data(self):
        """Adds sun and moon data to the current figure."""
        heading_top = (LETTER_H - TOP_MARGIN) / LETTER_H - 0.014
        value_top = heading_top - 0.006
        leftmost_event = 6 / LETTER_W
        x_step = 0.55 / LETTER_W
        moon_phase_x = 9.6 / LETTER_W

        # Rise, transit, and set events.
        today_events = (evt for evt in self.dataset.astronomical_events
                        if self.start_time <= evt[0] < self.end_time)
        for evt, idx in zip(today_events, range(6)):
            heading = '{}{}{}'.format(evt[1], '\n' if evt[2] == 'transit' else '', evt[2])
            value = '{}'.format(evt[0].strftime('%H%M'))
            color = BLUE if evt[1] == 'moon' else 'black'
            x_pos = leftmost_event + idx * x_step
            plt.figtext(x_pos, heading_top, heading, va='bottom', color=color, fontsize='x-small')
            plt.figtext(x_pos, value_top, value, va='top', color=color, fontsize='medium')

        # Moon phase information
        moon_desc, moon_fraction = self.dataset.moon_phases[self.date_index]
        plt.figtext(moon_phase_x, heading_top, 'moon phase',
                    va='bottom', color=BLUE, fontsize='x-small')
        plt.figtext(moon_phase_x, value_top, textwrap.fill(moon_desc, 8),
                    va='top', color=BLUE, fontsize='medium')
        plt.figtext(moon_phase_x, heading_top - 0.07, 'illumination',
                    va='bottom', color=BLUE, fontsize='x-small')
        plt.figtext(moon_phase_x, value_top - 0.07, '{:.0f}%'.format(moon_fraction * 100.0),
                    va='top', color=BLUE, fontsize='medium')

    def create_figure(self):
        """Plots the tide and current data as a new figure, heavily optimized to print nicely using
        PDF on a letter paper."""
        fig = plt.figure(dpi=300)
        fig.set_size_inches(LETTER_W, LETTER_H)
        fig.tight_layout()

        # Create the subplots, each with its own y-axis formatting
        tide_axes = plt.subplot(211)
        current_axes = plt.subplot(212)
        self.plot_tides(tide_axes)
        self.plot_currents(current_axes)

        # Manually position the axes, adding padding to account for the axis ticks, labels, and
        # titles that fall outside the rectangle used for positioning.
        axes_left_pad, axes_bottom_pad = 0.35, 0.4
        axes_width, axes_height = 0.75, 0.35
        axes_left = (MARGIN + axes_left_pad) / LETTER_W
        axes_bottoms = [(MARGIN + axes_bottom_pad) / LETTER_H,
                        (1.5 * MARGIN + 2 * axes_bottom_pad) / LETTER_H + axes_height]
        current_axes.set_position([axes_left, axes_bottoms[0], axes_width, axes_height])
        tide_axes.set_position([axes_left, axes_bottoms[1], axes_width, axes_height])

        # Apply formatting that is common between the two subplots
        for axes in (tide_axes, current_axes):
            axes.yaxis.set_label_coords(-0.03, 0.5)
            axes.set_xlim(self.start_time, self.end_time)
            axes.xaxis.set_minor_locator(matplotlib.dates.HourLocator())
            axes.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=3))
            axes.xaxis.set_minor_formatter(matplotlib.dates.DateFormatter('%H%M', tz=TIMEZONE))
            axes.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H%M', tz=TIMEZONE))
            axes.tick_params(which='both', axis='x', length=4, labelrotation=90)
            axes.tick_params(which='both', axis='y', right=True, labelright=True)
            axes.grid(which='minor', axis='both', linestyle='-', color='#cccccc')
            axes.grid(which='major', axis='both', linestyle='-', color='#666666')
            axes.legend(bbox_to_anchor=(1.04, -0.05), borderaxespad=0., frameon=False)

        # Add title and sun/moon information
        self.add_titles()
        self.add_astronomical_data()

    def filename(self):
        """Returns a descriptive filename for saving this figure."""
        return '{}_tides_currents_{}.pdf'.format(self.dataset.abbr, self.date.strftime('%Y%m%d'))


def parse_locations(file_path):
    """Parses a csv file at the supplied path defining a set of tide and current locations and
    line styles for plotting them, returning lists of tide and current stations.

    Each line in the file must contain 7 comma seperated lines as follows:
      1 = 'tide' or 'current'
      2 = A human readable description of the location
      3 = NOAA tide or current station ID
      4 = bin number for a current station or empty for tide stations
      5 = Line color as a six character hex RGB string
      6 = Line style as one of: '-', '--', '-.', ':', 'solid', 'dashed', 'dashdot', 'dotted'
      7 = 'annotate' if the highs and lows are to be annotated.

    Empty lines and lines that start with # are ignored.

    For example a valid line may be:
      tide,San Francisco,9414290,,000000,dotted,annotate
    """
    tides = []
    currents = []
    try:
        f = open(file_path, 'r')
    except OSError:
        print(f'Location file could not be opened {file_path}')
        sys.exit(1)

    with f:
        for line in f.readlines():
            if len(line.strip()) == 0 or line.startswith('#'):
                continue
            elements = line.split(',')
            if len(elements) != 7:
                print(f'Location file line did not contain 7 elements: {line}')
                sys.exit(1)
            annotate = (elements[6].strip() == 'annotate')
            if elements[0].strip() == 'tide':
                tides.append(TideStation(
                    name=elements[1], sid=elements[2],
                    color=('#'+elements[4]), line=elements[5], annotate=annotate))
            elif elements[0].strip() == 'current':
                currents.append(CurrentStation(
                    name=elements[1], sid=elements[2], sbin=elements[3],
                    color=('#'+elements[4]), line=elements[5], annotate=annotate))
    return (tides, currents)


# Define selectable sets of tide and current stations, maps available at:
# https://tidesandcurrents.noaa.gov/map/index.html
# https://tidesandcurrents.noaa.gov/map/index.html?type=CurrentPredictions
LOCATIONS = {
    'test' : {
        'name': 'SF Bay',
        'description': 'Cruising in the Central Bay',
        'tide_stations': [
            TideStation('San Francisco', 9414290, 'black', annotate=True),
        ],
        'current_stations': [
            CurrentStation('0.46nm E of Golden Gate (30ft)', 'SFB1203', 18, 'black', annotate=True),
        ]
    },
    'bay' : {
        'name': 'SF Bay',
        'description': 'Cruising in the Central Bay',
        'tide_stations': [
            TideStation('San Francisco', 9414290, 'black', annotate=True),
            TideStation('Richmond', 9414863, GREEN),
            TideStation('Alameda NAS', 9414750, PURPLE),
            TideStation('San Leandro', 9414688, RED),
        ],
        'current_stations': [
            CurrentStation('0.46nm E of Golden Gate (30ft)', 'SFB1203', 18, 'black', annotate=True),
            CurrentStation('Point San Pablo, midchannel (11ft)', 'SFB1312', 16, GREEN),
            CurrentStation('Racoon Strait (19ft)', 'SFB1212', 9, BLUE),
            CurrentStation('Bay Bridge B-C span (11ft)', 'SFB1208', 24, PURPLE),
            CurrentStation('1.6nm SE of Hunters Point (5ft)', 'SFB1308', 7, RED),
        ]
    },
    'delta' : {
        'name': 'Delta',
        'description': 'Cruises towards Benecia and the Delta',
        'tide_stations': [
            TideStation('San Francisco', 9414290, 'black', annotate=True),
            TideStation('Richmond', 9414863, GREEN),
            TideStation('Mare Island', 9415218, BLUE),
            TideStation('Benicia', 9415111, PURPLE),
            TideStation('Pittsburg', 9415096, RED),
        ],
        'current_stations': [
            CurrentStation('0.46nm E of Golden Gate (30ft)', 'SFB1203', 18, 'black', annotate=True),
            CurrentStation('Point San Pablo, midchannel (11ft)', 'SFB1312', 16, GREEN),
            CurrentStation('Carquinez Strait (12ft)', 'SFB1319', 10, BLUE, annotate=True),
            CurrentStation('Martinez-AMORCO (15ft)', 's06010', 16, PURPLE),
            CurrentStation('New York Slough (5ft)', 'SFB1326', 9, RED),
        ]
    },
    'coastal' : {
        'name': 'Coastal',
        'description': 'Cruises heading outside the Golden Gate',
        'tide_stations': [
            TideStation('San Francisco', 9414290, 'black', annotate=True),
            TideStation('Point Reyes', 9415020, GREEN),
            TideStation('Pillar Point Harbor', 9414131, BLUE),
            TideStation('Santa Cruz', 9413745, PURPLE),
            TideStation('Monterey', 9413450, RED),
        ],
        'current_stations': [
            CurrentStation('SF Bay Entrance (19ft)', 'SFB1201', 26, 'black', annotate=True),
            CurrentStation('SF Bar (5ft)', 'SFB1221', 7, 'black', line='dashed'),
            CurrentStation('0.95nm SSE of Pt Bonita (17ft)', 'SFB1220', 13, GREEN),
            CurrentStation('0.46nm E of Golden Gate (30ft)', 'SFB1203', 18, BLUE),
        ]
    },
}


# Define a fixed set of stations used for the anchoring CSV output. Color is not used.
ANCHOR_STATIONS = [
    TideStation('San Francisco', 9414290, 'black'),
    TideStation('Point Reyes', 9415020, 'black'),
    TideStation('Pillar Point Harbor', 9414131, 'black'),
    TideStation('Sausalito', 9414806, 'black'),
    TideStation('Santa Cruz', 9413745, 'black'),
    TideStation('Monterey', 9413450, 'black'),
]

# Define a fixed set of stations used for the current CSV output. Color is not used.
CURRENT_STATIONS = [
    CurrentStation('SF Bay Entrance (19ft)', 'SFB1201', 26, 'black'),
    CurrentStation('SF Bar (5ft)', 'SFB1221', 7, 'black'),
    CurrentStation('0.95nm SSE of Pt Bonita (17ft)', 'SFB1220', 13, 'black'),
    CurrentStation('0.46nm E of Golden Gate (30ft)', 'SFB1203', 18, 'black'),
    CurrentStation('3.7nm W of Pt Lobos (46 ft)', 'PCT0191', 1, 'black'),
    CurrentStation('0.2nm SE of Pt Diablo (?? ft)', 'PCT0251', 1, 'black'),
    CurrentStation('0.4nm SSE of Pt Bonita (43 ft)', 'PCT0236', 1, 'black'),
    CurrentStation('0.3nm W of Fort Point (75 ft)', 'PCT0261', 1, 'black'),
    CurrentStation('0.2nm NW of Mile Rock (15 ft)', 'PCT0246', 1, 'black'),
]

# Additional stations not currently used.
#        TideStation('Berkeley', 9414816, '#e74c3c'),
#        TideStation('Redwood City', 9414523, '#3498db'),
#        CurrentStation('0.5nm N of Alcatraz (6ft)', 'SFB1211', 22, '#e67e22'),

def create_parser():
    """Creates the definition of the expected command line flags."""
    class SmartFormatter(argparse.HelpFormatter):
        """Trivial formatter to wrap strings beginning with `R|` using their embedded line feeds."""
        def _split_lines(self, text, width):
            if text.startswith('R|'):
                return text[2:].splitlines()
            # this is the RawTextHelpFormatter._split_lines
            return argparse.HelpFormatter._split_lines(self, text, width)

    def _parse_date(date_str):
        if date_str == 'today':
            return dt.date.today()
        if date_str == 'tomorrow':
            return dt.date.today() + ONE_DAY
        if re.match(r'^\d{8}$', date_str):
            return dt.date.fromisoformat('{}-{}-{}'.format(
                date_str[:4], date_str[4:6], date_str[6:]))
        return dt.date.fromisoformat(date_str)

    parser = argparse.ArgumentParser(
        description='Script to plot NOAA tide and current data for SF Bay area along with basic '
                    'information for the sun and moon.',
        epilog='Copyright Jody Sankey 2020-2022',
        formatter_class=SmartFormatter)
    parser.add_argument('-o', '--output_dir', action='store', metavar='DIR',
                        default=tempfile.gettempdir(), help="Directory for output files.")
    parser.add_argument('-f', '--output_file', action='store', metavar='OUT_FILE',
                        default=None, help="Output filename. If absent a sensible default will "
                                           "be derived from date and location")
    parser.add_argument('-u', '--unify', action='store_true',
                        help="Combine all plots into a single PDF output file.")
    parser.add_argument('-d', '--date', action='store', metavar='YYYY-MM-DD', required=True,
                        type=_parse_date,
                        help="First date to calculate, e.g. 2020-12-15 for Christmas 2020. "
                             "'today' and 'tomorrow' are also accepted.")
    parser.add_argument('-n', '--num_days', action='store', default=1, type=int,
                        help="Number of days to calculate, defaults to 1. A separate plot will "
                             "be generated for each day.")
    parser.add_argument('-l', '--location', action='append',
                        choices=LOCATIONS.keys(),
                        help="R|Sets of tide and current stations to include:\n" +
                        "\n".join(['  {} - {}'.format(k, LOCATIONS[k]['description'])
                                   for k in LOCATIONS]) +
                        "\nMay be supplied multiple times for multiple locations.")
    parser.add_argument('-i', '--location_input', action='store', metavar='IN_FILE',
                        help="Comma separated file of locations and line colors as described in "
                             "the parse_locations function.")
    parser.add_argument('-a', '--anchor', action='store_true',
                        help="Output a CSV file of tides at standard anchoring locations.")
    parser.add_argument('-c', '--currents', action='store_true',
                        help="Output a CSV file of currents at standard current locations.")
    parser.add_argument('-q', '--quiet', action='store_true',
                        help="Don't print output for successful operations.")
    return parser


def main():
    """Executes the script using command line arguments."""
    args = create_parser().parse_args()
    start_date = args.date
    end_date = start_date + dt.timedelta(days=args.num_days-1)
    logger = Logger(args.quiet)

    DataSet.logger = logger
    locations = args.location if args.location else []
    try:
        datasets = [DataSet(LOCATIONS[loc]['name'],
                            loc, start_date, end_date,
                            LOCATIONS[loc]['tide_stations'],
                            LOCATIONS[loc]['current_stations']) for loc in locations]
    except RequestError as err:
        print(err)
        sys.exit(1)
    if args.location_input:
        tides, currents = parse_locations(args.location_input)
        datasets.append(DataSet('', 'custom', start_date, end_date,
                                tides, currents))

    Plot.set_defaults()
    dates = [start_date + dt.timedelta(days=i) for i in range(args.num_days)]
    date_range_str = '{}_to_{}'.format(start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d'))
    plots = [Plot(dataset, date) for date in dates for dataset in datasets]

    if args.unify:
        file = args.output_file or '{}_tides_currents_{}.pdf'.format(
            '_'.join(locations), date_range_str)
        path = os.path.join(args.output_dir, file)
        title = '{} Tides & Currents, {} to {}'.format(
            ', '.join([d.location for d in datasets]),
            start_date.strftime('%A %-d %B %Y'),
            end_date.strftime('%A %-d %B %Y'))
        pdf_pages = PdfPages(path)
        for plot in plots:
            plot.create_figure()
            pdf_pages.savefig()
        pdf_pages.infodict().update(plots[0].properties)
        pdf_pages.infodict()['Title'] = title
        pdf_pages.close()
        logger.info('Wrote ' + path)
    else:
        for plot in plots:
            plot.create_figure()
            # Use the command line argument filename, but only if there is a single output file.
            file = args.output_file if args.output_file and len(plots) == 1 else plot.filename()
            path = os.path.join(args.output_dir, file)
            plt.savefig(path, format='pdf', metadata=plot.properties)
            logger.info('Wrote ' + path)
    if args.anchor:
        dataset = DataSet('anchoring', 'anchoring', start_date, end_date, ANCHOR_STATIONS, [])
        path = os.path.join(args.output_dir, 'anchoring_{}.csv'.format(date_range_str))
        generate_tide_csv(dataset, path)
        logger.info('Wrote ' + path)
    if args.currents:
        dataset = DataSet('currents', 'currents', start_date, end_date, [], CURRENT_STATIONS)
        path = os.path.join(args.output_dir, 'currents_{}.csv'.format(date_range_str))
        generate_current_csv(dataset, path)
        logger.info('Wrote ' + path)


if __name__ == '__main__':
    main()
