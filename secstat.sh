#!/bin/bash

#=====================================================
# This script outputs a pretty terse and fairly stable
# reprentation of the security relevant configuration
#=====================================================
# AppliesTo: linux
# RemoveExtension: True
#=====================================================


bash_pid=`ps -C bash -o pid= | tr -d ' '`
#echo "#$bash_pid#"
echo "Active processes on "`uname -n`
#echo "ps -N --pid 2,$bash_pid,$$ --ppid 2,$bash_pid,$$ -o f,ruser,euser,cmd --sort=cmd,f | uniq -c"
ps -N --pid 2,$bash_pid,$$ --ppid 2,$bash_pid,$$ -o f,ruser,euser,cmd --sort=cmd,f | uniq -c
netstat -an
