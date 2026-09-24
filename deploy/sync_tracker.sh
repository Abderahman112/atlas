#!/usr/bin/env bash
# Run on your Mac (e.g. hourly via cron/launchd) to keep the server's copy of the co-op tracker fresh.
# Usage: SERVER=user@your-vps ./deploy/sync_tracker.sh
set -euo pipefail
rsync -az "$HOME/Desktop/Co-op Automation/Co-op Tracker.xlsx" "${SERVER:?set SERVER=user@host}:~/atlas/data/"
