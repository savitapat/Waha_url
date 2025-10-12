#!/bin/bash
set -euo pipefail

echo "== start.sh: begin =="

# Download and run WAHA
echo "Downloading WAHA..."
wget -q -O waha "https://github.com/devlikeapro/waha/releases/download/v5.0.0/waha-linux-x64-5.0.0"
chmod +x waha

# Start WAHA in background
echo "Starting WAHA..."
./waha --port 3000 &

# Wait for WAHA to initialize
echo "Waiting for WAHA to start..."
sleep 15

# Start Flask app
echo "Starting Flask app..."
exec python3 render_app.py