#!/usr/bin/python3

"""Script to verify a sun sight and the location calculated from it
given an accurate DR position. Run with --help to see the command
line options."""

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
import bisect
import datetime as dt
from math import trunc, sin, cos, asin, acos, copysign, pi
import os.path
import sys

from astronomy import Sun, RAD_TO_DEG, DEG_TO_RAD, datetime_to_ut, ut_to_dt, greenwich_sidereal_time


TEXT_WIDTH = 22
DATA_WIDTH = 15

FT_PER_M = 3.281

class LookupTable:
    """A table of one ordered floating point value (x) to another (y)."""
    def __init__(self, data):
        self.data = data

    def lookup(self, value):
        """Returns the y value with x closest to but not greater than the supplied value."""
        i = bisect.bisect_right(self.data, (value,))
        if abs(self.data[i][0] - value) < 0.001:
            # Close enough to return this point
            return self.data[i][1]
        # Return the previous point
        return self.data[i-1][1]


# A table of eye height in feet to dip angle in degrees. We could get an equation thats
# very close but for now we want to use the identical values to the almanac.
HEIGHT_TO_DIP = LookupTable((
    (2.0, -1.4),
    (3.0, -1.7),
    (4.0, -1.9),
    (5.0, -2.2),
    (6.0, -2.4),
    (7.0, -2.6),
    (8.0, -2.8),
    (8.6, -2.9),
    (9.2, -3.0),
    (9.8, -3.1),
    (10.5, -3.2),
    (11.2, -3.3),
    (11.9, -3.4),
    (12.6, -3.5),
    (13.3, -3.6),
    (14.1, -3.7),
    (14.9, -3.8),
    (15.7, -3.9),
    (16.5, -4.0),
    (17.4, -4.1),
    (18.3, -4.2),
    (19.1, -4.3),
    (20.1, -4.4),
    (21.0, -4.5),
    (22.0, -4.6),
    (22.9, -4.7),
    (23.9, -4.8),
    (24.9, -4.9),
    (26.0, -5.0),
    (27.1, -5.1),
    (28.1, -5.2),
    (29.2, -5.3),
    (30.4, -5.4),
    (31.5, -5.5),
    (32.7, -5.6),
    (33.9, -5.7),
    (35.1, -5.8),
    (36.3, -5.9),
    (37.6, -6.0),
    (38.9, -6.1),
    (40.1, -6.2),
    (41.5, -6.3),
    (15.0, -6.4),
    (44.2, -6.5),
    (45.5, -6.6),
    (46.9, -6.7),
    (48.4, -6.8),
    (49.8, -6.9),
    (51.3, -7.0),
    (52.8, -7.1),
    (54.3, -7.2),
    (55.8, -7.3),
    (57.4, -7.4),
    (58.9, -7.5),
    (60.5, -7.6),
    (62.1, -7.7),
    (63.8, -7.8),
    (65.4, -7.9),
    (67.1, -8.0),
    (68.8, -8.1),
    (70.5, -8.2),
),)

SUMMER_SUN_CORRECTION = LookupTable((
    (9.6500, 10.6),
    (9.8333, 10.7),
    (10.0333, 10.8),
    (10.2333, 10.9),
    (10.4500, 11.0),
    (10.6667, 11.1),
    (10.8833, 11.2),
    (11.1167, 11.3),
    (11.3667, 11.4),
    (11.6167, 11.5),
    (11.8833, 11.6),
    (12.1667, 11.7),
    (12.4500, 11.8),
    (14.7500, 11.9),
    (13.0667, 12.0),
    (13.4000, 12.1),
    (13.7333, 12.2),
    (14.1000, 12.3),
    (14.4833, 12.4),
    (14.8833, 12.5),
    (15.3000, 12.6),
    (15.7500, 12.7),
    (16.2167, 12.8),
    (16.7167, 12.9),
    (17.2333, 13.0),
    (17.7833, 13.1),
    (18.3833, 13.2),
    (19.0000, 13.3),
    (19.6833, 13.4),
    (20.4000, 13.5),
    (21.1667, 13.6),
    (21.9833, 13.7),
    (22.8667, 13.8),
    (23.8167, 13.9),
    (24.8500, 14.0),
    (25.9667, 14.1),
    (27.1833, 14.2),
    (28.5167, 14.3),
    (29.9667, 14.4),
    (31.5500, 14.5),
    (33.3000, 14.6),
    (35.2500, 14.7),
    (37.4000, 14.8),
    (39.8000, 14.9),
    (42.4667, 15.0),
    (45.4833, 15.1),
    (48.8667, 15.2),
    (51.6833, 15.3),
    (56.9833, 15.4),
    (61.8333, 15.5),
    (67.2500, 15.6),
    (73.2333, 15.7),
    (79.7000, 15.8),
    (86.5167, 15.9),
),)

WINTER_SUN_CORRECTION = LookupTable((
    (9.5500, 10.8),
    (9.7500, 10.9),
    (9.9333, 11.0),
    (10.1333, 11.1),
    (10.3333, 11.2),
    (10.5500, 11.3),
    (10.7667, 11.4),
    (11.0000, 11.5),
    (11.2500, 11.6),
    (11.5000, 11.7),
    (11.7500, 11.8),
    (12.0167, 11.9),
    (12.3000, 12.0),
    (12.6000, 12.1),
    (12.9000, 12.2),
    (13.2333, 12.3),
    (13.5667, 12.4),
    (13.9167, 12.5),
    (14.2833, 12.6),
    (14.6833, 12.7),
    (15.0833, 12.8),
    (15.5167, 12.9),
    (15.9833, 13.0),
    (16.4500, 13.1),
    (16.9667, 13.2),
    (17.5000, 13.3),
    (18.0833, 13.4),
    (18.6833, 13.5),
    (19.3333, 13.6),
    (20.0333, 13.7),
    (20.7667, 13.8),
    (21.5667, 13.9),
    (22.4167, 14.0),
    (23.3333, 14.1),
    (24.3333, 14.2),
    (25.4000, 14.3),
    (26.5667, 14.4),
    (27.8333, 14.5),
    (29.2167, 14.6),
    (30.7333, 14.7),
    (32.4000, 14.8),
    (34.2500, 14.9),
    (36.2833, 15.0),
    (38.5667, 15.1),
    (41.1000, 15.2),
    (43.9333, 15.3),
    (47.1167, 15.4),
    (50.7167, 15.5),
    (54.7667, 15.6),
    (59.3500, 15.7),
    (64.4667, 15.8),
    (70.1667, 15.9),
    (76.4000, 16.0),
    (83.0833, 16.1),
),)


class Angle:
    """An angular number that prints nicely in degrees and minutes."""
    def __init__(self, value):
        self.value = value

    @staticmethod
    def from_string(string):
        """Returns a new angle from the supplied tack separate string, e.g. 45-12."""
        try:
            degrees, minutes = string.split('-')
            return Angle.deg_min(float(degrees), float(minutes))
        except ValueError:
            sys.exit('{} is not a valid angle as degrees-minutes'.format(string))

    @staticmethod
    def deg_min(degrees, minutes):
        """Returns a new angle for the supplied minutes and seconds, with sign set by degrees."""
        return Angle(degrees + copysign(minutes/60.0, degrees))

    def mod_360(self):
        """Returns the angle wrapped to between 0 and 360 degrees."""
        return Angle((360.0 + self.value) % 360.0)

    def round_to_minute(self):
        """Returns the angle rounded to the nearest minute."""
        return Angle(round(self.value * 60.0) / 60.0)

    def decompose(self):
        """Returns a tuple of sign, integer degrees, integer minutes, and integer tenths of min."""
        sign = -1 if self.value < 0.0 else +1
        remainder, tenths = divmod(int(round(abs(self.value) * 600)), 10)
        degrees, minutes = divmod(remainder, 60)
        return (sign, degrees, minutes, tenths)

    def __str__(self):
        sign, degrees, minutes, tenths = self.decompose()
        if degrees == 0:
            return "{}.{}'".format(sign * minutes, tenths)
        return "{}° {:2d}.{}'".format(sign * degrees, minutes, tenths)

    def nearest_degree_str(self):
        return "{:0.0f}°      ".format(round(self.value))

    def __add__(self, other):
        return type(self)(self.value + other.value)

    def __sub__(self, other):
        return type(self)(self.value - other.value)


class Latitude(Angle):
    """An latitude in degrees that prints nicely."""
    def __init__(self, value):
        super().__init__(value)

    @staticmethod
    def from_string(string):
        """Returns a new latitude from the supplied tack separated string, e.g. 37-40N."""
        number, direction = string[:-1], string[-1]
        try:
            sign = {'N': 1, 'n': 1, 'S': -1, 's': -1}[direction]
        except KeyError:
            sys.exit('{} is not a valid latitude ending in N or S'.format(string))
        try:
            degrees, minutes = number.split('-')
            return Latitude(sign * (int(degrees) + float(minutes) / 60.0))
        except ValueError:
            sys.exit('{} is not a valid latitude as degrees-minutesN/S'.format(string))

    def __str__(self):
        sign, degrees, minutes, tenths = self.decompose()
        return "{} {:3d}° {:02d}.{}'".format('S' if sign < 0 else 'N', degrees, minutes, tenths)


class Longitude(Angle):
    """An longitude in degrees that prints nicely."""
    def __init__(self, value):
        super().__init__(value)

    @staticmethod
    def from_string(string):
        """Returns a new longitude from the supplied tack separated string, e.g. 121-15W."""
        number, direction = string[:-1], string[-1]
        try:
            sign = {'E': 1, 'e': 1, 'W': -1, 'w': -1}[direction]
        except KeyError:
            sys.exit('{} is not a valid longitude ending in E or W'.format(string))
        try:
            degrees, minutes = number.split('-')
            return Longitude(sign * (int(degrees) + float(minutes) / 60.0))
        except ValueError:
            sys.exit('{} is not a valid longitude as degrees-minutesE/W'.format(string))

    def __str__(self):
        sign, degrees, minutes, tenths = self.decompose()
        return "{} {:3d}° {:02d}.{}'".format('W' if sign < 0 else 'E', degrees, minutes, tenths)


class TerrestrialPosition:
    """A latitide/longitude pair."""
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude

    def data(self, heading_prefix):
        """Returns a list of (headings, data) tuples for this object."""
        return [
            (heading_prefix + " latitude", str(self.latitude)),
            (heading_prefix + " longitude", str(self.longitude)),
        ]


class ZonedDateTime:
    """A datetime in a specified time zone offset."""
    def __init__(self, date_string, time_string, zone_offset):
        try:
            date = dt.date.fromisoformat(date_string)
        except ValueError:
            sys.exit('{} is not a valid ISO format date string'.format(date_string))
        try:
            time = dt.time.fromisoformat(time_string)
        except ValueError:
            sys.exit('{} is not a valid ISO format time string'.format(string))

        self.zone_offset = zone_offset
        self.zone = dt.datetime.combine(
            date, time, tzinfo=dt.timezone(dt.timedelta(hours=-zone_offset)))
        self.utc = self.zone.astimezone(dt.timezone.utc)

    def data(self):
        """Returns a list of (headings, data) tuples for this object."""
        return [
            ('Zone date', self.zone.date().strftime("%Y-%m-%d")),
            ('Zone time', self.zone.time().strftime("%H:%M:%S")),
            ('Zone description', '{:+0d}'.format(self.zone_offset)),
            ('UTC date', self.utc.date().strftime("%Y-%m-%d")),
            ('UTC time', self.utc.time().strftime("%H:%M:%S")),
        ]


class Altitude:
    """A measured celestial altitude and the corrected altitude."""
    def __init__(self, sextant_altitude, index_correction, height_of_eye):
        self.sextant = sextant_altitude
        self.index_correction = index_correction
        self.height_of_eye = height_of_eye
        self.dip = Angle(HEIGHT_TO_DIP.lookup(height_of_eye)/60.0)
        self.apparent = sextant_altitude + self.index_correction + self.dip
        self.corrections = []

    def observed(self):
        value = self.apparent
        for delta in [correction[1] for correction in self.corrections]:
            value += delta
        return value

    def data(self):
        """Returns a list of (headings, data) tuples for this object."""
        data = [
            ("Sextant altitude", str(self.sextant)),
            ("  Index correction", str(self.index_correction)),
            ("  Dip", str(self.dip)),
            ("Apparent altitude", str(self.apparent)),
        ]
        for correction in self.corrections:
            data.append((correction[0], str(correction[1])))
        data.append(("Observed altitude", str(self.observed())))
        return data


class LlSunAltitude(Altitude):
    """A celestial altitude of the lower limb of the sun."""
    def __init__(self, datetime, sextant_altitude, index_correction, height_of_eye):
        super().__init__(sextant_altitude, index_correction, height_of_eye)
        if datetime.month >= 4 and datetime.month <= 9:
            main_correction_sec = SUMMER_SUN_CORRECTION.lookup(self.apparent.value)
        else:
            main_correction_sec = WINTER_SUN_CORRECTION.lookup(self.apparent.value)
        self.corrections = (('  Main Correction', Angle(main_correction_sec / 60.0)),)

    @staticmethod
    def from_observed(datetime, observed_altitude, index_correction, height_of_eye):
        """Constructs an altitude deriving the sextant reading which would have led to the
        supplied observed altitude."""
        # We don't actually have reverse lookup tables so just iterate numerically.
        trial = LlSunAltitude(datetime, observed_altitude, index_correction, height_of_eye)
        while True:
            error = trial.observed() - observed_altitude
            if abs(error.value) < 0.001:
                return trial
            trial = LlSunAltitude(datetime, trial.sextant - error, index_correction, height_of_eye)


class CelestialPosition:
    """A position for a celestial body."""
    def __init__(self, declination, gha):
        self.declination = declination
        self.gha = gha

    @staticmethod
    def from_eq(equatorial_position, sidereal_time):
        """Constructs a celestial position from an equatorial position and sidereal time. """
        declination = Latitude(equatorial_position.decl * RAD_TO_DEG)
        gha = Angle((sidereal_time - equatorial_position.ra) * RAD_TO_DEG).mod_360()
        return CelestialPosition(declination, gha)


class SunPosition(CelestialPosition):
    """An equatorial position for the sun."""
    def __init__(self, datetime):
        ut = datetime_to_ut(datetime)
        sidereal_time = greenwich_sidereal_time(ut)
        dynamic_time = ut_to_dt(ut)
        temp = CelestialPosition.from_eq(Sun().geocentric_position(dynamic_time)[1], sidereal_time)
        super().__init__(temp.declination, temp.gha)


class Reduction:
    """A reduction of a celestial and a terrestrial position to altitude and azimuth."""
    def __init__(self, celestial, terrestrial):
        lat = terrestrial.latitude.value * DEG_TO_RAD
        long = terrestrial.longitude.value * DEG_TO_RAD
        decl = celestial.declination.value * DEG_TO_RAD
        gha = celestial.gha.value * DEG_TO_RAD
        lha = gha + long
        alt = asin((sin(lat) * sin(decl)) + (cos(lat) * cos(decl) * cos(lha)))
        # The special case of lha=0 can lead to a numerical precision error
        if abs(lha) < 0.0001:
            az = pi if lat > decl else 0.0
        else:
            az = acos((sin(decl) - sin(alt) * sin(lat)) / (cos(alt) * cos(lat)))
        self.altitude = Angle(alt * RAD_TO_DEG)
        az_degrees = az * RAD_TO_DEG
        if lat >= 0.0:
            self.azimuth = Angle(az_degrees) if lha >= pi else Angle(360.0 - az_degrees)
        else:
            self.azimuth = Angle(180.0 - az_degrees) if lha >= pi else Angle(180.0 - az_degrees)


class Pub249Reduction:
    """A reduction of a celestial and a terrestrial position to altitude and azimuth approximating
    the tables in Pub249."""
    def __init__(self, celestial, terrestrial):
        # Calculate the altitude and azimuth for the whole degrees of declination on either side
        # of the body's actual position.
        true_decl = celestial.declination.value
        declinations = [trunc(true_decl), trunc(true_decl) + copysign(1.0, true_decl)]
        reductions = [Reduction(CelestialPosition(Latitude(d), celestial.gha), terrestrial)
                      for d in declinations]

        # Use these to calculate the inputs to and output of table 5.
        delta_altitude = round((reductions[1].altitude - reductions[0].altitude).value * 60.0)
        minutes_decl = abs(round((true_decl - declinations[0])* 60.0))
        d_correction_minutes = round(delta_altitude * minutes_decl / 60.0)

        # Finally populate the object with everything thats interesting
        self.initial_altitude = reductions[0].altitude.round_to_minute()
        self.d_correction = Angle(d_correction_minutes / 60.0)
        self.calculated_altitude = self.initial_altitude + self.d_correction
        self.azimuth = reductions[0].azimuth if minutes_decl <= 30.0 else reductions[1].azimuth

    def data(self):
        """Returns a list of (heading, data) tuples for this object."""
        return [
            ("  Initial Hc", str(self.initial_altitude)),
            ("  d correction", str(self.d_correction)),
            ("Hc", str(self.calculated_altitude)),
            ("Azimuth", self.azimuth.nearest_degree_str()),
        ]


class LlSunSight:
    """A celestial sight on the lower limb of the sun and its reduction"""
    def __init__(self, zoned_dt, dr_position, sextant_altitude, index_correction, height_of_eye):
        # Record information about the time and location.
        self.zoned_dt = zoned_dt
        self.dr_position = dr_position

        # Delegate correction of the sextant_altitude to an altitude object.
        self.altitude = LlSunAltitude(
            zoned_dt.utc, sextant_altitude, index_correction, height_of_eye)

        # Record the sun position at the sight time and also top of hour to mirror the almanac
        # Procedure of adding increments to the position at top of hour.
        top_of_hour = dt.datetime.combine(
            zoned_dt.utc.date(),
            dt.time(zoned_dt.utc.hour, 0, 0),
            tzinfo=zoned_dt.utc.tzinfo)
        self.eq_top_of_hour = SunPosition(top_of_hour)
        self.eq = SunPosition(zoned_dt.utc)

        # Pick the AP to give whole numbers of degrees.
        # TODO: Verify this works for LHA < 0 and E longitude
        lha = round(self.eq.gha.value + self.dr_position.longitude.value)
        self.assumed_position = TerrestrialPosition(
            Latitude(round(dr_position.latitude.value)),
            Longitude(lha - self.eq.gha.value)
        )

        # Reduce both the assumed and DR positions, simulating Pub 249 for AP.
        self.ap_reduction = Pub249Reduction(self.eq, self.assumed_position)
        self.dr_reduction = Reduction(self.eq, self.dr_position)

        # Summarize the intercept distance.
        self.intercept = (
            self.altitude.observed().value - self.ap_reduction.calculated_altitude.value) * 60.0

        # And calculate the error assuming the DR was correct
        self.altitude_at_dr = LlSunAltitude.from_observed(
            zoned_dt.utc, self.dr_reduction.altitude, index_correction, height_of_eye)


    def data(self):
        """Returns a list of (heading, data) tuples for this object."""
        lha = Angle(self.eq.gha.value + self.assumed_position.longitude.value).mod_360()
        return (
            self.zoned_dt.data() +
            [('', '')] +
            self.dr_position.data('DR') +
            [('', '')] +
            self.altitude.data() +
            [
                ('', ''),
                ('  Initial decl', str(self.eq_top_of_hour.declination)),
                ('  d correction',
                 str(Angle(self.eq.declination.value - self.eq_top_of_hour.declination.value))),
                ('Declination', str(self.eq.declination)),
                ('  Initial GHA', str(self.eq_top_of_hour.gha)),
                ('  GHA increment',
                 str(Angle(self.eq.gha.value - self.eq_top_of_hour.gha.value).mod_360())),
                ('GHA', str(self.eq.gha)),
                ('', ''),
            ] +
            self.assumed_position.data('AP') +
            [
                ('LHA', str(lha)),
                ('', ''),
            ] +
            self.ap_reduction.data() +
            [
                ('', ''),
                ('Intercept distance', '{:.1f} nm'.format(abs(self.intercept))),
                ('Direction', 'Towards' if self.intercept >= 0.0 else 'Away'),
                ('', ''),
                ('Sextant alt at DR', str(self.altitude_at_dr.sextant)),
                ('Measurement error', str(self.altitude.sextant - self.altitude_at_dr.sextant)),
            ]
        )


def create_parser():
    """Creates the definition of the expected command line flags."""
    parser = argparse.ArgumentParser(
        description='Script to calculate a sun sight worksheet giving sight data.',
        epilog='Copyright Jody Sankey 2022')
    parser.add_argument('sight_data',
                        help='Comma separated date, time, zone, DR, sextant altitude,'
                        'index correction, height of eye in ft. e.g.: '
                        '"2022-07-01,13:26:00,+7,37-46.0N,122-06.0W,75-44,0,7". '
                        'Or a path to a file containing one or more lines of this data.')
    return parser


def sight_from_sight_string(sight_string):
    """Produces a sight object from the supplied comma separated string."""
    def validate_integer(string):
        try:
            return int(string)
        except ValueError:
            sys.exit('{} is not a valid integer value'.format(string))

    elements = sight_string.split(',')
    if len(elements) != 8:
        sys.exit('{} does not contain 8 comma separated elements'.format(sight_string))

    return LlSunSight(
        zoned_dt=ZonedDateTime(elements[0], elements[1], validate_integer(elements[2])),
        dr_position=TerrestrialPosition(
            Latitude.from_string(elements[3]),
            Longitude.from_string(elements[4])),
        sextant_altitude=Angle.from_string(elements[5]),
        index_correction=Angle(validate_integer(elements[6]) / 60.0),
        height_of_eye=validate_integer(elements[7]))


def main():
    """Executes the script using command line arguments."""
    # We expect a single input arg, either a comma separated input of a path to a file.
    arg = create_parser().parse_args().sight_data
    if os.path.exists(arg):
        # If the input is a file, try reading it
        with open(arg, 'r') as datafile:
            sights = [sight_from_sight_string(l) for l in datafile if not l.startswith('#')]
    else:
        # Otherwise interpret it as a sight
        sights = [sight_from_sight_string(arg)]

    sights_elements_data = [s.data() for s in sights]
    elements_sights_data = map(list, zip(*sights_elements_data))
    for sights_data in elements_sights_data:
        line = sights_data[0][0].ljust(TEXT_WIDTH)
        for data in sights_data:
            line += data[1].rjust(DATA_WIDTH)
        print(line)


if __name__ == '__main__':
    print()
    main()
