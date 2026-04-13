#!/bin/bash
# ============================================================
# OKi Kiosk Launcher
# Starts Chromium in fullscreen kiosk mode on the OKi UI
# ============================================================

# Wait for OKi web server to be ready
echo "[KIOSK] Waiting for OKi web server..."
until curl -s http://localhost:8000 > /dev/null; do
    sleep 1
done
echo "[KIOSK] OKi is up — launching kiosk browser."

# Disable screen blanking and power saving
xset s off
xset s noblank
xset -dpms

# Hide mouse cursor after 1 second of inactivity
unclutter -idle 1 -root &

# Launch Chromium in kiosk mode
chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --autoplay-policy=no-user-gesture-required \
    --check-for-update-interval=31536000 \
    --touch-events=enabled \
    --window-size=720,720 \
    --window-position=0,0 \
    http://localhost:8000