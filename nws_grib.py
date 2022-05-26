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


class DataProduct:
    """A representation of NOAA weather data product, able to make requests for data."""
    def __init__(self, base_url, dir_fn, file_fn, out_prefix, interval, levels, variables):
        self.base_url = base_url
        self.dir_fn = dir_fn
        self.file_fn = file_fn
        self.out_prefix = out_prefix
        self.interval = interval
        self.levels = levels
        self.variables = variables

    def _make_params(self, forecast_time, forecast_hour, args):
        """Constructs a URL paramater dictionary for the requested forecast time and an hour in
        that forecast."""
        basics = {
            'file': self.file_fn(forecast_time, forecast_hour),
            'dir': self.dir_fn(forecast_time),
            'subregion': '',
            'leftlon': args.min_lon,
            'rightlon': args.max_lon,
            'toplat': args.max_lat,
            'bottomlat': args.min_lat,
        }
        levels = {'lev_{}'.format(l): 'on' for l in self.levels}
        variables = {'var_{}'.format(v): 'on' for v in self.variables}
        return {**basics, **levels, **variables}

    def request_forecast(self, forecast_time, forecast_hour, args):
        """Requests the URL for the requested time and forecast, printing an info message
        beforehand."""
        print('Requesting {} data for {}, forecast hour {}'.format(
            self.out_prefix, forecast_time.strftime('%Y%m%d %HZ'), forecast_hour))
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
        return forecast_time.strftime(self.out_prefix + '_%Y%m%d_%Hz.grb2')


PRODUCTS = {
    'GFS': DataProduct(
        base_url=r'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl',
        dir_fn=lambda time: r'/gfs.{}/{:02d}/atmos'.format(time.strftime('%Y%m%d'), time.hour),
        file_fn=lambda time,hour: r'gfs.t{:02d}z.pgrb2.0p25.f{:03d}'.format(time.hour, hour),
        out_prefix=r'gfs_0p25',
        interval=6,
        levels=[
            'surface',
            'mean_sea_level',
            '2_m_above_ground', # Used for air temperature
            '10_m_above_ground', # Used for surface wind
            'entire_atmosphere', # Used for cloud cover
            '500_mb',
        ],
        variables=[
            'UGRD',  # U component of wind
            'VGRD',  # V component of wind
            'GUST',  # Wind gust
            'PRMSL', # Pressure (for surface) [Not available in HRRR]
            'HGT',   # Geopotential height (for 500mb)
            'TMP',   # Temperature
            'PRATE', # Precipitation rate
            'VIS',   # Visibility
            'TCDC',  # Total cloud cover
        ]),
    'GFSwavewcoast': DataProduct(
        base_url=r'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfswave.pl',
        dir_fn=lambda time: r'/gfs.{}/{:02d}/wave/gridded'.format(
            time.strftime('%Y%m%d'), time.hour),
        file_fn=lambda time,hour: r'gfswave.t{:02d}z.wcoast.0p16.f{:03d}.grib2'.format(
            time.hour, hour),
        out_prefix=r'wave_wcoast_0p16',
        interval=6,
        levels=['surface'],
        variables=[
            'HTSGW',  # Significant wave height
            'WVDIR',  # Wind wave direction
            'WVPER',  # Wind wave period
        ]),
    # Unfortunately HRRR isn't usable yet. zxgrib entirely fails to display any grib from HRRR
    # while OpenCPN displays moderately beleivable data but on the wrong place on the map.
    'HRRR': DataProduct(
        base_url=r'https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl',
        dir_fn=lambda time: r'/hrrr.{}/conus'.format(time.strftime('%Y%m%d')),
        file_fn=lambda time,hour: r'hrrr.t{:02d}z.wrfsfcf{:02d}.grib2'.format(time.hour, hour),
        out_prefix=r'hrrr_conus',
        interval=1,
        levels=[
            'surface',
            'mean_sea_level',
            '2_m_above_ground', # Used for air temperature
            '10_m_above_ground', # Used for surface wind
            'entire_atmosphere', # Used for cloud cover
            '500_mb',
        ],
        variables=[
            'UGRD',  # U component of wind
            'VGRD',  # V component of wind
            'GUST',  # Wind gust
            #'PRMSL', # Pressure (for surface) [Not available in HRRR]
            'HGT',   # Geopotential height (for 500mb)
            'TMP',   # Temperature
            'PRATE', # Precipitation rate
            'VIS',   # Visibility
            'TCDC',  # Total cloud cover
        ]),
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
    for product in [PRODUCTS[name] for name in ['GFS', 'GFSwavewcoast']]:
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
