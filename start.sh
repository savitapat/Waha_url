#!/bin/bash
set -euo pipefail

echo "== start.sh: begin =="

# Download and install WAHA
echo "Downloading WAHA..."
cd /tmp
wget -q "https://github.com/devlikeapro/waha/releases/download/v5.0.0/waha-linux-x64-5.0.0.tar.gz"
tar -xzf waha-linux-x64-5.0.0.tar.gz
chmod +x waha-linux-x64/waha

# Start WAHA in background on port 3000
echo "Starting WAHA on port 3000..."
/tmp/waha-linux-x64/waha --port 3000 &
WAHA_PID=$!

echo "WAHA started with PID: $WAHA_PID"

# Wait for WAHA to initialize
echo "Waiting for WAHA to start..."
sleep 30

# Check if WAHA is running
if curl -f http://localhost:3000/api/sessions > /dev/null 2>&1; then
    echo "✅ WAHA is running successfully!"
else
    echo "❌ WAHA failed to start - but continuing..."
fi

# Start Flask app on port 5000
echo "Starting Flask app on port 5000..."
cd /opt/render/project/src
exec python3 render_app.py