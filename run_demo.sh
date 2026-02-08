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

# Start server with stderr+stdout to server.log (tee so timestamps appear and dashboard can read it)
echo "Starting server (logging to server.log)..."
( ./server 2>&1 | tee server.log ) &
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
