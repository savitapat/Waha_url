#!/bin/bash
set -euo pipefail

mkdir -p /home/cloudflared

if [ -z "${TUNNEL_CREDS_B64:-}" ]; then
  echo "ERROR: TUNNEL_CREDS_B64 environment variable not set"
  exit 1
fi

# decode credentials into file
echo "$TUNNEL_CREDS_B64" | base64 -d > /home/cloudflared/creds.json

# cloudflared config (Tunnel UUID filled)
cat > /home/cloudflared/config.yml <<'EOF'
tunnel: afdff7a5-08d4-44a2-9fc7-6355a8380355
credentials-file: /home/cloudflared/creds.json

ingress:
  - hostname: waha.dealking.website     # <-- REPLACE this with your real hostname
    service: http://localhost:5000
  - service: http_status:404
EOF

# start cloudflared (background)
# note: cloudflared binary placed at /usr/local/bin/cloudflared by Dockerfile
/usr/local/bin/cloudflared tunnel --config /home/cloudflared/config.yml run my-waha &

# small wait to let tunnel come up
sleep 3

# start your WAHA app (it should bind to 0.0.0.0:5000)
python render_app.py
