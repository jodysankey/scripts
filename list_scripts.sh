#!/bin/bash
# AppliesTo: linux
# PublicPermissions: True
# RemoveExtension: True
# Just print the files in the script directory

dir=/usr/local/scripts
echo ""
echo "Executable Scripts:"
ls -ogh $dir | egrep "^.{3}x" 
echo ""
echo "Unexecutable Scripts:"
ls -ogh $dir | egrep "^.{3}-" 
echo ""
