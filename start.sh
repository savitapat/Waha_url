#!/bin/bash
set -euo pipefail

echo "== start.sh: begin =="

# Download WAHA directly
echo "Downloading WAHA..."
cd /tmp
wget -q "https://github.com/devlikeapro/waha/releases/download/v5.0.0/waha-linux-x64-5.0.0"
chmod +x waha-linux-x64-5.0.0

# Start WAHA in background
echo "Starting WAHA on port 3000..."
/tmp/waha-linux-x64-5.0.0 --port 3000 &

# Wait longer for WAHA
echo "Waiting for WAHA to initialize (45 seconds)..."
sleep 45

# Start Flask app
echo "Starting Flask app..."
exec python3 render_app.py
