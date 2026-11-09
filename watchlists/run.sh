#!/bin/sh
set -eu
umask 077
mkdir -p /data/watchlists
if [ -f /data/options.json ]; then
  cp /data/options.json /data/watchlists/options.json
else
  printf '{}' > /data/watchlists/options.json
fi
chown -R watchlists:watchlists /data/watchlists
chmod 600 /data/watchlists/options.json
export WATCHLIST_OPTIONS=/data/watchlists/options.json
exec gosu watchlists sh -c '
  Xvfb :99 -screen 0 1280x900x24 -nolisten tcp >/dev/null 2>&1 &
  display_pid=$!
  trap "kill $display_pid 2>/dev/null || true" EXIT TERM INT
  python -m app.main &
  app_pid=$!
  trap "kill $app_pid $display_pid 2>/dev/null || true" EXIT TERM INT
  wait "$app_pid"
'
