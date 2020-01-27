#!/bin/bash
# AppliesTo: linux
# AppliesTo: oberon
# PublicPermissions: True
# RemoveExtension: True
# Performs an emergency backup to compact flash

echo ">> Building file archives..."
/etc/cron.daily/bak-04-build-archives
echo ">> Copying archives to CF..."
/etc/cron.weekly/bak-04-copy-to-cf
echo ">> CF may now be removed"

echo ">> Performing backup to local drive..."
/etc/cron.daily/aa-activate-backup-drive
/etc/cron.daily/bak-02-copy-local
/etc/cron.daily/zz-deactivate-backup-drive
echo ">> Backup to local drive complete"
