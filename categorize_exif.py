#!/usr/bin/python3
# Categorize all files in the current specified directory using EXIF data.
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True

import argparse
import os
import EXIF

parser = argparse.ArgumentParser(description='Categorize photos in a directory according to an exif item')
parser.add_argument('--camera', dest='camera', default='NIKON D80',
                    help='Camera string used to filter images')
parser.add_argument('--exif', dest='exif', default='EXIF FocalLengthIn35mmFilm',
                    help='EXIF attribute to categorize')
parser.add_argument('--bin', dest='bin', 
                    help='Bin size to group integer attributes')
parser.add_argument(dest='directory', metavar='DIR',
                    help='Directory to search')

CAMERA_EXIF = 'Image Model'
PRINT_SPACING = 100

def print_dict(dic):
  """Prints the keys and values in a dictionary in order."""
  print(', '.join(['{}:{}'.format(k, dic[k]) for k in sorted(dic.keys())]))

if __name__ == '__main__':
  args = parser.parse_args()
  results = {}
  index = 0
  for (dirpath, dirnames, filenames) in os.walk(args.directory):
    for filename in filenames:
      qualified_filename = os.path.join(dirpath, filename)
      try:
        f = open(qualified_filename, 'rb')
        exif_data = EXIF.process_file(f)
        if not exif_data:
          pass
          #print('No exif data found in ' + qualified_filename)
        elif CAMERA_EXIF not in exif_data:
          print('No camera model found in ' + qualified_filename)
        elif exif_data[CAMERA_EXIF].values.decode('utf-8') != args.camera:
          print('{} taken with {} not {}'.format(
              filename, exif_data[CAMERA_EXIF].values.decode('utf-8'), args.camera))
        elif args.exif not in exif_data:
          print('Attribute {} not found in {}'.format(args.exif, filename))
        else:
          index += 1
          values = exif_data[args.exif].values
          value = values[0] if len(values) == 1 else values
          #print('{} {} = {}'.format(filename, args.exif, value))
          if value not in results:
            results[value] = 1
          else:
            results[value] += 1
          if index % PRINT_SPACING == 0:
            print_dict(results)
      except IOError as e:
        print('Error reading {}: {}'.format(filename, e))
  print_dict(results)

