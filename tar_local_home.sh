#!/bin/bash

# Simple script to build an archive of all the directories on a Kubuntu
# host that might be useful in configuring similar user settings on a
# different machine.

ARCHIVE=~/local_home.tar

if [ -f $ARCHIVE ] ; then
  echo "Removing existing $ARCHIVE"
  rm $ARCHIVE
fi

tar -cvf $ARCHIVE -C $HOME .atom \
   && tar -rvf $ARCHIVE -C $HOME .config \
   && tar -rvf $ARCHIVE -C $HOME .kde \
   && tar -rvf $ARCHIVE -C $HOME .thunderbird \
   && tar -rvf $ARCHIVE -C $HOME .vim \
   && tar -rvf $ARCHIVE -C $HOME .vscode \
   && tar -rvf $ARCHIVE -C $HOME .thunderbird \
   && tar -rvf $ARCHIVE -C $HOME .thunderbird \
   && echo "Created archive at $ARCHIVE"
