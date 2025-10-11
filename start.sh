#!/bin/bash
set -euo pipefail

# ---------- config ----------
TUNNEL_NAME="my-waha"
CREDS_PATH="/home/cloudflared/creds.json"
CLOUDFLARED_BIN="/home/cloudflared/cloudflared"
CONFIG_PATH="/home/cloudflared/config.yml"
APP_CMD="python3 render_app.py"
HOSTNAME="waha.dealking.website"   # <-- your hostname
# ----------------------------

echo "== start.sh: begin =="

# create dir for cloudflared and set permissions
mkdir -p /home/cloudflared
chmod 700 /home/cloudflared || true

# 1) Decode tunnel credentials from env var (TUNNEL_CREDS_B64) into CREDS_PATH
if [ -z "${TUNNEL_CREDS_B64:-}" ]; then
  echo "ERROR: TUNNEL_CREDS_B64 env var is not set. Exiting."
  exit 1
fi

echo "Writing credentials to $CREDS_PATH"
echo "$TUNNEL_CREDS_B64" | base64 -d > "$CREDS_PATH"
chmod 600 "$CREDS_PATH" || true

# 2) Ensure cloudflared binary exists (download to local folder if missing)
if [ ! -x "$CLOUDFLARED_BIN" ]; then
  echo "Downloading cloudflared to $CLOUDFLARED_BIN ..."
  wget -q -O "$CLOUDFLARED_BIN" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
  chmod +x "$CLOUDFLARED_BIN"
fi

# 3) Write config.yml with ingress rules (this is why you were getting 503)
cat > "$CONFIG_PATH" <<EOF
tunnel: afdff7a5-08d4-44a2-9fc7-6355a8380355
credentials-file: $CREDS_PATH

ingress:
  - hostname: $HOSTNAME
    service: http://localhost:5000
  - service: http_status:404
EOF

chmod 600 "$CONFIG_PATH" || true
echo "Wrote cloudflared config to $CONFIG_PATH"

# 4) Start cloudflared tunnel in background using the config
echo "Starting cloudflared tunnel (config: $CONFIG_PATH) ..."
"$CLOUDFLARED_BIN" tunnel --no-autoupdate --config "$CONFIG_PATH" run "$TUNNEL_NAME" &
CLOUDPID=$!

# wait for tunnel to establish
sleep 5

# optional quick check: print cloudflared status lines (best-effort)
echo "cloudflared started with PID $CLOUDPID"

# 5) Start WAHA app in foreground
echo "Starting WAHA app..."
exec $APP_CMD
