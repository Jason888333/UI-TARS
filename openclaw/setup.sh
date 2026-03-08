#!/usr/bin/env bash
# OpenClaw Setup Script - Configures OpenClaw with OpenAI API
set -euo pipefail

OPENCLAW_DIR="$HOME/.openclaw"
CONFIG_FILE="$OPENCLAW_DIR/openclaw.json"
ENV_FILE="$OPENCLAW_DIR/.env"

echo "=== OpenClaw + OpenAI Setup ==="

# Check Node.js version
NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
if [ -z "$NODE_VERSION" ] || [ "$NODE_VERSION" -lt 22 ]; then
    echo "Error: Node.js >= 22 is required. Current: $(node --version 2>/dev/null || echo 'not installed')"
    exit 1
fi
echo "Node.js version OK: $(node --version)"

# Install OpenClaw if not present
if ! command -v openclaw &>/dev/null; then
    echo "Installing OpenClaw..."
    npm install -g openclaw@latest
else
    echo "OpenClaw already installed: $(openclaw --version)"
fi

# Prompt for API key if not set
if [ -z "${OPENAI_API_KEY:-}" ]; then
    read -rp "Enter your OpenAI API key (sk-...): " OPENAI_API_KEY
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OpenAI API key is required."
    exit 1
fi

# Create config directory
mkdir -p "$OPENCLAW_DIR"

# Write .env file
cat > "$ENV_FILE" << ENVEOF
OPENAI_API_KEY=$OPENAI_API_KEY
ENVEOF
chmod 600 "$ENV_FILE"
echo "API key saved to $ENV_FILE"

# Write config file
cat > "$CONFIG_FILE" << 'CONFEOF'
{
  "env": {
    "OPENAI_API_KEY": "${OPENAI_API_KEY}"
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "openai/gpt-4o-mini",
        "fallbacks": []
      },
      "models": {
        "openai/gpt-4o-mini": {
          "params": {
            "transport": "auto",
            "openaiWsWarmup": true,
            "serviceTier": "default"
          }
        }
      }
    }
  }
}
CONFEOF
echo "Config written to $CONFIG_FILE"

# Validate config
openclaw config validate
echo ""
echo "=== Setup complete! ==="
echo "Run 'openclaw' to start your AI agent."
echo "Run 'openclaw --help' for all available commands."
