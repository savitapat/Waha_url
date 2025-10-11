#!/bin/bash

# 1️⃣ Download cloudflared
if ! [ -x "$(command -v cloudflared)" ]; then
    echo "Installing cloudflared..."
    wget -O cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x cloudflared
    sudo mv cloudflared /usr/local/bin/
fi

# 2️⃣ Start the Cloudflare Tunnel
echo "Starting cloudflared tunnel..."
cloudflared tunnel run my-waha &

# 3️⃣ Start WAHA bot
echo "🎯 Starting WhatsApp Forwarder..."
python3 render_app.py

