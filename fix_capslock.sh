#!/bin/bash
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True

# Defines capslock key to behave as escape, configured in
# ~/.xsessionrc also but sometimes get dropped.
setxkbmap -option caps:escape
