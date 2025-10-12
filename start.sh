#!/bin/bash
set -euo pipefail

echo "== start.sh: begin =="

# Start WAHA app directly (no cloudflared)
echo "Starting WAHA app..."
exec python3 render_app.py