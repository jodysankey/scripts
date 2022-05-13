#!/bin/python3

"""Script to gather a subset of the current NWS GFS model in a
single GRIB2 file. Run with --help to see command line options."""

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
import math
import os.path
import time
import sys
import tempfile

import requests


LEVELS = [
    'surface',
    'mean_sea_level',
    '10_m_above_ground', # Used for surface wind
    'entire_atmosphere', # Used for cloud cover
    '500_mb',
]

VARIABLES = [
    'UGRD',  # U component of wind
    'VGRD',  # V component of wind
    'GUST',  # Wind gust
    'PRMSL',  # Pressure (for surface) [Not available in HRRR]
    'HGT',   # Geopotential height (for 500mb)
    'TMP',  # Temperature
    'PRATE', # Precipitation rate
    'VIS',   # Visibility
    'TCDC',  # Total cloud cover
]


class DataProduct:
    """A representation of NOAA weather data product, able to make requests for data."""
    def __init__(self, base_url, dir_param, file_param, output_prefix, interval):
        self.base_url = base_url
        self.dir_param = dir_param
        self.file_param = file_param
        self.output_prefix = output_prefix
        self.interval = interval

    def _make_params(self, forecast_time, forecast_hour, args):
        """Constructs a URL param dictionary for the requested time and forecast."""
        basics = {
            'file': self.file_param.format(forecast_time.hour, forecast_hour),
            'dir': self.dir_param.format(forecast_time.strftime('%Y%m%d'), forecast_time.hour),
            'subregion': '',
            'leftlon': args.min_lon,
            'rightlon': args.max_lon,
            'toplat': args.max_lat,
            'bottomlat': args.min_lat,
        }
        levels = {'lev_{}'.format(l): 'on' for l in LEVELS}
        variables = {'var_{}'.format(v): 'on' for v in VARIABLES}
        return {**basics, **levels, **variables}

    def request_forecast(self, forecast_time, forecast_hour, args):
        """Requests the URL for the requested time and forecast, printing an info message
        beforehand."""
        print('Requesting data for {}, forecast hour {}'.format(
            forecast_time.strftime('%Y%m%d %HZ'), forecast_hour))
        return requests.get(self.base_url,
                            params=self._make_params(forecast_time, forecast_hour, args))

    def get_most_recent_cycle_time(self):
        """Returns the most recent UTC datetime who's hour is a multiple of the interval."""
        cycle_time = dt.datetime.utcnow()
        hour = self.interval * math.floor(cycle_time.hour / self.interval)
        return cycle_time.replace(hour=hour, minute=0, second=0, microsecond=0)

    def get_previous_cycle_time(self, cycle_time):
        """Returns a UTC datetime one interval before the supplied datatime."""
        return cycle_time - dt.timedelta(hours=self.interval)

    def filename(self, forecast_time):
        """Returns a convenient string for the supplied forecast datetime."""
        return forecast_time.strftime(self.output_prefix + '%Y%m%d_%Hz.grb2')


PRODUCTS = {
    'GFS': DataProduct(
        r'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl',
        r'/gfs.{}/{}/atmos',
        r'gfs.t{:02d}z.pgrb2.0p25.f{:03d}',
        r'gfs_0p25_',
        6),
    # Unfortunately HRRR isn't usable yet. zxgrib entirely fails to display the any grib from HRRR
    # while OpenCPN displays moderately beleivable data but on the wrong place on the map.
    'HRRR': DataProduct(
        r'https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl',
        r'/hrrr.{}/conus', # Note doesn't contain an hour, gonna need to do something different.
        r'hrrr.t{:02d}z.wrfsfcf{:02d}.grib2',
        r'hrrr_conus_',
        1),
}


def create_parser():
    """Creates the definition of the expected command line flags."""
    parser = argparse.ArgumentParser(
        description='Script to collect NOAA GRIB data for only interesting variables and a limited '
                    'geographical range',
        epilog='Copyright Jody Sankey 2022')
    parser.add_argument('-o', '--output_dir', action='store', metavar='DIR',
                        default=tempfile.gettempdir(), help="Directory for output file.")
    parser.add_argument('-d', '--duration', action='store', default=48, type=int, metavar='HOURS',
                        help="Time range to collect (this range starts at model run time, not "
                             "current time).")
    parser.add_argument('-i', '--interval', action='store', default=1, type=int, metavar='HOURS',
                        help="Number of hours between collected datasets.")
    parser.add_argument('-s', '--sleep', action='store', default=500, type=int, metavar='MS',
                        help="Number of milliseconds to sleep between requests to avoid DoS.")
    parser.add_argument('--min_lat', action='store', default=34, type=int, metavar='DEGREES',
                        help="Minimum latitude to collect data for, positive for North.")
    parser.add_argument('--max_lat', action='store', default=41, type=int, metavar='DEGREES',
                        help="Maximum latitude to collect data for, positive for North.")
    parser.add_argument('--min_lon', action='store', default=-127, type=int, metavar='DEGREES',
                        help="Minimum longitude to collect data for, positive for East.")
    parser.add_argument('--max_lon', action='store', default=-120, type=int, metavar='DEGREES',
                        help="Maximum longitude to collect data for, positive for East.")
    return parser


def main():
    """Executes the script using command line arguments."""
    args = create_parser().parse_args()
    product = PRODUCTS['GFS'] # Because HRRR doesn't work yet
    forecast_time = product.get_most_recent_cycle_time()
    resp = product.request_forecast(forecast_time, 0, args)

    # If the server doesn't have this most recent time yet, backoff to the previous time
    if resp.status_code == 404:
        print('Not found, backing off one interval')
        forecast_time = product.get_previous_cycle_time(forecast_time)
        resp = product.request_forecast(forecast_time, 0, args)

    # If neither succeeded just quit.
    if resp.status_code != 200:
        sys.exit('HTTP response code {}'.format(resp.status_code))

    # Write this first response and a set of additional forecast hours to file.
    filepath = os.path.join(args.output_dir, product.filename(forecast_time))
    with open(filepath, 'wb') as file:
        file.write(resp.content)
        for forecast_hour in range(1, args.duration, args.interval):
            resp = product.request_forecast(forecast_time, forecast_hour, args)
            if resp.status_code != 200:
                sys.exit('HTTP response code {}'.format(resp.status_code))
            file.write(resp.content)
            time.sleep(args.sleep / 1000.0)
        print('Wrote {}'.format(filepath))


if __name__ == '__main__':
    main()
