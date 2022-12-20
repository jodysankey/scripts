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
inotifywait -e close_write,moved_to,create -m . |
while read -r directory events filename; do
  if [ "$filename" = "$1" ]; then
    pylint $1
  fi
done
