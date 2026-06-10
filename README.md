# Data Lineage Agentic App

Automated data lineage extraction and visualisation for **COBOL** (with COPYbooks) and **Java Spring Batch** codebases, built with **LangGraph** and **Amazon Bedrock Titan models** (no Claude — only Titan).

---

## Architecture

```
Local Repo (COBOL / Java / JCL)
        │
        ▼
[Ingestion Layer]
  • File walk & classification
  • COBOL: paragraph/section regex chunker
  • Java: tree-sitter AST chunker
  • Config: PyYAML parser
  • Embeds → ChromaDB (Titan Embed V2)
  • SQLite hash cache (incremental re-runs)
        │
        ▼
[LangGraph Pipeline — Titan Text Premier via Bedrock]
  repo_scan_node
    → config_resolve_node
    → code_analysis_node  (ReAct, one invocation per file)
    → dependency_resolver_node
    → lineage_graph_builder_node
    → validation_node
    → output_node
        │
        ▼
[Neo4j]  ←→  [FastAPI]  ←→  [Cytoscape.js UI]
```

## Models used (Bedrock — Titan only)

| Purpose | Model ID |
|---|---|
| Embeddings | `amazon.titan-embed-text-v2:0` |
| Analysis / Reasoning / Generation | `amazon.titan-text-premier-v1:0` |

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Managed by `uv` |
| `uv` | `pip install uv` |
| AWS account | Bedrock access to Titan models in your region |
| Neo4j Desktop | [Download](https://neo4j.com/download/) — create a local DB, enable APOC |

---

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env:
#   AWS_PROFILE, AWS_REGION, NEO4J_PASSWORD (at minimum)
```

### 3. Start Neo4j Desktop

Start your local Neo4j database. Note the bolt URI (default `bolt://localhost:7687`) and your password.

---

## Running

### Option A: Full pipeline (recommended)

```bash
uv run python main.py pipeline --repo ./mock_code
```

This runs ingestion → agent → writes to Neo4j → exports JSON.

### Option B: Step by step

```bash
# Step 1: Ingest and embed source files into ChromaDB
uv run python main.py ingest --repo ./mock_code

# Step 2: Run LangGraph lineage extraction pipeline
uv run python main.py agent --repo ./mock_code

# Step 3: Start the visualisation server
uv run python main.py serve --port 8000
```

Then open **http://localhost:8000** in your browser.

---

## Project structure

```
data-lineage-agentic-app/
├── mock_code/
│   ├── cobol/
│   │   ├── CUSTPROC.cbl         # Customer processing COBOL program
│   │   ├── ACCTPROC.cbl         # Account processing COBOL program
│   │   └── copybooks/
│   │       ├── CUSTOMER.cpy     # Customer record layout
│   │       └── ACCOUNT.cpy      # Account record layout
│   ├── jcl/
│   │   └── CUSTJOB.jcl          # JCL job with DD statements
│   └── java/
│       └── src/main/
│           ├── java/com/example/batch/
│           │   ├── BatchConfig.java
│           │   ├── CustomerItemReader.java
│           │   ├── CustomerProcessor.java
│           │   └── CustomerItemWriter.java
│           └── resources/application.yml
├── src/
│   ├── models.py          # Shared dataclasses
│   ├── config.py          # Settings from .env
│   ├── ingest.py          # Ingestion pipeline
│   ├── chunkers/
│   │   ├── cobol_chunker.py
│   │   └── java_chunker.py
│   ├── tools.py           # LangGraph tools
│   ├── agent.py           # LangGraph graph
│   ├── neo4j_writer.py    # Neo4j I/O
│   └── api.py             # FastAPI server
├── static/
│   └── index.html         # Cytoscape.js visualisation
├── .env.example
├── pyproject.toml
└── main.py                # CLI entry point
```

---

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Cytoscape.js visualisation UI |
| `GET /lineage` | Full lineage graph (Cytoscape.js JSON) |
| `GET /lineage/entity/{name}` | Subgraph for a named entity |
| `GET /lineage/entities` | List all entity names |
| `GET /lineage/json` | Raw JSON from last agent run |
| `GET /health` | Health check |
| `GET /docs` | FastAPI interactive docs |

---

## Incremental re-runs

The ingestion step uses a SQLite hash cache (`hash_cache.db`). Re-running `ingest` only re-embeds files that have changed since the last run. For a large repo, this reduces subsequent runs from hours to minutes.

---

## Lineage graph schema (Neo4j)

**Node labels**
- `DataEntity` — tables, files, datasets, queues
- `TransformationUnit` — COBOL programs, Java Spring Batch jobs, JCL steps

**Relationship types**
- `READS_FROM` — transformation reads a data entity
- `WRITES_TO` — transformation writes a data entity
- `TRANSFORMS_VIA` — one transformation calls another

**Useful Cypher queries**

```cypher
-- Full lineage for CUSTOMER_TABLE
MATCH path = (n:DataEntity {name: 'CUSTSCHEMA.CUSTOMER_TABLE'})-[*1..5]-(m) RETURN path

-- What does CUSTPROC feed?
MATCH (p:TransformationUnit {name: 'CUSTPROC'})-[:WRITES_TO]->(t) RETURN t

-- Orphan detection
MATCH (n:DataEntity) WHERE NOT (n)-[]-() RETURN n
```




First time on a new machine

 bash scripts/setup.sh    # install uv, Node, Neo4j, Jaeger; creates .env
 # ✏️  edit .env — set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, NEO4J_PASSWORD
 make setup               # install Python + npm deps, create output dirs

Every subsequent run

 make all                 # starts all 5 services, blocks, Ctrl+C stops everything cleanly

Step-by-step workflow

 # 1 — Start services individually
 make start-neo4j         # Neo4j graph DB     → bolt://localhost:7687
 make start-jaeger        # Jaeger tracing     → http://localhost:16686
 make start-backend       # FastAPI backend    → http://localhost:8000/docs
 make start-streamlit     # RAG assistant      → http://localhost:8501
 make frontend-dev        # React lineage UI   → http://localhost:3000
 
 # 2 — Run the data pipeline
 make ingest              # embed source code into ChromaDB
 make pipeline            # extract lineage (ReAct + Reflexion)
 
 # 3 — Validate
 make eval                # run 3-level evaluation against golden datasets
 make check-imports       # smoke-test all Python modules (25/25)
 make test                # run pytest
 
 # 4 — Stop everything
 make stop
 
 # 5 — See what's running
 make status

Quick reference

 make help    # prints all targets with descriptions

What changed

 - run_all.sh deleted — its logic (health-check loop + trap cleanup) is now in make all
 - make all = blocking start-all with Ctrl+C cleanup (replaces run_all.sh)
 - make dev = same but fires services in the background (no blocking)
 - make run = backend + infra only, no UI
