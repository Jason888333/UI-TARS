#!/usr/bin/env bash
# Start ClawBot Controller PWA
# Requires: python3 or npx serve
set -euo pipefail

PORT="${1:-8080}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🦞 ClawBot Controller starting on http://localhost:$PORT"
echo "   Open this URL on your phone (same network) to use as remote control."
echo ""

if command -v python3 &> /dev/null; then
  cd "$DIR" && python3 -m http.server "$PORT"
elif command -v npx &> /dev/null; then
  npx serve "$DIR" -l "$PORT"
else
  echo "Error: python3 or npx required to serve the app."
  exit 1
fi
