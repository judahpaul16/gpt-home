#!/bin/bash
set -e

# Start D-Bus
mkdir -p /var/run/dbus
dbus-daemon --system --fork

# Start Avahi daemon for mDNS (gpt-home.local)
/usr/sbin/avahi-daemon --no-rlimits --daemonize

# Run spotifyd in foreground
exec /usr/local/bin/spotifyd --no-daemon
