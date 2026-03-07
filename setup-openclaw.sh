#!/usr/bin/env bash
# OpenClaw Setup Script
# Run this script to complete the OpenClaw onboarding.
#
# Prerequisites:
#   - Node.js >= 22 (already installed)
#   - npm (already installed)
#   - OpenClaw CLI (already installed globally: openclaw v2026.3.2)
#   - An Anthropic API key from https://console.anthropic.com
#
# Usage:
#   chmod +x setup-openclaw.sh
#   ./setup-openclaw.sh

set -euo pipefail

echo "🦞 OpenClaw Setup Script"
echo "========================"
echo ""

# Check if openclaw is installed
if ! command -v openclaw &> /dev/null; then
    echo "OpenClaw not found. Installing..."
    npm install -g openclaw@latest
fi

echo "OpenClaw version: $(openclaw --version)"
echo ""

# Check for API key
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "Please enter your Anthropic API key (starts with sk-ant-...):"
    read -r -s API_KEY
    echo ""
else
    API_KEY="$ANTHROPIC_API_KEY"
    echo "Using ANTHROPIC_API_KEY from environment."
fi

if [ -z "$API_KEY" ]; then
    echo "Error: No API key provided. Exiting."
    exit 1
fi

echo "Starting OpenClaw onboarding..."
echo ""

# Run non-interactive onboarding
openclaw onboard \
    --non-interactive \
    --accept-risk \
    --mode local \
    --anthropic-api-key "$API_KEY" \
    --install-daemon \
    --skip-channels \
    --skip-skills \
    --skip-ui \
    --json

echo ""
echo "✅ OpenClaw setup complete!"
echo ""
echo "Next steps:"
echo "  1. Start the gateway:    openclaw gateway"
echo "  2. Open the dashboard:   openclaw dashboard"
echo "  3. Run the TUI:          openclaw tui"
echo "  4. Check health:         openclaw doctor"
echo "  5. Add channels:         openclaw channels --help"
echo ""
echo "Documentation: https://docs.openclaw.ai"
