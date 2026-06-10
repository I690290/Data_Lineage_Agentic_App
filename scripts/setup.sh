#!/bin/bash
# scripts/setup.sh — One-time local system setup for Data Lineage Agent
# Run: bash scripts/setup.sh

set -e
echo "=== Data Lineage Agent — Local Setup ==="

# 1. Python version check
PY_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
REQUIRED="3.12"
echo "Python: $PY_VERSION (required >= $REQUIRED)"

# 2. Node.js version check (required for React frontend)
echo ""
echo "=== Node.js Check ==="
if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js not found."
    echo "  Install Node 20+ from https://nodejs.org or via nvm:"
    echo "    nvm install 20 && nvm use 20"
    exit 1
fi
NODE_MAJOR=$(node --version | grep -oE '[0-9]+' | head -1)
echo "Node.js: $(node --version)  (required >= 20)"
if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "ERROR: Node.js 20+ required. Current: $(node --version)"
    echo "  Upgrade via nvm: nvm install 20 && nvm use 20"
    exit 1
fi
echo "npm: $(npm --version)"

# 3. uv check / install
echo ""
echo "=== uv Package Manager ==="
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "uv: $(uv --version)"

# 4. Python dependencies
echo ""
echo "=== Python Dependencies ==="
uv sync
echo "Python dependencies installed."

# 5. Frontend dependencies
echo ""
echo "=== Frontend Dependencies (npm) ==="
cd frontend && npm install && cd ..
echo "Frontend node_modules installed."

# 6. Output directories
echo ""
echo "=== Creating output directories ==="
mkdir -p output evaluation/golden evaluation/reports data/chromadb
echo "  output/  evaluation/golden/  evaluation/reports/  data/chromadb/  ✅"

# 7. Neo4j Desktop (pre-installed — skip installation)
echo ""
echo "=== Neo4j Desktop Check ==="
echo "Skipping Neo4j installation — using Neo4j Desktop already installed on this system."
echo "Ensure a database is running in Neo4j Desktop before starting the app."
if nc -z localhost 7687 2>/dev/null; then
    echo "Neo4j bolt port 7687 ✅  reachable at bolt://localhost:7687"
else
    echo "Neo4j bolt port 7687 ❌  not reachable — start a database in Neo4j Desktop first."
fi

# 8. Jaeger (pre-installed binary — skip installation)
echo ""
echo "=== Jaeger Check ==="
echo "Skipping Jaeger installation — using jaeger-all-in-one binary already installed on this system."
echo "Download from: https://github.com/jaegertracing/jaeger/releases/latest"
echo "  Extract and place jaeger-all-in-one in /usr/local/bin/ (or any directory on PATH)."
JAEGER_BIN=$(command -v jaeger-all-in-one 2>/dev/null || echo "")
if [ -n "$JAEGER_BIN" ]; then
    JAEGER_VERSION=$("$JAEGER_BIN" --version 2>&1 | head -1)
    echo "jaeger-all-in-one ✅  found at $JAEGER_BIN ($JAEGER_VERSION)"
else
    echo "jaeger-all-in-one ❌  not found on PATH — install it before running 'make start-jaeger'."
    echo "  macOS: download jaeger-<version>-darwin-arm64.tar.gz (Apple Silicon)"
    echo "         or     jaeger-<version>-darwin-amd64.tar.gz   (Intel)"
    echo "  Then:  sudo mv jaeger-all-in-one /usr/local/bin/ && chmod +x /usr/local/bin/jaeger-all-in-one"
fi

# 9. AWS CLI check
echo ""
echo "=== AWS Bedrock Setup ==="
if command -v aws &>/dev/null; then
    echo "AWS CLI: $(aws --version)"
    echo "Verify Bedrock access:"
    aws bedrock list-foundation-models \
        --query "modelSummaries[?contains(modelId, 'nova')].[modelId]" \
        --output table 2>/dev/null \
        || echo "  (Bedrock access check failed — ensure AWS credentials are configured in .env)"
else
    echo "AWS CLI not found. Install from: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
fi

# 10. Create .env from example if missing
echo ""
echo "=== Environment Configuration ==="
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
    echo ""
    echo "  ⚠️  REQUIRED: Edit .env and set:"
    echo "    AWS_ACCESS_KEY_ID      — your AWS access key"
    echo "    AWS_SECRET_ACCESS_KEY  — your AWS secret key"
    echo "    AWS_REGION             — e.g. us-east-1"
    echo "    NEO4J_PASSWORD         — your Neo4j password (default: lineage_password)"
    echo "    VITE_RAG_URL           — Streamlit URL (default: http://localhost:8501)"
    echo "    LINEAGE_VIEWER_URL     — React URL (default: http://localhost:3000)"
else
    echo ".env already exists (skipping)"
fi

echo ""
echo "=== Setup complete ✅ ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your AWS credentials and Neo4j password"
echo "  2. Start a database in Neo4j Desktop            (bolt://localhost:7687)"
echo "  3. make start-jaeger         # start Jaeger tracing (http://localhost:16686)"
echo "  4. make ingest               # embed mock_code/ into ChromaDB"
echo "  5. make pipeline             # run ReAct+Reflexion lineage extraction"
echo "  6. make start-backend        # start FastAPI backend  (http://localhost:8000)"
echo "  7. make streamlit            # start RAG chat         (http://localhost:8501)"
echo "  8. make frontend-dev         # start React frontend   (http://localhost:3000)"
echo "  9. make eval                 # run 3-level evaluation against golden datasets"
echo ""
echo "  Or start everything at once:  make dev"
echo "  Or use the script:            bash run_all.sh"
