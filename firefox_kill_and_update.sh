#!/bin/bash 
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True

# Attempt to kill all instances of firefox and update the snap
# because the update process in 22.04 is broken.

echo KILLING FIREFOX
sudo killall firefox
echo ATTEMPTING REFRESH
sudo snap refresh
echo DONE

