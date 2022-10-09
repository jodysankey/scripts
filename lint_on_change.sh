#!/bin/bash
#========================================================
# Calls pylint on the supplied file when it changes
#========================================================
# Copyright Jody M Sankey 2022
#========================================================
# AppliesTo: linux
# AppliesTo: client
# RemoveExtension: True
# PublicPermissions: True
#========================================================
pylint $1
while inotifywait -e close_write $1
do
  pylint $1
done
