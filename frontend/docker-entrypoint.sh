#!/bin/sh
set -eu

cat > /app/public/config.js <<EOF
window.__AP_TRACKER_CONFIG__ = { apiUrl: "${AP_TRACKER_PUBLIC_API_URL:-}" };
EOF

exec npm start
