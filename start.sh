#!/bin/bash
set -euo pipefail

echo "== start.sh: begin =="

# Start WAHA in background
echo "Starting WAHA on port 3000..."
/usr/local/bin/waha --port 3000 &
WAHA_PID=$!

# Wait for WAHA to fully start
echo "Waiting for WAHA to initialize..."
sleep 30

# Check if WAHA is running
if curl -f http://localhost:3000/api/sessions > /dev/null 2>&1; then
    echo "✅ WAHA is running successfully!"
else
    echo "❌ WAHA failed to start"
fi

# Start Flask app
echo "Starting Flask app on port 5000..."
exec python3 render_app.py
exec python3 render_app.py