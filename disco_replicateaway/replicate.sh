#!/usr/bin/env bash

# Will check if there are nodes blacklisted for ddfs but not fully replicated yet.
# If this is the case, it will run the GC as long as all data is not replicated away.

# debug
#set -x

# Treat unset variables as an error when substituting.
set -u

# master
HOST=disco.example.com:8989
DDFS_URL="http://$HOST/ddfs/ctrl"
DISCO_URL="http://$HOST/disco/ctrl"

# API commands
GC_STATUS=$DDFS_URL/gc_status
GC_START=$DDFS_URL/gc_start
BLACKLIST=$DISCO_URL/get_gc_blacklist
SAFE_GC=$DDFS_URL/safe_gc_blacklist

# counter to mark how many times the GC ran.
CNT=0

function is_running {
    # will get "" if GC not running, or a string describing the current status.
    _GC_RES=$(wget -q -O- $GC_STATUS)
    if [ "$_GC_RES" == '""' ]
    then
        _GC_RES=''
    fi
    echo $_GC_RES
}

function is_safe {
    _BLACKLISTED=$(wget -q -O- $BLACKLIST)
    _SAFE=$(wget -q -O- $SAFE_GC)

    # eg.
    # blacklisted:  ["slave1","slave2","slave3"]
    # safe_gc_blacklist: []

    # safe is a subset of get. If we concat the 2 (de-jsonised) and get uniques, we have 2 cases:
    # - no uniques =&gt; all nodes are safe (in blacklist *and* in safe)
    # - uniques =&gt; some nodes are not safe

    echo "$_BLACKLISTED $_SAFE" | tr -d '[]"' | tr ', ' '\n' | sort | uniq -u
}

while true
do

    GC_RES=$(is_running)

    if [ -z "$GC_RES" ]
    then
        echo "GC not running, let's check if it is needed."
        NON_SAFE=$(is_safe)
        if [ -z "$NON_SAFE" ]
        then
            echo "All nodes are safe for removal."
            exit
        else
            echo "Somes nodes are not yet safe: $NON_SAFE"
            CNT=$((CNT+1))
            date +'%Y-%m-%d %H:%M:%S'
            wget -q -O /dev/null $GC_START
            echo "Run $CNT started."
        fi
    else
        echo "GC running ($GC_RES). Let's wait".
    fi
    sleep 60
done