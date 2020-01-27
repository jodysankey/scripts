#!/usr/bin/python3
#========================================================
# Python script to call ImageMagick on a series of
# pictures in a directory, shrinking to approximately
# the same size appropriate for web use
#========================================================
# Copyright Jody M Sankey 2009
#========================================================
# $HeadURL$
# Last $Author$
# $Revision$
# $Date$
#========================================================
# AppliesTo: linux, windows
# RemoveExtension: True
# PublicPermissions: True
#========================================================


# Declare a few constants
MAX_SIZE = 2000
MIN_SIZE = 1600

# Imports
import sys
import re
import glob
from subprocess import check_output, call
#import pdb


#Subroutines
def printUsage():
	"""Print standard help string then quit"""
	print("ShrinkPictures Script (c)2009 Jody Sankey)")
	v = sys.version_info
	print("Currently running in Python v{}.{}.{}\n".format(v[0],v[1],v[2]))
	print("SHRINKPICTURES glob*\n")
	print("  glob  = Unix style file glob of files to shrink\n")
	sys.exit()

def jpegSize(filename):
	"""Return the width and height of the specified JPEG, in pixels"""
	if filename.lower().endswith(".jpg"):
	#if(re.search(r".jpg$",filename,flags=re.IGNORECASE)):
		ret = check_output('identify -ping "'+filename+'"',shell=True)
		mo = re.search(r" (\d+)x(\d+)",str(ret))

		if mo==None:
			print("Could not IDENTIFY size of",filename)
		else:
			# Be sure to return integers not strings
			return [int(sz) for sz in mo.groups()]
			#return [int(sz) for sz in str(ret[2]).split("x")]
	return



#Just print usage if no arguments
if len(sys.argv)<2:
	printUsage()

# Gather a list of all files which match the globs on the command line
files = []
for gl in sys.argv[1:]:
	for fn in glob.glob(gl):
		files.append(fn)

# Now go through, and for each that ends in .jpg get the size
count = 0
for fn in files:
	#print(fn)
	sz = jpegSize(fn)
	if sz:
		lng = max(sz)

		# Check if we're already small enough
		if lng<=MAX_SIZE:
			print("{} is already small enough ({}x{})".format(fn,sz[0],sz[1]))
			continue

		#pdb.set_trace()

		# We prefer factors of 2, so see if any are in range
		fac = 1.0;
		while lng/fac>MAX_SIZE:
			fac*=2.0

		# If not, just aim for the mid point
		if lng/fac<MIN_SIZE: fac = lng/((MIN_SIZE+MAX_SIZE)/2)

		# Finally do and report the work
		newsz = [round(axis/fac) for axis in sz]
		command = 'mogrify -quality 98 -resize {}x{} "{}"'.format(newsz[0],newsz[1],fn)
		#print(command)
		call(command,shell=True)
		print("{} Scaled from {}x{} to {}x{} \n".format(fn,sz[0],sz[1],newsz[0],newsz[1]));
		count += 1

print("Processed",count,"files")
