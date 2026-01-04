#!/bin/bash
# Quick demo script to run all components

echo "=== UDP Packet Processor Demo ==="
echo ""
echo "This script will:"
echo "1. Build the server and monitor"
echo "2. Start the server in the background"
echo "3. Start the monitor in the background"
echo "4. Run the client for 10 seconds"
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

# Start server
echo "Starting server..."
./server &
SERVER_PID=$!
sleep 2

# Start monitor
echo "Starting monitor..."
./monitor &
MONITOR_PID=$!
sleep 1

# Run client for 10 seconds
echo "Running client for 10 seconds at 2000 pps..."
python3 client.py --rate 2000 --duration 10

# Cleanup
echo ""
echo "Stopping server and monitor..."
kill $SERVER_PID 2>/dev/null
kill $MONITOR_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
wait $MONITOR_PID 2>/dev/null

echo "Demo complete!"

