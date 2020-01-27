#!/bin/bash 
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True

# Attempt to clear stuck jobs from the cups queue 

# Most recent experience indicated turning the printer off after cups is shut down
# is important. Maybe put in a user prompt to do this, ie

# stop accepting jobs
# terminate cups
# prompt for printer off
# delete jobs in spool
# prompt for printer on
# cups on


#printer=`lpstat -p | head 1 | awk -F '-' '{print $1}'`
printer=`lpstat -p | head -n 1 | awk '{print $2}'`

#echo Printer = XX $printer XX
#lprm -P $printer

echo
echo Initial printer queue ........
lpq -P $printer 
echo

# Cool the printer down
cupsreject $printer
cupsdisable -c $printer

# Try CUPS cancel (usually doesn't work)
cancel -a $printer

# Shut down cups service
#/etc/init.d/cups stop  	# Old SysV init way
stop cups			# New upstart way

sleep 4

# Actually delete from the spool directory (this is the bit which needs root)
rm /var/spool/cups/*

# And kick things off again
sleep 2
#/etc/init.d/cups start  	# Old SysV init way
start cups			# New upstart way

cupsenable  $printer
cupsaccept $printer

echo
echo Final printer queue ........
lpq -P $printer 
echo
echo NOTE THIS SCRIPT MUST BE RUN AS ROOT TO WORK EFFECTIVELY
echo RUNNING WHILE PRINTER IS OFF WILL IMPROVE CHANCES OF SUCCESS
