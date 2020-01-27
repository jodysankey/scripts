#!/bin/bash
# AppliesTo: linux
# PublicPermissions: True
# RemoveExtension: True
# Just print the files in the script directory

public_dir=/usr/local/scripts
private_dir=~/files/code/scripts/private

echo ""
echo "Executable Public Scripts:"
ls -oghp "$public_dir" | egrep "^.{3}x" | grep -v '/$'
echo ""
if [ -d "$private_dir" ]; then
  echo "Executable Private Scripts:"
  ls -oghp "$private_dir" | egrep "^.{3}x" | grep -v '/$'
fi
