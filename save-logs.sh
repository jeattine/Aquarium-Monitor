#!/bin/bash
# Only run this if the system is in the process of shutting down
if [[ "$(systemctl is-system-running)" == "stopping" ]]; then
    if [ -f /tmp/aquamon.log ]; then
        rsync -a /tmp/aquamon.log /home/aquamon/reef_monitor/logs/aquamon.log
    fi
fi
