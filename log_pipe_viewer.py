#!/usr/bin/python3
# ========================================================
# Curses python script to manage display of log messages
# received on a named pipe.
#
# If updating this a lot should be configuration flags
# rather than hardcoded.
# ========================================================
# Copyright Jody M Sankey 2015-2022
# ========================================================
# AppliesTo: linux
# AppliesTo: server
# RemoveExtension: True
# PublicPermissions: True
# ========================================================

from collections import deque
from curses import COLOR_MAGENTA, COLOR_WHITE, COLOR_RED, COLOR_GREEN, COLOR_CYAN
from curses import COLOR_YELLOW, COLOR_BLACK, COLOR_BLUE, A_REVERSE
from datetime import datetime, timedelta

import curses
import time
import queue
import re
import subprocess
import threading


LOG_PIPE = '/var/log/syslog_pipe'
ITERATION_TENTHS_SEC = 10
BUFFER_LENGTH = 3000
HOST_INDEX_COUNT = 9
HEALTH_INTERVAL = timedelta(seconds=15)

REPLACEMENTS = (
    (r'puck', r'puck'),
    (r'\[SWITCH_LOCAL-default-D\]', r''),
    (r' MAC=([0-9a-f]{2}:){5,17}[0-9a-f]', r''),
    (r'TTL=6\d ', ''),
    (r'TOS=0x00 PREC=0x00 ', ''),
    (r'IN=switch0', 'IN=sw0'),
    (r'^\[\d+\.\d+\] ', r''),
    (r'ff:ff:ff:ff:ff:ff', r'f::f'),
)

COMMANDS = {
    ord('j'): ('SCROLL_DOWN', 0, 'Scroll downwards'),
    ord('k'): ('SCROLL_UP', 1, 'Scroll upwards'),
    ord(' '): ('SCROLL_STOP', None, None),
    ord('0'): ('VIS_ALL_HOSTS', 4, 'Show all hosts'),
    ord(','): ('VIS_LEVEL_UP', 7, 'Show one less level'),
    ord('.'): ('VIS_LEVEL_DOWN', 8, 'Show one more level'),
    ord('i'): ('INSERT_ERROR', 10, 'Insert a dummy error'),
    ord('?'): ('SHOW_HELP', 11, 'Display this page'),
}
for c, s in zip('123456789', '!@#$%^&*('):
    COMMANDS[ord(c)] = ('VIS_ONLY_HOST_' + c, None, None)
    COMMANDS[ord(s)] = ('VIS_TOGGLE_HOST_' + c, None, None)

EXTRA_HELP = {2: ('Space', 'Leave scrolling'),
              5: ('1-9', 'Show only the numbered host'),
              6: ('!-)', 'Toggle visibility of one host')}

SECONDS_PER_HOUR = 3600
PANEL_WIDTH = 10
MIN_PANEL_HEIGHT = 34
FIRST_LEVEL_ROW = 4
FIRST_HOST_ROW = 14

next_curses_color_index = 1
def init_curses_color(fg_color, bg_color):
    """Initializes the next available curses index to a color pair and returns attributes."""
    global next_curses_color_index
    next_curses_color_index += 1
    curses.init_pair(next_curses_color_index - 1, fg_color, bg_color)
    return curses.color_pair(next_curses_color_index - 1)


DEBUG_FILE = None
#DEBUG_FILE = '/tmp/logviewer_debug.txt'
def debug(text):
    """Writes a debug statment to file if a file was hardcoded above, working with curses
    this is better than the typical printf debugging."""
    if DEBUG_FILE:
        with open(DEBUG_FILE, 'a') as f:
            f.write(text + '\n')


class Hosts:
    """Simple class to store the set of hosts and their indexes."""

    def __init__(self, initial_names):
        self.list = initial_names
        self.name_to_index = {self.list[i]: i for i in range(len(self.list))}

    def get_index(self, raw_host_name):
        """Returns an index for the supplied host, adding to the list and dictionary if needed."""
        name = HOST_REPLACEMENTS.get(raw_host_name, raw_host_name)
        if name not in self.name_to_index:
            self.list.append(name)
            self.name_to_index[name] = len(self.list) - 1
        return self.name_to_index[name]
HOST_REPLACEMENTS = {'puck.jsankey.com': 'puck'}
HOSTS = Hosts(['ariel', 'puck', 'mab', 'switch', 'umbriel', 'debbie', 'vicki'])

class Level:
    """Simple class to represent an rsyslog level and its color."""
    _next_idx = 0

    def __init__(self, name, color_val):
        self.index = Level._next_idx
        self.name = name
        self._color_val = color_val
        self.color = None
        Level._next_idx += 1

    def init_color(self):
        """Initializes a color index for this level."""
        self.color = init_curses_color(self._color_val, COLOR_BLACK)


LEVELS = [Level('emerg', COLOR_MAGENTA),
          Level('alert', COLOR_MAGENTA),
          Level('crit', COLOR_RED),
          Level('err', COLOR_RED),
          Level('warning', COLOR_YELLOW),
          Level('notice', COLOR_WHITE),
          Level('info', COLOR_GREEN),
          Level('debug', COLOR_GREEN)]
NO_LEVEL = Level('n/a', COLOR_CYAN)


class Visibility:
    """Defines the current visibility state of each host and level"""

    def __init__(self):
        self.host_index_visible = [True] * HOST_INDEX_COUNT
        self.limit_level = None
        self.set_all_levels()

    def increase_level(self):
        """Makes one more severity visible"""
        self.limit_level = max(0, self.limit_level - 1)

    def decrease_level(self):
        """Makes one less severity visible"""
        self.limit_level = min(len(LEVELS) - 1, self.limit_level + 1)

    def set_all_levels(self):
        """Makes all severities visible"""
        self.limit_level = len(LEVELS) - 1

    def toggle_host(self, host_index):
        """Makes the selected host visible if currently not and visa versa"""
        if host_index in range(HOST_INDEX_COUNT + 1):
            self.host_index_visible[host_index] = not self.host_index_visible[host_index]

    def exclusive_host(self, host_index):
        """Makes only the selected host visible"""
        if host_index in range(HOST_INDEX_COUNT + 1):
            self.host_index_visible = [False] * HOST_INDEX_COUNT
            self.host_index_visible[host_index] = True

    def set_all_hosts(self):
        """Makes all hosts visible"""
        self.host_index_visible = [True] * HOST_INDEX_COUNT

    def is_entry_visible(self, entry):
        """Returns true if the supplied entry should be visible"""
        return self.is_host_visible(entry.host_idx) and self.is_level_visible(entry.level.index)

    def is_host_visible(self, host_index):
        """Returns true if the supplied host should be visible"""
        return self.host_index_visible[host_index]

    def is_level_visible(self, level):
        """Returns true if the supplied severity level should be visible"""
        return level <= self.limit_level


class Entry:
    """Defines a single log entry read from the pipe, or a fixed error string"""

    @staticmethod
    def from_log_line(logline):
        """Create a new error entry from the supplied log line assumed to be in the following
        format: time|HOST|facility|facility-text|level|level-text|tag|msg\n"""
        items = logline.split('|', 9)
        if len(items) != 8:
            return Entry.from_error_text('parse', logline)

        message = items[7].strip()
        # Strip date space, would be nice if rsyslog could do this
        timestr = items[0][0:3] + items[0][4:]
        for replacement in REPLACEMENTS:
            message = re.sub(replacement[0], replacement[1], message)
        return Entry(timestr=timestr, host_idx=HOSTS.get_index(items[1]), facility=items[3],
                     level_idx=int(items[4]), tag=items[6].strip(':'), msg=message)

    @staticmethod
    def from_error_text(facility, text):
        """Create a new error entry from the supplied 'facility' and error text"""
        return Entry(timestr=datetime.now().strftime('%b%-2d %H:%M:%S'),
                     host_idx=HOSTS.get_index('error'), facility=facility,
                     level_idx=0, tag='', msg='ERROR: ' + text)

    def __init__(self, timestr, host_idx, facility, level_idx, tag, msg):
        self.time = timestr
        self.host = HOSTS.list[host_idx]
        self.host_idx = host_idx
        self.facility = facility
        self.level = LEVELS[level_idx]
        self.tag = tag
        self.msg = msg

    def color(self):
        """Returns the color to use for this entry."""
        return self.level.color

    def display_string(self, length_limit):
        """Returns the string to diplay for this entry, capped at the supplied length."""
        line = '{} {:6} {:>7} {:8} '.format(
            self.time, self.host, self.level.name, self.facility)
        if self.tag and self.tag != 'kernel':
            line += '{{{}}} '.format(self.tag)
        if len(line) + len(self.msg) > length_limit:
            return line + self.msg[:length_limit-len(line)-1] + '>'
        return line + self.msg


class NonBlockingStreamReader:
    """Class to read complete lines from an infinite stream without blocking the main thread.
    Based on http://eyalarubas.com/python-subproc-nonblock.html"""

    def __init__(self, stream):
        def _transfer_line_to_queue(stream, the_queue):
            while True:
                line = stream.readline()
                if line:
                    the_queue.put(line)
                else:
                    time.sleep(ITERATION_TENTHS_SEC * 10)

        self._stream = stream
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=_transfer_line_to_queue,
                                        args=(self._stream, self._queue))
        self._thread.daemon = True
        self._thread.start()

    def read_line(self):
        """Read one line from the stream."""
        try:
            return self._queue.get(block=False, timeout=None)
        except queue.Empty:
            return None


class HealthMonitor:
    """Simple class to gather the current health of local host."""

    def __init__(self):
        boot_str = subprocess.check_output(
            ['who', '-b']).decode('utf-8').strip().split(None, 2)[2]
        self.boot_time = datetime.strptime(boot_str, '%Y-%m-%d %H:%M')
        self.update()

    def update(self):
        """Updates the current state by calling processes."""
        now = datetime.now()
        td_since_boot = now - self.boot_time
        self.uptime = '{}d {}h'.format(
            td_since_boot.days, td_since_boot.seconds // SECONDS_PER_HOUR)
        self.temperature = HealthMonitor._value_from_process_output(
            ['sensors'], r'Core 0:\s*\+?([0-9.]*)') + 'C'
        self.home_used = HealthMonitor._value_from_process_output(
            ['df', '/home', '--output=pcent'], r'(\d+%)')
        self.last_update = now

    @staticmethod
    def _value_from_process_output(command_list, regex):
        """Runs a command and returns a string extracted from the output line matching regex.
        Note STDERR is discarded since UPSC throws a lot of useless information into STDERR."""
        try:
            response = subprocess.check_output(
                command_list, stderr=subprocess.DEVNULL).decode('utf-8')
        except subprocess.CalledProcessError:
            return 'ERR'
        match = re.search(regex, response)
        return match.group(1) if match else 'N/K'


class CursesStatusWin:
    """Functionality to maintain and update a curses window showing status."""

    def __init__(self, win, visibility, display_count_func):
        self.win = win
        self.height, self.width = win.getmaxyx()
        self.counts = [[0] * len(LEVELS) for _ in range(HOST_INDEX_COUNT)]
        self.visibility = visibility
        self.display_count_func = display_count_func
        self.health_monitor = HealthMonitor()

    def notify_add(self, entry):
        """Updates the counters and headings to account for an added entry."""
        self.counts[entry.host_idx][entry.level.index] += 1
        if self.height >= MIN_PANEL_HEIGHT and self.counts[entry.host_idx][entry.level.index] == 1:
            # If this is the first entry for this combination it may have changed the highlights
            self._draw_host_by_idx(entry.host_idx)
            self._draw_level_by_idx(entry.level.index)

    def notify_remove(self, entry):
        """Updates the counters and headings to account for a removed entry."""
        self.counts[entry.host_idx][entry.level.index] -= 1
        if self.height >= MIN_PANEL_HEIGHT and self.counts[entry.host_idx][entry.level.index] == 0:
            # If that was the last entry for this combination it may have changed the highlights
            self._draw_host_by_idx(entry.host_idx)
            self._draw_level_by_idx(entry.level.index)

    def repaint(self):
        """Replaints the entire status window including headings."""
        self.win.clear()
        self._draw_headings()
        self.update()

    def update(self):
        """Updates the counters and health."""
        total = sum([sum(host_counts) for host_counts in self.counts])
        self.win.addstr(1, 1, 'Tot:{:>4}'.format(total))
        self.win.addstr(2, 1, 'Vis:{:>4}'.format(self.display_count_func()))
        self._draw_clock()
        self._draw_health()
        self.win.refresh()

    def _draw_clock(self):
        if self.height >= MIN_PANEL_HEIGHT:
            now = datetime.now()
            self.win.addstr(self.height-4, 0,
                            '{:^10}'.format(now.strftime('%A')))
            self.win.addstr(self.height-3, 1,
                            '{:^8}'.format(now.strftime('%-d %b')))
            self.win.addstr(self.height-2, 1,
                            '{:^8}'.format(now.strftime('%H:%M:%S')))

    def _draw_health(self):
        if self.height >= MIN_PANEL_HEIGHT:
            # Updating these is expensive. Only do it rarely.
            if datetime.now() > self.health_monitor.last_update + HEALTH_INTERVAL:
                self.health_monitor.update()
            for idx, content in enumerate([
                    'Up:', '{:>8}'.format(self.health_monitor.uptime), '',
                    '/home:', '{:>8}'.format(self.health_monitor.home_used), '',
                    'CPU:', '{:>8}'.format(self.health_monitor.temperature), '']):
                self.win.addstr(self.height - 14 + idx, 1, content)

    def _draw_headings(self):
        if self.height >= MIN_PANEL_HEIGHT:
            for host_index in range(len(HOSTS.list)):
                self._draw_host_by_idx(host_index)
            for level_index in range(len(LEVELS)):
                self._draw_level_by_idx(level_index)

    def _draw_host_by_idx(self, host):
        attr = ([l.color for l in LEVELS if self.counts[host][l.index] > 0]
                + [NO_LEVEL.color])[0]
        if self.visibility.is_host_visible(host):
            attr += A_REVERSE
        host_name = ' {:<8}'.format(HOSTS.list[host])
        self.win.addstr(FIRST_HOST_ROW + host, 0, host_name, attr)

    def _draw_level_by_idx(self, level):
        attr = LEVELS[level].color
        if self.visibility.is_level_visible(level):
            attr += A_REVERSE
        level_name = ' {:<8}'.format(LEVELS[level].name)
        self.win.addstr(FIRST_LEVEL_ROW + level, 0, level_name, attr)


class CursesLogPad:
    """Functionality to maintain and update a curses pad of log entries"""

    def __init__(self, pad, screen_height, screen_left):
        self.pad = pad
        self.rows, self.width = pad.getmaxyx()
        self.height = screen_height
        self.coords = 0, screen_left, screen_height - 1, screen_left + self.width - 1
        self.first_allowed = 0
        self.entries = deque()
        self.next_line = 0
        self.scroll_line = None
        self.clear()

    def clear(self):
        """Clears all entries from the pad."""
        self.pad.erase()
        self.next_line = 0
        self.scroll_line = None
        self.first_allowed = 0
        self.entries.clear()

    def add_entry(self, entry):
        """Writes a single entry to the pad at the current position."""
        self.entries.append(entry)
        if self.next_line >= (self.rows - 1):
            # Oh noes, our pad is full. Lets start over at the beginning.
            debug('Pad full at {}'.format(self.next_line))
            self._refill_pad()
        else:
            self.pad.addstr(self.next_line, 0, entry.display_string(self.width), entry.color())
            self.next_line += 1

    def remove_entry(self, entry):
        """Removes an entry (which we may not have been given)."""
        if entry is self.entries[0]:
            self.entries.popleft()
            self.first_allowed += 1
            if self.scroll_line is not None and self.scroll_line < self.first_allowed:
                self.scroll_line = self.first_allowed

    def refresh(self):
        """Issues a refresh to the pad with understanding of scroll position and buffer length."""
        last_scroll_line = max(0, self.next_line - self.height)
        top = self.scroll_line if self.scroll_line is not None else last_scroll_line
        self.pad.refresh(top, 0, *self.coords)

    def scroll(self, num):
        """Scrolls the pad by num lines if possible, +ve is down."""
        last_scroll_line = max(0, self.next_line - self.height)
        if self.scroll_line is None:
            self.scroll_line = last_scroll_line
        else:
            self.scroll_line = sorted(
                (self.first_allowed, self.scroll_line + num, last_scroll_line))[1]

    def scroll_off(self):
        """Disables scrolling."""
        self.scroll_line = None

    def display_count(self):
        """Returns the total number of entries displayed."""
        return len(self.entries)

    def _refill_pad(self):
        """Clears and refills the pad from the beginning based on the entry queue. It would be
        possible to preserve the scroll position through this, but its so rare don't think it's
        worth it."""
        self.scroll_line = None
        self.first_allowed = 0
        self.pad.erase()
        for entry, y in zip(self.entries, range(len(self.entries))):
            self.pad.addstr(y, 0, entry.display_string(
                self.width), entry.color())
        self.next_line = len(self.entries)


class LogViewer:
    """The application main class"""

    def __init__(self, screen_win, panel_win, log_pad):
        self.entries = deque()
        self.visibility = Visibility()
        self.screen = screen_win
        self.pad = CursesLogPad(log_pad, *panel_win.getmaxyx())
        self.panel = CursesStatusWin(
            panel_win, self.visibility, self.pad.display_count)
        self.reader = NonBlockingStreamReader(open(LOG_PIPE, 'r'))
        self.help_win = None

    def add_new_entry(self, entry):
        """Adds a new entry to the buffer, removing old ones if necessary"""
        while len(self.entries) >= BUFFER_LENGTH:
            removed = self.entries.popleft()
            self.panel.notify_remove(removed)
            self.pad.remove_entry(removed)
        self.entries.append(entry)
        self.panel.notify_add(entry)
        if self.visibility.is_entry_visible(entry):
            self.pad.add_entry(entry)

    def repopulate_pad(self):
        """Recalculates the pad from the entry buffer respecting current visibility"""
        self.pad.clear()
        for entry in self.entries:
            if self.visibility.is_entry_visible(entry):
                self.pad.add_entry(entry)

    def display_help(self):
        """Shows a simple keyboard help screen until any key is pressed"""
        if self.help_win is None:
            # Calculate the row content
            y_to_texts = {COMMANDS[c][1]: (chr(c), COMMANDS[c][2])
                          for c in COMMANDS if COMMANDS[c][1] is not None}
            y_to_texts.update(EXTRA_HELP)
            widths = [max((len(y_to_texts[k][n]))
                          for k in y_to_texts) for n in range(2)]
            height = max(y_to_texts.keys())
            # Create the window
            self.help_win = curses.newwin(height + 5, sum(widths) + 6)
            self.help_win.bkgd(' ', init_curses_color(COLOR_WHITE, COLOR_BLUE))
            self.help_win.border()
            # Populate the actual help strings
            fmt = '{:>' + str(widths[0]) + '}  {}'
            for y in y_to_texts:
                self.help_win.addstr(y+2, 2, fmt.format(*y_to_texts[y]))
        LogViewer._overwrite_window_centered(self.screen, self.help_win)
        self.screen.touchwin()
        self.screen.refresh()
        while True:
            k = self.screen.getch()
            if k != curses.ERR:
                self.screen.touchwin()
                self.screen.refresh()
                self.panel.repaint()
                break

    @classmethod
    def _overwrite_window_centered(cls, bottom_win, top_win):
        bottom_sz = bottom_win.getmaxyx()
        top_sz = top_win.getmaxyx()
        offset = [(bottom_sz[i] - top_sz[i])//2 for i in range(2)]
        coords = [0, 0] + offset + [offset[i]+top_sz[i]-1 for i in range(2)]
        top_win.overwrite(bottom_win, *coords)

    def handle_character(self, k):
        """Handles the supplied command input character, assumes a pad refresh will occur after."""
        #self.panel.win.addstr(self.panel.height - 6, 1, "cmd = " + chr(k))
        command_name = COMMANDS[k][0]
        if command_name.startswith('VIS_'):
            if command_name.startswith('VIS_ONLY_HOST_'):
                self.visibility.exclusive_host(
                    ord(command_name[-1]) - ord('1'))
            elif command_name.startswith('VIS_TOGGLE_HOST_'):
                self.visibility.toggle_host(ord(command_name[-1]) - ord('1'))
            elif command_name == 'VIS_ALL_HOSTS':
                self.visibility.set_all_hosts()
            elif command_name == 'VIS_LEVEL_UP':
                self.visibility.increase_level()
            elif command_name == 'VIS_LEVEL_DOWN':
                self.visibility.decrease_level()
            self.repopulate_pad()
            self.panel.repaint()  # Full repaint cleans up any corruption we accumulate
        elif command_name == 'SCROLL_UP':
            self.pad.scroll(-1)
        elif command_name == 'SCROLL_DOWN':
            self.pad.scroll(1)
        elif command_name == 'SCROLL_STOP':
            self.pad.scroll_off()
        elif command_name == 'SHOW_HELP':
            self.display_help()
        else:
            self.add_new_entry(Entry.from_error_text(
                'control', 'Unknown command ' + str(k)))

    def main(self):
        """Main loop for the application"""
        # Getting a character first helps our drawing stick
        k = self.screen.getch()
        self.repopulate_pad()
        self.panel.repaint()
        while True:
            self.panel.update()
            log_line = self.reader.read_line()
            if log_line is not None:
                self.add_new_entry(Entry.from_log_line(log_line))
            else:
                # Only read keyboard once we've cleared the buffer
                # TODO: Consider one of these every 10 if buffer is still not empty
                k = self.screen.getch()
                if k in COMMANDS.keys():
                    self.handle_character(k)
                self.pad.refresh()


def main(stdscr):
    """Main curses function, which initializes curses objects then lets a
    LogViewer do the real work"""
    for level in LEVELS + [NO_LEVEL]:
        level.init_color()
    curses.halfdelay(ITERATION_TENTHS_SEC)  # Iteration timer
    curses.curs_set(0)  # Hide cursor
    height, width = stdscr.getmaxyx()
    panel = curses.newwin(height, PANEL_WIDTH, 0, 0)
    pad = curses.newpad(BUFFER_LENGTH * 2, width - PANEL_WIDTH)
    viewer = LogViewer(stdscr, panel, pad)
    viewer.main()


if __name__ == '__main__':
    # Wrap the curses operations to ensure everything terminates cleanly.
    curses.wrapper(main)
