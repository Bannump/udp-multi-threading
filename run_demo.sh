#!/bin/bash
# Quick demo script to run all components

echo "=== UDP Packet Processor Demo ==="
echo ""
echo "This script will:"
echo "1. Build the server and monitor"
echo "2. Start the server (stderr+stdout to server.log, timestamps for dashboard)"
echo "3. Start the monitor (output to monitor.log)"
echo "4. Run the client for 15 seconds"
echo "   Logs are saved in server.log and monitor.log for future reference."
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

# Build
echo "Building..."
make clean
make

# Check if build succeeded
if [ $? -ne 0 ]; then
    echo "Build failed!"
    exit 1
fi

# Clean up any existing shared memory
echo "Cleaning up old shared memory..."
sudo rm -f /dev/shm/telecom_shm 2>/dev/null

# Clear server.log only if oldest entry is really older than 48h (do not delete recent logs)
# 48h = 172800 seconds
if [ -f server.log ]; then
  now_epoch=$(date +%s)
  first_ts=$(head -200 server.log | grep -oE '\[[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z\]' | head -1 | tr -d '[]')
  if [ -n "$first_ts" ]; then
    # Normalize for date: "2025-02-08T12:00:00.123Z" -> "2025-02-08 12:00:00" (portable parsing)
    first_ts_normalized=$(echo "$first_ts" | sed 's/T/ /; s/\.[0-9]*Z$//')
    first_epoch=$(date -d "${first_ts_normalized}" +%s 2>/dev/null)
    # Only clear if parsed epoch is valid and really > 48h ago (avoid clearing when date fails and returns 0)
    if [ -n "$first_epoch" ] && [ "$first_epoch" -gt 0 ] && [ "$first_epoch" -le "$now_epoch" ] && [ $((now_epoch - first_epoch)) -gt 172800 ]; then
      : > server.log
      echo "Cleared server.log (oldest entry older than 48h)."
    fi
  else
    # No timestamp in first 200 lines; use file mtime only if clearly old
    if [ "$(uname)" = "Linux" ]; then
      file_epoch=$(stat -c %Y server.log 2>/dev/null)
    else
      file_epoch=$(stat -f %m server.log 2>/dev/null)
    fi
    if [ -n "$file_epoch" ] && [ "$file_epoch" -gt 0 ] && [ $((now_epoch - file_epoch)) -gt 172800 ]; then
      : > server.log
      echo "Cleared server.log (file older than 48h)."
    fi
  fi
fi

# Start server with stderr+stdout appended to server.log (keep logs for 48h)
echo "Starting server (logging to server.log)..."
( ./server 2>&1 | tee -a server.log ) &
SERVER_PID=$!
sleep 2

# Start monitor with output to monitor.log for future reference
echo "Starting monitor (logging to monitor.log)..."
( ./monitor 2>&1 | tee monitor.log ) &
MONITOR_PID=$!
sleep 1

# Run client for 10 seconds with 0.5% invalid packets (so Dropped & validation tab shows entries)
echo "Running client for 15 seconds at 2000 pps (0.5%% invalid packets for drop/validation logs)..."
python3 client.py --rate 2000 --duration 15 --invalid-fraction 0.005

# Cleanup: kill process group (subshell + server + tee) so server and monitor actually stop
echo ""
echo "Stopping server and monitor..."
kill -TERM -$SERVER_PID 2>/dev/null
kill -TERM -$MONITOR_PID 2>/dev/null
sleep 2
# Force kill by name if still running (e.g. if process-group kill didn't reach them)
pkill -f './server' 2>/dev/null
pkill -f './monitor' 2>/dev/null
sleep 1

echo "Demo complete! Logs saved in server.log and monitor.log for future reference."
