#!/usr/bin/python3
#========================================================
# Python script to generate trending graphs based on
# camera events delivered to an IMAP accessible email
# address.
#========================================================
# Copyright Jody M Sankey 2018
#========================================================
# AppliesTo: linux
# AppliesTo: server
# RemoveExtension: True
# PublicPermissions: True
#========================================================

# This has to be before the pyplot import to survive without X
import matplotlib
matplotlib.use('Agg')

import argparse
from datetime import date, datetime, time, timedelta
import email.parser
import imaplib
import itertools
import json
import matplotlib.pyplot as plt
import matplotlib.dates
import numpy as np
import pytz
import re
import os
import sys


def createParser():
  """Creates the definition of the expected command line flags."""
  parser = argparse.ArgumentParser(
    description='Creates graphs based on Nest notifications in an IMAP account',
    epilog='Copyright Jody Sankey 2018')
  parser.add_argument('-v', '--verbose', action='store_true',
                      help='Output detailed status')
  parser.add_argument('--days', type=int, default=365,
                      help='Maximum number of days to include in the graph')
  parser.add_argument('--host', default='mail.jsankey.com',
                      help='Hostname of IMAP server')
  parser.add_argument('--port', type=int, default=993,
                      help='Port of IMAP server')
  parser.add_argument('--sender', default='notifications@nest.com',
                      help='Sending address of notifcations')
  parser.add_argument('user', help='Username for IMAP server')
  parser.add_argument('password_file',
                      help='Text file containing account password')
  parser.add_argument('output_file', help='Location to save the plot output')
  return parser


class Logger(object):
  """Writes to terminal handling colors and verbosity."""

  def fine(self, text):
    if flags.verbose: Logger._writeColoredLine(36, text)

  def info(self, text):
    if flags.verbose: Logger._writeColoredLine(32, text)

  def warn(self, text):
    Logger._writeColoredLine(33, text)

  def error(self, text):
    Logger._writeColoredLine(31, text)

  @staticmethod
  def _writeColoredLine(color_number, text):
    if sys.stdout.isatty():
      print('\033[1;{}m{}\033[1;m'.format(color_number, text))
    else:
      print(text)


class Account(object):
  """Encapsulates access to an IMAP account."""

  def __init__(self):
    """Constructs a new account from the command line flags."""
    self.host = flags.host
    self.port = int(flags.port)
    self.user = flags.user
    with open(os.path.expanduser(flags.password_file)) as f:
      self.password = f.readline().rstrip()
    self.connection = None

  def open(self):
    """Opens an IMAP connection to this account."""
    assert(self.connection is None)
    self.connection = imaplib.IMAP4_SSL(self.host, self.port)
    LOGGER.info('Opened connection to {}:{}'.format(self.host, self.port))
    self.connection.login(self.user, self.password)
    if flags.verbose:
      stat, resp = self.connection.list()
      mailbox_count = len(resp) if stat == 'OK' else 'N/K'
      LOGGER.fine('authenticated as {}, total {} mailboxes'.format(
          self.user, mailbox_count))

  def list(self):
    """Returns a list of (datetime, subject) tuples for all matching emails."""
    assert(self.connection is not None)
    resp = self.connection.select('INBOX')
    if resp[0] != 'OK':
      LOGGER.warn(resp[1].decode('utf-8'))
      return []

    query = 'FROM "{}" SINCE {}'.format(
        flags.sender,
        (datetime.now() - timedelta(days=flags.days)).strftime('%d-%b-%Y'))
    stat, resp = self.connection.uid('SEARCH', query)
    if stat != 'OK':
      LOGGER.warn('Error with SEARCH {}: {}'.format(self, resp.decode('utf-8')))
      return []
    uids = resp[0].decode('utf-8').split()
    if len(uids) == 0:
      LOGGER.fine('Did not match any messages')
      return []

    LOGGER.fine('Found {} messages'.format(len(uids)))
    email_parser = email.parser.BytesParser()
    results = []
    for uid in uids:
      stat, resp = self.connection.uid('FETCH', uid, '(RFC822.HEADER)')
      if stat != 'OK':
        LOGGER.warning('Error fetching UID {}'.format(uid))
      else:
        e = email_parser.parsebytes(resp[0][1])
        d_utc = datetime.strptime(e['Date'][5:], '%d %b %Y %H:%M:%S %z')
        d_loc = d_utc.astimezone(TIMEZONE).replace(tzinfo=None)
        results.append((d_loc, e['Subject']))
    return results

  def close(self):
    """Cleanly closes an IMAP connection to this specified account."""
    assert(self.connection is not None)
    self.connection.logout()
    self.connection = None
    LOGGER.info('Closed connection to {}'.format(self.host))


class CameraData(object):
  """Encapsulates a set of measured data for one or more cameras."""

  def __init__(self, data):
    """Initializes from a list of (datetime, camera) email tuples."""
    self.min_date = min([d for (d, c) in data]).date()
    self.max_date = max([d for (d, c) in data]).date()
    self.day_count = (self.max_date - self.min_date).days + 1
    self.dates = [self.min_date + timedelta(n) for n in range(self.day_count)]

    self.cameras = sorted(set([c for (d, c) in data]))
    self.per_camera = {c: {} for c in self.cameras}
    LOGGER.fine('Processing data for {} cameras and {} days'.format(
                len(self.cameras), self.day_count))

    # Assemble per-date ordered event lists for each camera
    for c in self.cameras:
       self.per_camera[c]['events'] = [[] for x in range(self.day_count)]
    for (d, c) in data:
      day_index = (d.date() - self.min_date).days
      day_fraction = (d - datetime.combine(d.date(), time.min)) / timedelta(1)
      self.per_camera[c]['events'][day_index].append(day_fraction)
    for c in self.cameras:
      for e in self.per_camera[c]['events']:
        e.sort()

    # Then calculate derived data from these
    for c in self.cameras:
      cam_data = self.per_camera[c]
      cam_data['first'] = [
          e[0] if e else None for e in cam_data['events']]
      cam_data['second'] = [
          (e[1] if len(e) > 2 else None) for e in cam_data['events']]
      cam_data['penultimate'] = [
          (e[-2] if len(e) > 2 else None) for e in cam_data['events']]
      cam_data['last'] = [
          (e[-1] if e else None) for e in cam_data['events']]
      cam_data['count'] = [len(e) for e in cam_data['events']]

  def createPlot(self):
    """Creates a comprehensive graphical output using current data."""
    plt.figure(figsize=(10, 8), dpi=300)
    plt.subplot(1 + len(self.cameras),1,1)
    plt.gca().set_prop_cycle('color', ['#005195', '#cc0044'])
    for c in self.cameras:
      plt.plot(self.dates, self.per_camera[c]['count'], label=c)
      plt.ylabel('Number of Events')
    plt.legend(bbox_to_anchor=(1.23, 1.03), fontsize=10)
    CameraData._formatDatedPlot(plt.gca(), False)

    for (i, c) in enumerate(self.cameras, start=1):
      plt.subplot(1 + len(self.cameras), 1, 1 + i)
      plt.ylim(0, 1)
      plt.yticks(
          np.arange(0, 1.0, step=0.125),
          ('','','6am','9am','12pm','3pm','6pm','9pm'))
      plt.gca().set_prop_cycle(
          'color', ['#558822', '#008472', '#005195', '#7722aa'])
      plt.plot(self.dates, self.per_camera[c]['first'], label='First')
      plt.plot(self.dates, self.per_camera[c]['second'], label='Second')
      plt.plot(
          self.dates, self.per_camera[c]['penultimate'], label='Penultimate')
      plt.plot(self.dates, self.per_camera[c]['last'], label='Last')
      plt.ylabel(c + ' Times')
      plt.legend(bbox_to_anchor=(1.23, 1.03), fontsize=10)
      CameraData._formatDatedPlot(plt.gca(), i == len(self.cameras))
    
    plt.subplots_adjust(bottom=0.15, top=0.95, left=0.12, right=0.8)
    plt.savefig(flags.output_file)
    plt.close()

  @staticmethod
  def _formatDatedPlot(ax, draw_x_labels):
    """Applies appropriate formatting to the supplied matplotlib axes."""
    ax.grid(color='0.7', linestyle='-')
    ax.tick_params(labelsize=10)
    ax.yaxis.set_label_coords(-0.09, 0.5)
    ax.xaxis.set_major_locator(
        matplotlib.dates.WeekdayLocator(byweekday=matplotlib.dates.MO))
    if draw_x_labels:
      ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%Y-%m-%d'))
    else:
      ax.xaxis.set_ticklabels([])
    ax.xaxis.set_minor_locator(matplotlib.dates.DayLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=90)
    


PARSER = createParser()
LOGGER = Logger()
EMAIL_REGEX = re.compile('Your (\w+) camera saw someone.')
TIMEZONE = pytz.timezone('Europe/London')


if __name__ == '__main__':
  global flags

  flags = PARSER.parse_args()
  account = Account()
  try:
    account.open()
    datetime_subject = account.list()
    datetime_match = [(d, EMAIL_REGEX.match(e)) for (d, e) in datetime_subject]
    datetime_camera = [(d, m.group(1)) for (d, m) in datetime_match if m]
    CameraData(datetime_camera).createPlot()
    
  except imaplib.IMAP4.error as e:
    LOGGER.error(str(e))
  finally:
    account.close()
