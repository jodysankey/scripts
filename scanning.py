#!/usr/bin/python3
#========================================================
# Python script for linux to make and scale scans.
# relies on scanimage (SANE) for the scanning and
# ImageMagick for the image manipulation 
#========================================================
# Copyright Jody M Sankey 2010 - 2018
#========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
#========================================================


import sys
import os
import glob
import re
import subprocess
import itertools
import math
import collections


# Define constants
SCAN_PATH = os.path.expanduser("~/tmp/scan")
SCAN_NAME = "scan_"
RECENT_SECONDS = 3600

# Gamma4SI arguments are: gamma, floor, ceiling, table_size
GAMMA_TABLE = subprocess.check_output(["gamma4scanimage","1.2","200","3500","4095"]).decode("utf-8")

if 'SCANNER_URL' not in os.environ:
    print('Could not find a SCANNER_URL environment variable')
    sys.exit(1)
SCANNER_URL = os.environ['SCANNER_URL']
BASE_SCAN_COMMAND = "scanimage -d '{}' --buffer-size=1024 --format=tiff --mode=Color".format(SCANNER_URL)
BASE_SCAN_SUFFIX = ("--res=300") # HP scanner resets resolution unless it is the last argument
BASE_CONVERT_COMMAND = ("convert ")

sources = [
    {'labels':('p','platen'),
     'description':'Flatbed, single sheet',
     'multi':'off',
     'scan':'--source=Platen'},
    {'labels':('m','manual'),
     'description':'Flatbed, confirm each sheet',
     'multi':'manual',
     'scan':'--source=Platen'},
    {'labels':('1','simplex'),
     'description':'ADF, single sided',
     'multi':'driver',
     'scan':"--source=ADF"},
    {'labels':('2','duplex'),
     'description':'ADF, double sided',
     'multi':'driver',
     'flip_even':True,
     'scan':"--source=Duplex"},
    {'labels':('3','dualsimplex'),
     'description':'ADF, single sided, fed twice',
     'multi':'double',
     'scan':"--source=ADF"},
    {'labels': ('f','dualsimplex-front'),
     'description': 'ADF, single sided, fed front side',
     'multi': 'driver',
     'skip_alternate': 'forward',
     'scan': "--source=ADF"},
    {'labels': ('b','dualsimplex-back'),
     'description': 'ADF, single sided, fed back side in reverse',
     'multi': 'driver',
     'skip_alternate': 'backward',
     'scan': "--source=ADF"},
]

papers = [
    {'labels':('l','letter'),
     'description':'US Letter /ANSI A',
     'scan':'-x 212 -y 279',
     'scan_conditional': {
         'simplex': '-l 3',
         'dualsimplex': '-l 3',
         'dualsimplex-front': '-l 3',
         'dualsimplex-back': '-l 3',
         'duplex': '-l 3'}},
    {'labels':('p','payslip'),
     'description':'Payslip non standard',
     'scan':'-x 191 -y 241',
     'scan_conditional': {
         'simplex': '-l 15',
         'dualsimplex': '-l 15',
         'dualsimplex-front': '-l 15',
         'dualsimplex-back': '-l 15',
         'duplex': '-l 15'}},
    {'labels':('g','legal'), 'description':'US Legal ',
     'scan':'-x 212 -y 355',
     'scan_conditional':{
         'simplex': '-l 3',
         'dualsimplex': '-l 3',
         'dualsimplex-front': '-l 3',
         'dualsimplex-back': '-l 3',
         'duplex': '-l 3'}},
    {'labels':('4','a4'),
     'description':'ISO A4',
     'scan':'-x 210 -y 297',
     'scan_conditional':{
         'simplex': '-l 5',
         'dualsimplex': '-l 5',
         'dualsimplex-front': '-l 5',
         'dualsimplex-back': '-l 5',
         'duplex': '-l 5'}},
    #{'labels':('a','auto'),'description':'(Attempt) auto cropping','crop':False,
    # 'scan':'','sources':{}, 'convert':'-trim +repage'},
]

#Note order is important for convert, 'convert' gets added before 'color' or 'gray'
scales = [
    {'labels':('s','small'),'description':'Small (40% 300dpi)',
     'file_type':'png',
     'convert':'-resize 40%',
     'convert_color':'-colors 32 -contrast -despeckle -colors 32',
     'convert_gray':'-colorspace gray -colors 8 -contrast -despeckle -colorspace gray -colors 8'},
    {'labels':('m','medium'),'description':'Medium (60% 300dpi)',
     'file_type':'jpg',
     'convert':'-resize 60%'},
    {'labels':('l','large'),'description':'Large (Unscaled 300dpi)',
     'file_type':'jpg',
     'convert':''},
]

colors = [
    {'labels':('c','color','colour'),'description':'All pages colour',
     'first_col':True,
     'other_col':True},
    {'labels':('g','gray','grey'),'description':'All pages greyscale',
     'first_col':False,
     'other_col':False},
    {'labels':('f','first'),'description':'First page colour, others greyscale',
     'first_col':True,
     'other_col':False},
]

class ScanError(Exception):
    def __init__(self, message):
        self.message = message

class Customization(object):
    def __init__(self, purpose, dictionary):
        self.purpose = purpose
        for k in dictionary:
            setattr(self, k, dictionary[k])
    def attribute(self, attribute_name, conditional_names):
        ret = []
        if hasattr(self, attribute_name):
            ret.append(getattr(self, attribute_name))
        if hasattr(self, attribute_name + "_conditional"):
            conditional = getattr(self, attribute_name + "_conditional")
            ret.extend([conditional[k] for k in conditional if k in conditional_names])
        return ret        

class CustomizationSet(object):
    def __init__(self):
        self.customizations = []
    def append(self, new_customization):
        self.customizations.append(new_customization)
    def firstValue(self, key):
        for c in self.customizations:
            if hasattr(c, key):
                return getattr(c, key)
        return None
    def summary(self, leader):
        lines = ["{}{:10} {}".format(leader, c.purpose, c.description) for c in self.customizations]
        return "\n".join(lines)
    def labels(self):
        label_lists = [c.labels for c in self.customizations]
        return list(itertools.chain.from_iterable(label_lists))
    def scanFlags(self):
        flag_lists = [c.attribute("scan", self.labels()) for c in self.customizations]
        return list(itertools.chain.from_iterable(flag_lists))
    def convertFlags(self, is_color):
        flag_lists = [c.attribute("convert", self.labels()) for c in self.customizations]
        if is_color:
            flag_lists.extend([c.attribute("convert_color", self.labels()) for c in self.customizations])
        else:
            flag_lists.extend([c.attribute("convert_gray", self.labels()) for c in self.customizations])
        return list(itertools.chain.from_iterable(flag_lists))


#Subroutines
def printOptionSet(option_set, leader):
    """Print a line for each option in the set, prefixed with leader"""
    for option in option_set:
        labels = ",".join(option['labels'])
        option_set = leader + labels + " "*(20-len(labels)) + "- " + option['description']
        print(option_set)

def findOptionOrDie(option_set, label):
    """Return the option containing label, or None if not found"""
    label = label.lower()
    for option in option_set:
        if label in option['labels']:
            return option
    die("Invalid option: " + label)

def beep():
    subprocess.check_call([
        'play', '--no-show-progress', '--null', '--channels', '1',
         'synth', '1.5',
         'sine', '1200' if beep.high else '880'])
    beep.high = not beep.high
beep.high = False

def printUsage():
    """Print standard help string then quit"""
    leader = "        "
    print("\n  Usage: scanning [-v|-c|-k=N] SOURCE PAPER SCALE COLOR [basename]\n")
    print("  SOURCE  Paper source:")
    printOptionSet(sources, leader)
    print("  PAPER    Paper size:")
    printOptionSet(papers, leader)
    print("  SCALE    Scaling factor:")
    printOptionSet(scales, leader)
    print("  COLOR    Colour mode:")
    printOptionSet(colors, leader)
    print("  basename Desired base filename, optionally including path")
    print("  -v       View each scan when conversion is complete") 
    print("  -c       Confirm each scan before saving in final location\n") 
    print("  -k=N     Do not convert page N of scan\n") 
    print("SCANNING Script (c)2010 Jody Sankey")
    v = sys.version_info
    print("Currently running in Python v{}.{}.{}\n".format(*v))
    sys.exit()

def die(print_string):
    """Prints the specified string then exits with code 1"""
    print(print_string)
    sys.exit(1)

def largestFilenameInDir(path, pattern):
    """Returns the largest numbered file matching pattern in dir"""
    regex_pat = pattern.replace('%','([0-9]{3})')
    max_page = 0
    for f in os.listdir(path):
        match = re.search(regex_pat, f)
        if match is not None and int(match.groups()[0]) > max_page:
            max_page = int(match.groups()[0])
    return max_page


# Scanning and conversion subroutines


def getStartOutputPage(dest, file_type):
    """Returns the initial output page number to avoid existing files."""
    start_page = 1
    if dest:
        (dest_dir, dest_name) = os.path.split(dest)
        if not dest_name: 
            die("ERROR: Supplied path must include filename") 
        if dest_dir:
            dest_dir = os.path.expanduser(dest_dir)
            if not os.path.isdir(dest_dir):
                die("ERROR:Supplied path '{}' does not exist".format(dest_dir))
            dest = os.path.join(dest_dir, dest_name)
        else:
            dest = os.path.join(SCAN_PATH, dest_name)
    
        if os.path.isfile("{}.{}".format(dest, file_type)):
            start_page += 1
        while (os.path.isfile("{} p{}.{}".format(dest, start_page, file_type))
            or os.path.isfile("{} p0{}.{}".format(dest, start_page, file_type)) 
            or os.path.isfile("{} p00{}.{}".format(dest, start_page, file_type))):
            start_page += 1
        if start_page > 1:
            print("Destination already exists, start at page {}".format(start_page))
    return start_page
     

def getStartScanIndex(dest, file_type):
    """Returns the initial scan index to avoid existing scan files or direct retypes"""
    start_num = largestFilenameInDir(SCAN_PATH, SCAN_NAME + "%.tif") + 1
    if not dest:
        start_num = max(start_num, largestFilenameInDir(SCAN_PATH, SCAN_NAME+'%.'+file_type) + 1)
    return start_num
 

def batchScanimage(base_command, start_num):
    """Calls the scanimage command given by base_command in batch scan mode
    beginning at start_num and checks the return code"""
    full_command = (base_command + 
        " --batch='{}/{}%03d.tif' --batch-start={}".format(SCAN_PATH, SCAN_NAME, start_num))
    #print(full_command)
    ret = subprocess.call(full_command, shell=True)
    if ret and ret != 7: #Error 7 is out of documents when doing a batch feed
        raise ScanError("ERROR {} calling scanimage".format(ret))
 
 
def singleScanimage(command, num):
    """Calls the scanimage command given by base_command in single scan mode for
    index num, checks the return code, and returns the filename"""
    scan_file = scanFileName(num)
    ret = subprocess.call("{} > '{}'".format(command, scan_file), shell=True)
    if ret: 
        raise ScanError("ERROR {} calling scanimage".format(ret))
    return scan_file

 
def scanFileName(index):
    return "{0}/{1}{2:0>3}.tif".format(SCAN_PATH, SCAN_NAME, index)


def acquireScans(dest, customizations, scan_start_index, output_start_index):
    """Runs an external command to acquire a set of scans and returns:
    1. A list of filenames,
    2. A dictionary of whether invertion is required for each filename
    3. A dictionary of output indices for each filename
    4. The error produced during scanning if one exists"""

    flags = customizations.scanFlags()
    command = " ".join([BASE_SCAN_COMMAND] + customizations.scanFlags() + [BASE_SCAN_SUFFIX])

    scans = []
    index_map = dict()
    invertion_map = collections.defaultdict(bool) # Invertion is false unless otherwise speciified
    mode = customizations.firstValue('multi')
    error = None
    if mode == 'driver':
        try:
            batchScanimage(command, scan_start_index)
        except ScanError as err:
            print("Caught scan error during scan, continuing to process remaining images")
            error = err
        end_scan_index = largestFilenameInDir(SCAN_PATH, SCAN_NAME + "%.tif")
        if customizations.firstValue('flip_even'):
            for num in range(scan_start_index, end_scan_index + 1):
                # The duplexer scans every other sheet upside down, need to mark these now while we're
                # certain which images it applies to (mogrify to flip the raw image was extremely slow)
                invertion_map[scanFileName(num)] = (num - scan_start_index) % 2 > 0
        for num in range(scan_start_index, end_scan_index + 1):
            scans.append(scanFileName(num))
            if customizations.firstValue('skip_alternate') == 'forward':
                index_map[scanFileName(num)] = output_start_index + (num - scan_start_index) * 2
            elif customizations.firstValue('skip_alternate') == 'backward':
                index_map[scanFileName(num)] = output_start_index + (end_scan_index - num) * 2
            else:
                index_map[scanFileName(num)] = output_start_index + (num - scan_start_index)

    elif mode == 'double':
        print("Load the document front side of first sheet up")
        start_index_front = scan_start_index
        try:
            batchScanimage(command, start_index_front)
        except ScanError as err:
            print("Caught scan error during scan, continuing to process remaining images")
            error = err
            error.message += " (during front side scan)"
        end_index_front = largestFilenameInDir(SCAN_PATH, SCAN_NAME + "%.tif")
        num_sheets = end_index_front - start_index_front + 1
        for num in range(start_index_front, end_index_front + 1):
            scans.append(scanFileName(num))
            index_map[scanFileName(num)] = output_start_index + (num - start_index_front) * 2

        if error is None:
            input('Load the document back side of last page up then press enter')
            start_index_back = end_index_front + 1
            try:
                batchScanimage(command, start_index_back)
            except ScanError as err:
                print("Caught scan error during scan, continuing to process remaining images")
                error = err
                error.message += " (during back side scan)"
            end_index_back = largestFilenameInDir(SCAN_PATH, SCAN_NAME + "%.tif")
            if (end_index_back - start_index_back + 1) != num_sheets:
                num_sheets = max(num_sheets, end_index_back - start_index_back + 1)
                if error is None:
                    error = ScanError("Number of front and back pages don't match")
            for num in range(start_index_back, end_index_back + 1):
                scans.append(scanFileName(num))
                index_map[scanFileName(num)] = ((output_start_index + (2 * num_sheets) - 1)
                        - ((num - start_index_back) * 2))

    elif mode == 'manual':
        num = scan_start_index
        out = output_start_index
        try:
            while True:
                scans.append(singleScanimage(command, num))
                index_map[scanFileName(num)] = out
                #beep()
                answer = input('Return to scan another or any other key to stop: ')
                if answer != '':
                    break
                num += 1
                out += 1
        except ScanError as err:
            print("Caught scan error during scan, stopping manual scan")
        
    else:
        scans.append(singleScanimage(command, scan_start_index))
        index_map[scanFileName(scan_start_index)] = output_start_index

    return scans, invertion_map, index_map, error
    

def removeKilledFiles(files, kill_indices, index_map):
    """Removes a set of files from a list of filenames, both deleting on disk and removing from
    the list. Files to remove are specified as list indices."""
    kill_indices.sort()
    kill_indices.reverse()
    for kill in kill_indices:
        if kill <= len(files):
            kill_file = files[kill-1]
            kill_output = index_map[kill_file]
            os.remove(kill_file)
            files.remove(kill_file)
            # TODO: renumbering based on index map not yet tested
            del index_map[kill_file]
            for f in index_map:
              if index_map[f] > kill_output: index_map[f] = index_map[f] - 1
        else:
            print("WARNING: Page {} was not created so could not be killed".format(kill))
    return files
   

def answerQuestionInteractively(question): 
    """Returns True or False for t yes/no question to the user"""
    while True:
        answer = input(question + '? [Y or N]: ')
        if answer.lower() == 'y':
            return True
        elif answer.lower() == 'n':
            return False
    
    
def removeUnwantedFiles(files, index_map):
    """Removes a set of files from a list of filenames, where the set is selected 
    interactively by presenting the user with thumbnails of the file contents"""
    # TODO: The output indices map also needs to be renumbered to account for the deletions
    kill_indices = []
    for i, f in zip(range(len(files)), files):
        subprocess.call("display -resize 25% '{}'".format(f), shell=True)
        if not answerQuestionInteractively('Keep ' + f):
            kill_indices.append(i)
    return removeKilledFiles(files, kill_indices, index_map)


def outputFormatString(dest, num_digits, extention):
    return "{} p{{:0{}d}}.{}".format(dest, num_digits, extention)


def renumberExistingFiles(dest, num_digits, extention, start_page):
    """Renames existing files so all use the specified num of digits"""
    unnumbered_format = "{}.{}".format(dest, extention)
    output_format = outputFormatString(dest, num_digits, extention)
    lesser_formats = [outputFormatString(dest, d, extention) for d in range(1, num_digits)]

    # Do the had-no-num case first
    if os.path.isfile(unnumbered_format) and not os.path.isfile(output_format.format(1)):
        os.rename(unnumbered_format, output_format.format(1))
    # Then all smaller formats
    for num, fmt in itertools.product(range(start_page), lesser_formats):
        if (os.path.isfile(fmt.format(num)) and not os.path.isfile(output_format.format(num))):
            os.rename(fmt.format(num), output_format.format(num))
    
    
def convertScans(scans, invertion_map, index_map, customizations, dest, extention, num_digits):
    """Convert a set of raw scans into the desired output format and filename."""
    outputs = []
    for scan_file in scans:
        if not dest:
            new_file = scan_file.replace("tif", extention)
        elif len(scans)==1 and index_map[scans[0]] == 1:        
            new_file = "{}.{}".format(dest, extention)
        else:
            new_file = outputFormatString(dest, num_digits, extention).format(index_map[scan_file])

        is_color = (customizations.firstValue('first_col') if scan_file == scans[0] 
                    else customizations.firstValue('other_col'))
        command = "{} '{}' {} {} '{}'".format(BASE_CONVERT_COMMAND,
            scan_file,
            "-rotate 180" if invertion_map[scan_file] else "", 
            " ".join(customizations.convertFlags(is_color)),
            new_file)
        #print(command)

        ret_val = subprocess.call(command, shell=True)
        if ret_val != 0 and not os.path.exists(new_file):
            print("WARNING: Could not convert {} (error code: {})".format(scan_file, ret_val))
        else:
            if ret_val != 0:
              print('Converted {} to {} (but convertion returned error code {})'.format(scan_file, new_file, ret_val))
            else:
              print('Converted {} to {}'.format(scan_file, new_file))
            os.remove(scan_file)
            outputs.append(new_file)
    return outputs


def scanAndConvert(dest, customizations, view, check, kills):
    """Do the bulk of the work to execute scans and convert"""

    file_type = customizations.firstValue("file_type")
    output_start_page = getStartOutputPage(dest, file_type)
    scan_start_index = getStartScanIndex(dest, file_type)
    
    # Summarize what we're going to do
    print(customizations.summary("   "))
    print("   Dest       " + (dest if dest else SCAN_PATH))
    print("   InitialNum " + str(scan_start_index))
    print("   InitialOutput p" + str(output_start_page))

    # Do the scanning and remove unwanted pages
    scans, invertion_map, index_map, error = acquireScans(dest, customizations, scan_start_index, output_start_page) 
    scans = removeKilledFiles(scans, kills, index_map)
    if check:
        scans = removeUnwantedFiles(scans, index_map)
    if len(scans) == 0:
        die("ERROR: Could not find any remaining scans to process")

    # Calculate the file output formats and renumber existing files if required
    output_max_page = max(index_map.values())
    num_digits = int(math.log(float(output_max_page), 10)) + 1
    renumberExistingFiles(dest, num_digits, file_type, output_start_page)
    
    # Do the conversion
    outputs = convertScans(scans, invertion_map, index_map, customizations, dest, file_type, num_digits)

    # Display a warning if an error occured
    if error is not None:
        print("WARNING: ERROR DURING SCANNING, OUTPUT MAY BE INCOMPLETE " + error.message)

    #Finally show the user what we've created, if they are interested
    if view:
        for output in outputs:
            subprocess.call("display -resize 25% '{}' &".format(output), shell=True)


def performScan(dest, source, paper, scale, color, view, check, kills):
    # This is provided mainly for easy reuse from other modules

    # Parse each customization from the supplied string
    customizations = CustomizationSet()
    customizations.append(Customization("Source", findOptionOrDie(sources, source)))
    customizations.append(Customization("Paper",  findOptionOrDie(papers,  paper)))
    customizations.append(Customization("Scale",  findOptionOrDie(scales,  scale)))
    customizations.append(Customization("Color",  findOptionOrDie(colors,  color)))
    # Call the function
    scanAndConvert(dest, customizations, view, check, kills)


if __name__ == '__main__':
    #If run as a script take parameters to feed the function from the command line

    #Just print usage if no arguments supplied
    if len(sys.argv)<2:
        printUsage()
    args = sys.argv[1:]

    #Declare and initialize the variables controlled by switch
    check = False
    view = False
    kills = []

    #Eat any switches from the front
    while len(args) and args[0].startswith('-'):
        arg = args.pop(0).lower()
        print("eating " + arg)
        mko = re.search(r"-k=([1-9]+)$", arg)
        if mko is not None:
            kills.append(int(mko.groups()[0]))
        elif arg == '-c':
            check = True
        elif arg == '-v':
            view = True
        elif arg == '--help':
            printUsage()
        else:
            die("ERROR: Switch '{}' not recognized".format(arg))
    
    # Do we have enough parameters left?
    if len(args) not in range(4,6):
        print(args)
        die("ERROR: Wrong number of parameters supplied")
    dest = os.path.join(SCAN_PATH, args[4]) if len(args) == 5 else None

    performScan(dest, args[0], args[1], args[2], args[3], view, check, kills)

