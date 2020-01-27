#!/bin/bash
# AppliesTo: linux
# RemoveExtension: True

hash=`md5sum $1`
echo "MD5 hash: $hash"
echo "=================================================================="
cat $1
echo "=================================================================="
echo "MD5 hash: $hash"
