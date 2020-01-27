#!/bin/bash
#=====================================================
# This script does a human readable DU on the specified
# path to the specified depth
# Usage 1: dud 2 - Depth 2 on cwd
# Usage 2: dud 3 /usr - Depth 3 on /usr
#=====================================================
# AppliesTo: linux
# PublicPermissions: True
# RemoveExtension: True
#=====================================================

if [ "$2" == "" ]; then
  du -h --max-depth=$1 .
else
  du -h --max-depth=$1 $2
fi
