#!/usr/bin/python3
#========================================================
# monitor_clipboards.py
#========================================================
# Trivial first curses application to periodically print
# the current contents of two system clipboards and one
# tmux clipboard.
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================
 
import curses
import os
import subprocess

TICKERS = ['-','\\','|','/']
QUIT_CH = ord('q')

ITERATION_TENTHS_SEC = 20
ERROR_COL = 1
GOOD_COL = 2
STATUS_COL = 3


def _xClipboard(clipboard_name):
    """Return the current clipboard contents as a string, or None if not in X."""
    if 'DISPLAY' not in os.environ:
        return None
    else:
        return subprocess.check_output(['xclip', '-o', '-selection', 
                                        clipboard_name]).decode('utf-8')

def _tmuxClipboard():
    """Return the current tmux contents as a string, or None if not in tmux."""
    if 'TMUX' not in os.environ:
        return None
    try:
        return subprocess.check_output(['tmux', 'show-buffer']).decode('utf-8')
    except subprocess.CalledProcessError:
        return ''


def _addClipboardString(stdscr, clipboard_name, y, x, width):
    """Add a string for the current clipboard at the specified position."""
    contents = _tmuxClipboard() if clipboard_name == 'tmux' else _xClipboard(clipboard_name)
    if contents == None:
        missing_env = '$TMUX' if clipboard_name == 'tmux' else '$DISPLAY'
        stdscr.addstr(y, x, 'No {} set'.format(missing_env), curses.color_pair(ERROR_COL))
    else:
        if len(contents) == 0:
            stdscr.addstr(y, x, '{:>14} empty'.format(clipboard_name),
                          curses.color_pair(STATUS_COL))
        else:
            header = '{} {} bytes'.format(clipboard_name, len(contents))
            output = '{:>20}: {}'.format(header, contents.split('\n')[0])
            if len(output) > width - x:
                output = output[:width - x - 3] + '...'
            stdscr.addstr(y, x, output, curses.color_pair(GOOD_COL))
 

def main(stdscr):
    curses.halfdelay(ITERATION_TENTHS_SEC) # Iteration timer
    curses.init_pair(ERROR_COL, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(GOOD_COL, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(STATUS_COL, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.curs_set(0) # Hide cursor

    i = 0
    height, width = stdscr.getmaxyx()
    while True:
        stdscr.clear()
        stdscr.addstr(1, 0, TICKERS[i])
        _addClipboardString(stdscr, 'clipboard', 0, 2, width)
        _addClipboardString(stdscr, 'primary', 1, 2, width)
        _addClipboardString(stdscr, 'tmux', 2, 2, width)
        #stdscr.addstr(3, 3, 'Width = {}, Height = {}'.format(width, height))
        i = (i + 1) % len(TICKERS)
        k = stdscr.getch()
        if k == QUIT_CH:
            break
        elif k == curses.KEY_RESIZE:
           height, width = stdscr.getmaxyx()



if __name__ == '__main__':
    # Use curses wrapper to handle init and safe teardown
    curses.wrapper(main)
