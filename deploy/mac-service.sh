#!/usr/bin/env bash
# Run Atlas in the background on macOS: starts at login, restarts if it crashes.
# Usage: deploy/mac-service.sh install | start | stop | restart | status | logs | uninstall
# Keep the project outside iCloud-synced folders (Desktop/Documents): offloaded files freeze Python.
set -euo pipefail
LABEL="com.atlas.assistant"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$DIR/logs"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
  install)
    mkdir -p "$LOGS" "$(dirname "$PLIST")"
    cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$DIR/.venv/bin/python</string><string>-m</string><string>atlas</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LOGS/atlas.log</string>
  <key>StandardErrorPath</key><string>$LOGS/atlas.log</string>
</dict></plist>
PLIST
    echo "Installed $PLIST (not started). Run: $0 start" ;;
  start)   launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null || launchctl kickstart -k "$DOMAIN/$LABEL"; echo "started" ;;
  stop)    launchctl bootout "$DOMAIN/$LABEL" && echo "stopped" ;;
  restart) launchctl kickstart -k "$DOMAIN/$LABEL" && echo "restarted" ;;
  status)  launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "state|pid|last exit" || echo "not running" ;;
  logs)    tail -n 50 -f "$LOGS/atlas.log" ;;
  uninstall) launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true; rm -f "$PLIST"; echo "uninstalled" ;;
  *) echo "usage: $0 install|start|stop|restart|status|logs|uninstall"; exit 1 ;;
esac
