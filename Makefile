.PHONY: setup install run all dev stop \
        start-neo4j start-jaeger start-backend start-streamlit frontend-install frontend-dev frontend-build frontend-check \
        ingest extract pipeline streamlit \
        eval test test-unit check-imports clean clean-all status help

# ================================================================
# Data Lineage Agent — Developer Makefile
#
# QUICK START (first time):
#   make setup          ← install all deps, create .env, create dirs
#   # edit .env with AWS credentials + Neo4j password
#   make all            ← start every service (blocks; Ctrl+C stops all)
#
# QUICK START (subsequent runs):
#   make all            ← start every service (blocks; Ctrl+C stops all)
#
# INDIVIDUAL SERVICES:
#   make start-neo4j    make start-jaeger    make start-backend
#   make start-streamlit                     make frontend-dev
#
# DATA PIPELINE:
#   make ingest         ← embed source code into ChromaDB
#   make pipeline       ← run ReAct+Reflexion lineage extraction
#   make eval           ← run 3-level evaluation against golden datasets
#
# OTHER:
#   make status         ← check which services are running
#   make stop           ← stop all services
#   make clean          ← remove generated artefacts
#   make test           ← run pytest
#   make check-imports  ← smoke-test all Python imports
#   make help           ← show this summary
#
# Ports:
#   Backend API   : http://localhost:8000   (api.main:app)
#   API Docs      : http://localhost:8000/docs
#   React Frontend: http://localhost:3000   (Vite → proxies /api → :8000)
#   RAG Assistant : http://localhost:8501   (Streamlit)
#   Neo4j Browser : http://localhost:7474   bolt://localhost:7687
#   Jaeger UI     : http://localhost:16686
# ================================================================

# ── First-time setup ──────────────────────────────────────────
setup: _check-node
	@echo "=== Setting up Data Lineage Agent ==="
	python3 --version
	uv sync
	@mkdir -p data/chromadb output evaluation/golden evaluation/reports
	@[ -f .env ] || (cp .env.example .env && echo "Created .env from .env.example — fill in AWS credentials and Neo4j password.")
	@echo "=== Python dependencies installed ==="
	$(MAKE) frontend-install
	@echo ""
	@echo "Next: start a DB in Neo4j Desktop, then: make start-jaeger && make run"

_check-node:
	@node --version >/dev/null 2>&1 || (echo "ERROR: Node.js not found. Install Node 20+ from https://nodejs.org" && exit 1)
	@npm --version >/dev/null 2>&1 || (echo "ERROR: npm not found." && exit 1)

# Install / sync Python dependencies only
install:
	uv sync

# ── Infrastructure ────────────────────────────────────────────
start-neo4j:
	@nc -z localhost 7687 2>/dev/null \
		&& echo "[neo4j]  Neo4j Desktop running on bolt://localhost:7687" \
		|| (echo "[neo4j]  WARNING: bolt://localhost:7687 not reachable." && \
		    echo "         Start a database in Neo4j Desktop and retry.")

start-jaeger:
	@pgrep -x jaeger-all-in-one >/dev/null 2>&1 \
		&& echo "[jaeger] Already running on http://localhost:16686" \
		|| (command -v jaeger-all-in-one >/dev/null 2>&1 \
			&& (jaeger-all-in-one >/tmp/jaeger.log 2>&1 & sleep 2 && echo "[jaeger] Started — http://localhost:16686  |  OTLP gRPC :4317") \
			|| echo "[jaeger] WARNING: jaeger-all-in-one not found. Install: brew install jaegertracing/tap/jaeger")

# ── Backend ───────────────────────────────────────────────────
start-backend:
	@pgrep -f "uvicorn api.main" >/dev/null 2>&1 \
		&& echo "[api]    Already running on http://localhost:8000" \
		|| (uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload >/tmp/fastapi.log 2>&1 & \
		    sleep 3 && echo "[api]    Started — http://localhost:8000  |  Docs: http://localhost:8000/docs")

# ── Streamlit RAG chat ─────────────────────────────────────────
start-streamlit:
	@pgrep -f "streamlit run streamlit_app" >/dev/null 2>&1 \
		&& echo "[rag]    Streamlit already running on http://localhost:8501" \
		|| (uv run streamlit run streamlit_app/rag_chat.py --server.port 8501 --server.headless true \
		    >/tmp/streamlit.log 2>&1 & sleep 3 && echo "[rag]    Started — http://localhost:8501")

streamlit: start-streamlit

# ── Frontend ──────────────────────────────────────────────────
frontend-install:
	cd frontend && npm install
	@echo "[ui]     Node modules installed in frontend/"

frontend-dev:
	@pgrep -f "vite" >/dev/null 2>&1 \
		&& echo "[ui]     Vite already running on http://localhost:3000" \
		|| (cd frontend && npm run dev >/tmp/vite.log 2>&1 & sleep 3 && echo "[ui]     Started — http://localhost:3000")

frontend-build:
	cd frontend && npm run build
	@echo "[ui]     Production build → static/frontend/"

frontend-check:
	cd frontend && npm run type-check

# ── Composite targets ─────────────────────────────────────────
# Minimal: infra + backend only (no UI, background)
run: start-neo4j start-jaeger start-backend
	@echo ""
	@echo "=== Core services running ==="
	@echo "  Backend API   : http://localhost:8000"
	@echo "  API Docs      : http://localhost:8000/docs"
	@echo "  Neo4j Browser : http://localhost:7474"
	@echo "  Jaeger UI     : http://localhost:16686"
	@echo ""
	@echo "  Start UI:  make frontend-dev"
	@echo "  Start RAG: make streamlit"

# Full stack: all services (background, non-blocking)
dev: start-neo4j start-jaeger start-backend start-streamlit frontend-dev
	@echo ""
	@echo "=== Full stack running ==="
	@echo "  Backend API   : http://localhost:8000"
	@echo "  API Docs      : http://localhost:8000/docs"
	@echo "  React Frontend: http://localhost:3000"
	@echo "  RAG Assistant : http://localhost:8501"
	@echo "  Neo4j Browser : http://localhost:7474"
	@echo "  Jaeger UI     : http://localhost:16686"

# Full stack: BLOCKING — health-checks backend, Ctrl+C stops everything cleanly
all:
	@bash -euo pipefail -c '\
	  PIDS=(); \
	  cleanup() { \
	    echo ""; echo "=== Stopping all services ==="; \
	    for p in "$${PIDS[@]:-}"; do kill "$$p" 2>/dev/null && echo "  stopped PID $$p" || true; done; \
	    neo4j stop 2>/dev/null && echo "  Neo4j stopped (if CLI-managed)" || true; \
	    echo "Done."; \
	  }; \
	  trap cleanup EXIT INT TERM; \
	  echo "[neo4j]  Checking Neo4j Desktop connection..."; \
	  nc -z localhost 7687 2>/dev/null \
	    && echo "[neo4j]  Running on bolt://localhost:7687" \
	    || (echo "[neo4j]  WARNING: bolt://localhost:7687 not reachable — start a database in Neo4j Desktop."); \
	  if command -v jaeger-all-in-one >/dev/null 2>&1; then \
	    pgrep -x jaeger-all-in-one >/dev/null 2>&1 && echo "[jaeger] Already running" || \
	    (jaeger-all-in-one >/tmp/jaeger.log 2>&1 & PIDS+=($$!) && sleep 1 && echo "[jaeger] Running on http://localhost:16686"); \
	  else echo "[jaeger] WARNING: not installed (brew install jaegertracing/tap/jaeger)"; fi; \
	  echo "[api]    Starting FastAPI..."; \
	  uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload >/tmp/fastapi.log 2>&1 & PIDS+=($$!); \
	  echo "[api]    Waiting for http://localhost:8000/api/health ..."; \
	  for i in $$(seq 1 30); do \
	    curl -sf http://localhost:8000/api/health 2>/dev/null | grep -q "status" && break; \
	    [ "$$i" -eq 30 ] && echo "[api]    ERROR: timed out — check /tmp/fastapi.log" && exit 1; \
	    sleep 2; \
	  done; echo "[api]    Running on http://localhost:8000"; \
	  uv run streamlit run streamlit_app/rag_chat.py --server.port 8501 --server.headless true >/tmp/streamlit.log 2>&1 & PIDS+=($$!); \
	  sleep 2; echo "[rag]    Running on http://localhost:8501"; \
	  if [ -d frontend/node_modules ]; then \
	    (cd frontend && npm run dev >/tmp/vite.log 2>&1) & PIDS+=($$!); \
	    sleep 2; echo "[ui]     Running on http://localhost:3000"; \
	  else echo "[ui]     WARNING: run make frontend-install first"; fi; \
	  echo ""; \
	  echo "============================================================"; \
	  echo "  Backend API   : http://localhost:8000"; \
	  echo "  API Docs      : http://localhost:8000/docs"; \
	  echo "  React Frontend: http://localhost:3000"; \
	  echo "  RAG Assistant : http://localhost:8501"; \
	  echo "  Neo4j Browser : http://localhost:7474"; \
	  echo "  Jaeger UI     : http://localhost:16686"; \
	  echo "  Press Ctrl+C to stop all services."; \
	  echo "============================================================"; \
	  wait; \
	'

# ── Stop all ──────────────────────────────────────────────────
stop:
	@-pkill -f "uvicorn api.main"          && echo "Backend stopped"            || true
	@-pkill -f "streamlit run streamlit_app" && echo "Streamlit stopped"         || true
	@-pkill -f "vite"                      && echo "Frontend dev server stopped" || true
	@-pkill -x jaeger-all-in-one           && echo "Jaeger stopped"              || true
	@echo "Neo4j Desktop: stop the database via the Neo4j Desktop application."

# ── Data pipeline ─────────────────────────────────────────────
# Step 1: Embed source code into ChromaDB (incremental, skips unchanged files)
ingest:
	uv run python main.py ingest --repo ./mock_code

# Step 2a: Legacy LangGraph extraction pipeline (src/agent.py)
extract:
	uv run python main.py agent --repo ./mock_code

# Step 2b: ReAct + Reflexion pipeline (agents/pipeline.py)
pipeline:
	uv run python main.py pipeline --repo ./mock_code

# ── Evaluation ────────────────────────────────────────────────
eval:
	@mkdir -p evaluation/golden output
	@echo "=== Step 1/2: Generating golden datasets from mock_code/ ==="
	uv run python -c "\
from evaluation.golden_dataset_generator import GoldenDatasetGenerator; \
gen = GoldenDatasetGenerator(); \
golden = gen.generate_for_directory('./mock_code'); \
gen.save(golden, 'evaluation/golden'); \
print(f'[eval]   Generated {len(golden)} golden datasets -> evaluation/golden/')"
	@echo "=== Step 2/2: Running 3-level evaluation ==="
	uv run python -c "\
from evaluation.runner import EvaluationRunner; \
runner = EvaluationRunner(); \
report = runner.run_full_evaluation('output/', 'evaluation/golden/'); \
print(f\"[eval]   Report saved to evaluation/reports/\")"

# ── Tests ─────────────────────────────────────────────────────
test:
	uv run pytest tests/ -v --tb=short

test-unit:
	uv run pytest tests/unit/ -v --tb=short

# ── Smoke-test all module imports ──────────────────────────────
check-imports:
	uv run python scripts/check_imports.py

# ── Clean ─────────────────────────────────────────────────────
clean:
	rm -rf output/ evaluation/reports/ chroma_db/ data/chromadb/ \
	       hash_cache.db lineage_output.json static/frontend/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

clean-all: clean
	rm -rf evaluation/golden/ frontend/node_modules/ .venv/

# ── Status ─────────────────────────────────────────────────────
status:
	@echo "Service            Status"
	@echo "──────────────────────────────────────────"
	@nc -z localhost 7687 2>/dev/null \
		&& echo "Neo4j            ✅  bolt://localhost:7687" \
		|| echo "Neo4j            ❌  not reachable (start DB in Neo4j Desktop)"
	@pgrep -x jaeger-all-in-one >/dev/null 2>&1 \
		&& echo "Jaeger           ✅  http://localhost:16686" \
		|| echo "Jaeger           ❌  not running"
	@pgrep -f "uvicorn api.main" >/dev/null 2>&1 \
		&& echo "FastAPI backend  ✅  http://localhost:8000" \
		|| echo "FastAPI backend  ❌  not running"
	@pgrep -f "streamlit run streamlit_app" >/dev/null 2>&1 \
		&& echo "Streamlit RAG    ✅  http://localhost:8501" \
		|| echo "Streamlit RAG    ❌  not running"
	@pgrep -f "vite" >/dev/null 2>&1 \
		&& echo "React frontend   ✅  http://localhost:3000" \
		|| echo "React frontend   ❌  not running"

# ── Help ───────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Data Lineage Agent — Makefile targets"
	@echo "══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "FIRST TIME"
	@echo "  make setup            Install all deps, create .env, make dirs"
	@echo "  # edit .env: set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,"
	@echo "  #            AWS_REGION, NEO4J_PASSWORD"
	@echo ""
	@echo "START SERVICES"
	@echo "  make all              Start every service (BLOCKING — Ctrl+C stops all)"
	@echo "  make run              Start infra + backend only (background)"
	@echo "  make dev              Start all services (background)"
	@echo "  make start-neo4j      Check Neo4j Desktop connectivity (bolt://localhost:7687)"
	@echo "  make start-jaeger     Start Jaeger tracing only"
	@echo "  make start-backend    Start FastAPI backend only"
	@echo "  make start-streamlit  Start Streamlit RAG chat only"
	@echo "  make frontend-dev     Start React dev server only"
	@echo "  make stop             Stop all services"
	@echo ""
	@echo "DATA PIPELINE"
	@echo "  make ingest           Embed mock_code/ into ChromaDB (incremental)"
	@echo "  make pipeline         Run ReAct+Reflexion lineage extraction"
	@echo "  make extract          Run legacy LangGraph extraction"
	@echo "  make eval             Generate golden datasets + run 3-level evaluation"
	@echo ""
	@echo "FRONTEND"
	@echo "  make frontend-install Install npm packages (required once)"
	@echo "  make frontend-build   Build production bundle → static/frontend/"
	@echo "  make frontend-check   TypeScript type-check"
	@echo ""
	@echo "TESTING & VALIDATION"
	@echo "  make test             Run all pytest tests"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make check-imports    Smoke-test all 25 Python module imports"
	@echo ""
	@echo "MAINTENANCE"
	@echo "  make status           Show which services are running"
	@echo "  make clean            Remove generated artefacts (output/, chroma, etc.)"
	@echo "  make clean-all        clean + node_modules/ + .venv/"
	@echo ""
