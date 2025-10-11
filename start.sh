#!/bin/bash
set -euo pipefail

# ---------- config ----------
TUNNEL_NAME="my-waha"
CREDS_PATH="/home/cloudflared/creds.json"
CLOUDFLARED_BIN="/home/cloudflared/cloudflared"
APP_CMD="python3 render_app.py"
# ----------------------------

echo "== start.sh: begin =="

# make dir for cloudflared and creds
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

# 3) Start cloudflared tunnel in background (use full path to binary)
echo "Starting cloudflared tunnel (using creds $CREDS_PATH) ..."
"$CLOUDFLARED_BIN" tunnel --no-autoupdate --credentials-file "$CREDS_PATH" run "$TUNNEL_NAME" &
CLOUDPID=$!

# Give cloudflared a few seconds to establish
sleep 5

# Optional: check whether cloudflared actually started
if ! ps -p $CLOUDPID > /dev/null 2>&1; then
  echo "ERROR: cloudflared process died immediately. Check logs below for errors."
  # print last 200 bytes of cloudflared log if it's making one (best-effort)
  sleep 1
fi

# 4) Start your WAHA app (foreground)
echo "Starting WAHA app..."
exec $APP_CMD
