#!/bin/bash

# ===================================================
# START: Install cloudflared if not present
# ===================================================
if ! [ -x "$(command -v cloudflared)" ]; then
    echo "Installing cloudflared..."
    wget -O cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x cloudflared
    sudo mv cloudflared /usr/local/bin/
fi

# ===================================================
# START: Export Cloudflare Tunnel credentials
# ===================================================
export TUNNEL_NAME="my-waha"
export TUNNEL_CREDENTIALS="/etc/cloudflared/afdff7a5-08d4-44a2-9fc7-6355a8380355.json"

# If Render container cannot use /etc/cloudflared, you can place your JSON in repo root and change path:
# export TUNNEL_CREDENTIALS="./afdff7a5-08d4-44a2-9fc7-6355a8380355.json"

# ===================================================
# START: Run Cloudflare Tunnel in background
# ===================================================
echo "Starting Cloudflare Tunnel..."
cloudflared tunnel --no-autoupdate --credentials-file $TUNNEL_CREDENTIALS run $TUNNEL_NAME &

# Wait a few seconds to ensure tunnel is up
sleep 5

# ===================================================
# START: Run WAHA Python app
# ===================================================
echo "🎯 Starting WhatsApp Forwarder..."
python3 render_app.py
