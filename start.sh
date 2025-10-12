#!/bin/bash
set -euo pipefail

echo "== start.sh: begin =="

# Install and start WAHA (WhatsApp HTTP API)
echo "Installing and starting WAHA..."
cd /home
wget -q -O waha.tar.gz "https://github.com/devlikeapro/waha/releases/download/v5.0.0/waha-linux-x64-5.0.0.tar.gz"
tar -xzf waha.tar.gz
chmod +x waha-linux-x64/waha

# Start WAHA in background on port 3000
echo "Starting WAHA on port 3000..."
/home/waha-linux-x64/waha --port 3000 &
WAHA_PID=$!

# Wait for WAHA to start
sleep 10
echo "WAHA started with PID $WAHA_PID"

# Start your Flask app on port 5000
echo "Starting Flask app on port 5000..."
exec python3 render_app.py