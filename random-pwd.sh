#!/bin/bash
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True

# Generates a printable random password of 12 characters.
head /dev/urandom | uuencode -m - | sed -n 2p | cut -c1-${1:-12}
