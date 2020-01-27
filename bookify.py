#!/usr/bin/python3
# -*- coding: utf-8 -*-
#===========================================================
# Creates individual jpg pages from scans of double page
# sheets in the current directory.
#
# Usage:
#  bookify book_name [output_dir]
#
# Scans should be named as follows:
#   "book_name Cover pX"
#   "book_name I pX" (inside sheet starting at centrefold)
#   "book_name O pX" (outside sheet starting at
#                     first/last pages}
#
# The number of inside and outside sheets must match.
# Cover can either be one sheet that is the outside or two
# sheets that are the inside and outside.
# 
# If output dir is omitted current directory will be used.
#
# This is still a pretty rough script written in a couple
# of hours to solve a particular problem.
#========================================================
# Copyright Jody M Sankey 2018
#========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
#========================================================



import math
import os
import subprocess
import sys


def splitImage(source_fn, lhs_fn, rhs_fn):
  print('Splitting {} into {} and {}'.format(
      source_fn, lhs_fn, rhs_fn))
  w, h = [int(d) for d in subprocess
      .check_output(['convert', source_fn, '-format', '%w %h', 'info:'])
      .decode()
      .split()]
  lhs_dim = '{}x{}+0x0'.format(int(w/2), h)
  rhs_dim = '{}x{}+{}x0'.format(int(w/2), h, int(w/2))
  subprocess.check_call(['convert', source_fn, '-crop', lhs_dim, lhs_fn])
  subprocess.check_call(['convert', source_fn, '-crop', rhs_dim, rhs_fn])
  

def die(error):
  print(error)
  sys.exit(1)


def processScans(filenames, book_name, out_dir):
  covers = sorted([f for f in filenames if (book_name + ' Cover' in f)])
  insides = sorted([f for f in filenames if (book_name + ' I p' in f)])
  outsides = sorted([f for f in filenames if (book_name + ' O p' in f)])
  if len(covers) < 1 or len(covers) > 2:
    die('Wrong number of cover sheets')
  if len(insides) != len(outsides):
    die("Inside and outside sheet counts don't match")
  if len(insides) < 1:
    die('No sheets found')

  N = len(insides)
  C = len(covers)
  total_pages = 2 * (len(covers) + len(insides) + len(outsides))
  num_digits = int(math.log(float(total_pages), 10)) + 1

  page_fmt = 'p{{:0{}d}}'.format(num_digits)
  fmt = '{} {}.jpg'.format(os.path.join(out_dir, book_name), page_fmt)

  splitImage(covers[0], fmt.format(total_pages), fmt.format(1))
  if C == 2:
    splitImage(covers[1], fmt.format(2), fmt.format(total_pages - 1))
  for i, f in enumerate(outsides, start=1):
    splitImage(f, fmt.format(2*(2*N - i) + 2 + C), fmt.format(2*i + C - 1))
  for i, f in enumerate(insides, start=1):
    splitImage(f, fmt.format(2*(N - i) + 2 + C), fmt.format(2*(N + i) + C - 1))


if __name__ == '__main__':
  book_name = sys.argv[1]
  out_dir = sys.argv[2] if len(sys.argv) > 2 else ""
  processScans(os.listdir(), book_name, out_dir)
