#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export UV_CACHE_DIR="$PWD/.tools/uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
export npm_config_cache="$PWD/.tools/npm-cache"
command -v uv >/dev/null
command -v aws >/dev/null
node -e 'if(Number(process.versions.node.split(".")[0])<20)process.exit(1)'
uv python install 3.12
# Use a dedicated 3.12 environment even if a different .venv exists for offline checks.
uv venv --python 3.12 .venv312
uv pip sync --python .venv312/bin/python requirements.lock.txt
npm install --prefix .tools/agentcore --no-audit --no-fund @aws/agentcore@0.30.0
npm ci --prefix agentcore/cdk --no-audit --no-fund
printf '%s\n' 'Setup ready. Use .venv312/bin/python and add .tools/agentcore/node_modules/.bin to PATH.'
