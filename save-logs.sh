#!/bin/bash
# Only run this if the system is in the process of shutting down
if [[ "$(systemctl is-system-running)" == "stopping" ]]; then
    if [ -f /tmp/log.txt ]; then
        rsync -a /tmp/log.txt /home/aquamon/reef_monitor/logs/log.txt
    fi
fi