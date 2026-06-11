# Data Lineage Agentic App

Automated data lineage extraction and visualisation for legacy **COBOL** (with COPYbooks), **JCL** (including DFSORT/JOINKEYS), **Oracle SQL**, and **Java Spring Batch** codebases. The system uses a **LangGraph ReAct + Reflexion** agentic pipeline backed by **Amazon Bedrock** (Nova Pro for reasoning, Titan Embed V2 for vector search), stores lineage in **Neo4j**, and exposes it through a **FastAPI** backend, a **React + Cytoscape.js** graph UI, and a **Streamlit** RAG chat interface.

---

## What This System Does

Given a directory of legacy source files, the system:

1. **Parses** every COBOL program, JCL job, SQL script, and Java class into structured AST chunks — extracting I/O operations, data movements, DB2 cursor declarations, EXEC SQL blocks, DFSORT control cards, and JDBC calls.
2. **Embeds** the chunks into ChromaDB using Amazon Titan Embed V2, building a vector index for semantic retrieval.
3. **Extracts lineage** using a LangGraph ReAct agent per file: the agent reasons over the parsed AST and vector-retrieved context to produce OpenLineage-format assertions (`source → transformation → target`).
4. **Verifies** every assertion programmatically (no LLM): checks AST existence, transformation location, and data-type compatibility. Filters COBOL Working-Storage internal variables (WS-/HV-) from appearing as lineage entities.
5. **Retries** failed assertions using **Reflexion** episodic memory — accumulating failure context and oracle-derived hints (from the known expected lineage) before each retry.
6. **Links** cross-language flows: JCL DD-name → physical dataset → COBOL program → SQL table → Oracle view.
7. **Emits** OpenLineage-format JSON events and **persists** the lineage graph to Neo4j.
8. **Evaluates** lineage correctness against a five-level framework including a handcrafted oracle, end-to-end path completeness, and an optional LLM judge for semantic equivalence.
9. **Exposes** the graph via FastAPI REST endpoints, a React/Cytoscape.js visualisation, and a Strands Agents RAG chat.

### Reference pipeline (MI4014 Credit Risk)

The bundled mock code implements the real MI4014 Credit Risk Behaviour Scoring daily extract:

```
DB2: CRISK.CUST_ACCOUNT_MASTER
        │  (cursor CSR_CUST_ACCT)
        ▼
COBOL: CRDB2EXT  (STEP010)
        │  BHSCOEXT DD
        ▼
Flat file: CUST.BHSCORE.EXTRACT  ─────────────────────────────┐
                                                               │
DB2: CRISK.DAILY_TRANSACTIONS                                  │
        │  (cursor CSR_DAILY_TXN per account)                  │
        ▼                                                      │
COBOL: CRTXNEXT  (STEP020)                                     │
        │  BHSCOTXN DD                                         │
        ▼                                                      │
Flat file: TRANS.BHSCORE.EXTRACT                               │
        │                                                      │
        └───────────── JCL DFSORT JOINKEYS (STEP030) ─────────┘
                              │  SORTOUT DD
                              ▼
                    MERGED.BHSCORE.EXTRACT
                              │  BHSCOMRG DD
                              ▼
                    COBOL: CRXMLGEN  (STEP040)
                              │  BHSCOXML DD + FTP (STEP050)
                              ▼
                    XML: MI4014_Transaction_Extract_*.xml
                              │  Oracle External Table (ORACLE_LOADER)
                              ▼
              Oracle: BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_DIARIAS
                              │  INSERT /*+ APPEND PARALLEL */
                              ▼
              Oracle: BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_STG
                              │  CREATE OR REPLACE VIEW
                              ▼
              Oracle: V_MI4014_TRANSACCIONES_VALIDAS
                              │  GROUP BY aggregation
                              ▼
              Oracle: V_MI4014_ACCOUNT_SUMMARY
```

**14 lineage nodes · 15 directed edges · column-level traceability across 9 hops**

---

## Architecture

```
mock_code/  (COBOL / JCL / SQL / Java / XML)
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  Ingestion Layer  (src/ingest.py)                   │
│  • File walk + language detection                   │
│  • Language-specific parsers → ChunkMetadata        │
│  • Titan Embed V2 → ChromaDB (cosine index)         │
│  • SQLite hash cache  (incremental re-runs)         │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  LangGraph Pipeline  (agents/pipeline.py)           │
│                                                     │
│  language_router                                    │
│    ├─ cobol_agent  ─┐                               │
│    ├─ java_agent   ─┤                               │
│    ├─ sql_agent    ─┼─▶ verification_gate           │
│    └─ jcl_agent   ─┘      │  pass ──▶ cross_lang   │
│                            │  fail ──▶ reflexion    │
│                            │             │           │
│                            └─────────────┘           │
│  cross_language_linker                              │
│    └─▶ openlineage_emitter                          │
│           └─▶ neo4j_writer                          │
└────────────────────────┬────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Neo4j DB       output/*.json   ChromaDB
          │
          ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI  (api/main.py — port 8000)                 │
│  /api/lineage   — graph queries (Neo4j)             │
│  /api/rag       — Strands RAG chat (Bedrock)        │
│  /api/eval      — evaluation reports                │
│  /api/lineage/extract — pipeline trigger            │
└────────────┬──────────────────────────┬─────────────┘
             │                          │
             ▼                          ▼
  React + Cytoscape.js UI        Streamlit RAG chat
  (frontend/  — port 3000)       (streamlit_app/  — port 8501)
```

---

## Models (Amazon Bedrock)

| Purpose | Model ID | Used by |
|---|---|---|
| Embeddings | `amazon.titan-embed-text-v2:0` | `src/ingest.py`, RAG retrieval |
| Reasoning / extraction | `amazon.nova-pro-v1:0` | ReAct agents, Reflexion |
| LLM judge (optional) | `amazon.nova-pro-v1:0` | `evaluation/llm_judge.py` |

Configure via `.env` (see below). All model IDs are overridable per-agent.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Managed by `uv` |
| `uv` | `pip install uv` |
| Node.js 18+ | For the React frontend |
| AWS account | Bedrock access to Nova Pro + Titan Embed in your region |
| Neo4j Desktop 5+ | [Download](https://neo4j.com/download/) — create a local DB, enable APOC plugin |
| Jaeger (optional) | Docker: `docker run -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one` |

---

## Setup

### 1. First-time machine setup

```bash
bash scripts/setup.sh    # install uv, Node, Neo4j, Jaeger; creates .env from .env.example
```

### 2. Install Python and Node dependencies

```bash
make setup               # uv sync + npm install in frontend/ + create output dirs
```

### 3. Configure environment

Edit `.env` — required keys:

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

NEO4J_PASSWORD=your_password     # match your Neo4j Desktop DB password
NEO4J_URI=bolt://localhost:7687  # default

# Optional overrides
BEDROCK_TEXT_MODEL_ID=amazon.nova-pro-v1:0
BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0
REPO_PATH=./mock_code
OUTPUT_DIR=./output
REFLEXION_MAX_RETRIES=3
MIN_CONFIDENCE_THRESHOLD=0.1
ENABLE_TRACING=true
```

### 4. Start Neo4j Desktop

Create a local database and start it. Default bolt: `bolt://localhost:7687`.

---

## Running

### All services at once (recommended)

```bash
make all    # starts Neo4j check, Jaeger, FastAPI, Streamlit, React — Ctrl+C stops all
```

### Individual services

```bash
make start-neo4j      # verify Neo4j is running on bolt://localhost:7687
make start-jaeger     # Jaeger tracing UI → http://localhost:16686
make start-backend    # FastAPI → http://localhost:8000/docs
make start-streamlit  # RAG chat → http://localhost:8501
make frontend-dev     # React graph UI → http://localhost:3000
make status           # show which services are up
make stop             # kill all background processes
```

### Data pipeline

```bash
make ingest    # embed mock_code/ into ChromaDB (incremental via SQLite hash cache)
make pipeline  # run ReAct+Reflexion extraction → Neo4j + output/
make eval      # run 5-level evaluation against golden datasets and oracle
```

### Testing

```bash
make test              # uv run pytest tests/ -v --tb=short
make test-unit         # uv run pytest tests/unit/ -v
make check-imports     # smoke-test all Python module imports
make frontend-check    # TypeScript type-check
```

### CLI (direct)

```bash
uv run python main.py ingest   [--repo ./mock_code]
uv run python main.py pipeline [--repo ./mock_code]   # ingest + extract in one shot
uv run python main.py serve    [--host 0.0.0.0] [--port 8000]
```

---

## Project Structure

```
data-lineage-agentic-app/
│
├── mock_code/                          # Reference pipeline: MI4014 Credit Risk
│   ├── cobol/
│   │   ├── CRDB2EXT.cbl               # Phase 1: DB2 cursor → CUST.BHSCORE.EXTRACT
│   │   ├── CRTXNEXT.cbl               # Phase 2: CUST extract + DB2 txns → TRANS extract
│   │   ├── CRXMLGEN.cbl               # Phase 4: merged extract → XML file
│   │   └── copybooks/
│   │       ├── CRCUSTAC.cpy           # Customer account record layout
│   │       ├── CRTRANSR.cpy           # Transaction record layout
│   │       └── CRXMLTAG.cpy           # XML tag layout
│   ├── jcl/
│   │   └── CRJBHSCR.jcl              # Job: STEP010–STEP050 (incl. DFSORT JOINKEYS STEP030)
│   ├── sql/
│   │   ├── MI4014_EXT_TABLE.sql       # Oracle external table DDL (reads XML)
│   │   ├── MI4014_STAGE_LOAD.sql      # Staging table DDL + INSERT SELECT with type casts
│   │   └── MI4014_VIEW.sql            # V_MI4014_TRANSACCIONES_VALIDAS + V_MI4014_ACCOUNT_SUMMARY
│   ├── data/
│   │   └── MI4014_Transaction_Extract_TSB_NAM65_20260514.xml  # Sample XML output
│   └── expected_lineage/
│       └── expected_lineage.json      # Handcrafted ground-truth oracle (14 nodes, 15 edges)
│
├── agents/                            # LangGraph pipeline
│   ├── pipeline.py                    # Graph builder + run_pipeline() entry point
│   ├── state.py                       # LineageState TypedDict
│   ├── react_agent.py                 # cobol/java/sql/jcl extraction agents (Bedrock ReAct)
│   ├── reflexion.py                   # Episodic memory + oracle hint injection
│   ├── verification.py                # Programmatic AST verification gate (no LLM)
│   ├── cross_language_linker.py       # JCL DD→dataset→COBOL + Java→SQL resolution
│   ├── prompts/                       # System prompt text files per language
│   └── tools/                         # Agent tools: ast_query, vector_search, sqlglot, neo4j_query
│
├── parsers/                           # Deterministic language-specific parsers
│   ├── orchestrator.py                # ParserOrchestrator: routes files to right parser
│   ├── models.py                      # ChunkMetadata dataclass
│   ├── cobol_parser.py                # Paragraph/section/EXEC SQL chunker
│   ├── jcl_parser.py                  # JCL step/DD/SORT card parser
│   ├── sql_parser.py                  # SQL statement chunker (sqlglot-backed)
│   └── java_parser.py                 # Java class/method chunker (regex-based)
│
├── evaluation/                        # Five-level correctness framework
│   ├── runner.py                      # EvaluationRunner — orchestrates all levels + OTel spans
│   ├── level1_assertion.py            # Per-assertion AST + type checks
│   ├── level2_file.py                 # Per-file precision / recall / F1 / hallucination rate
│   ├── level3_system.py               # Aggregate system metrics + cross-language accuracy
│   ├── expected_lineage_evaluator.py  # Oracle: validates against expected_lineage.json (25 checks)
│   ├── path_evaluator.py              # End-to-end chain completeness (hop-by-hop break detection)
│   ├── llm_judge.py                   # LLM-as-judge for unmatched pair semantic equivalence
│   ├── golden_dataset_generator.py    # Parser-derived golden datasets (L1/L2 baseline)
│   └── golden/                        # Hand-annotated ground-truth golden files
│       ├── CRDB2EXT.golden.json
│       ├── CRTXNEXT.golden.json
│       ├── CRXMLGEN.golden.json
│       ├── MI4014_STAGE_LOAD.golden.json
│       ├── MI4014_VIEW.golden.json
│       └── cross_language.golden.json  # 14 cross-language edges for full MI4014 flow
│
├── graph/                             # Neo4j I/O
│   ├── writer.py                      # Neo4jLineageWriter: upsert, upstream/downstream queries
│   └── schema.py                      # Node/edge type definitions + Cypher constraint queries
│
├── lineage/
│   └── openlineage_emitter.py         # Converts assertions → OpenLineage event JSON
│
├── rag/                               # Strands Agents RAG
│   ├── strands_rag.py                 # StrandsRAG: vector_search, graph_traverse, impact_analysis
│   ├── hybrid_retriever.py            # ChromaDB + Neo4j hybrid retrieval
│   └── answer_generator.py            # Bedrock-backed answer synthesis
│
├── observability/
│   ├── tracing.py                     # OTel TracerProvider → Jaeger OTLP gRPC
│   └── metrics.py                     # In-process counters + histograms (assertions, retries, tokens)
│
├── api/                               # FastAPI application
│   ├── main.py                        # App factory, CORS, OTel lifespan, router mounts
│   ├── middleware/otel.py             # Request-level OTel spans
│   └── routers/
│       ├── lineage.py                 # /api/lineage — graph queries, search, impact, column flow
│       ├── extraction.py              # /api/lineage/extract — async pipeline trigger
│       ├── rag.py                     # /api/rag — streaming RAG chat + citation retrieval
│       └── evaluation.py             # /api/eval — evaluation reports + human review queue
│
├── src/                               # Ingestion layer
│   ├── ingest.py                      # File walk, chunking, Titan embedding, ChromaDB write
│   ├── config.py                      # Re-export of config.settings
│   ├── models.py                      # Shared Pydantic models
│   └── chunkers/
│       ├── cobol_chunker.py           # COBOL paragraph/section splitter
│       └── java_chunker.py            # Java class/method splitter
│
├── config/
│   └── settings.py                    # Pydantic-settings: all config from .env
│
├── embeddings/
│   └── pipeline.py                    # Embedding pipeline helpers
│
├── models/
│   └── lineage_models.py              # Pydantic models for lineage node/edge types
│
├── streamlit_app/                     # Streamlit RAG chat UI
│   ├── rag_chat.py                    # Main Streamlit app
│   ├── components/                    # Chat panel, citation card, sidebar
│   └── utils/                         # API client, streaming helpers
│
├── frontend/                          # React + Vite + TypeScript + Cytoscape.js
│   └── src/
│       └── App.tsx                    # Lineage graph visualisation entry point
│
├── tests/
│   └── unit/                          # pytest unit tests
│
├── observability/tracing.py           # OTel → Jaeger
├── neo4j_schema_migration.cypher      # Idempotent schema migration script
├── main.py                            # CLI: ingest | pipeline | serve
├── Makefile                           # All developer tasks
└── pyproject.toml                     # Python project manifest (uv-managed)
```

---

## Evaluation Framework (Five Levels)

The system validates extracted lineage at five complementary levels, each catching different failure modes:

| Level | Class | What it catches |
|---|---|---|
| **L1 — Assertion** | `AssertionEvaluator` | Per-assertion: entity in AST? operation at that line? types compatible? |
| **L2 — File** | `FileEvaluator` | Per-file precision / recall / F1 / hallucination rate vs golden dataset. Pass threshold: P≥0.90, R≥0.85, hallucination<5% |
| **L3 — System** | `SystemEvaluator` | Aggregate P/R/F1, cross-language link accuracy, OpenLineage schema compliance, latency p50/p95 |
| **Oracle** | `ExpectedLineageEvaluator` | 25 deterministic checks against `expected_lineage.json`: named programs, DB2/Oracle tables, JCL SORT step, XML intermediate file, copybooks, column-level path endpoints |
| **Path** | `PathEvaluator` | End-to-end chain completeness — reports the exact hop where each pipeline chain breaks |

An optional **LLM Judge** (`LLMJudge`) uses Bedrock to resolve unmatched pairs that differ only in entity naming (e.g. `BHSCOEXT` vs `CUST.BHSCORE.EXTRACT`). Enable with `EvaluationRunner(enable_llm_judge=True)`.

All evaluation spans are exported to Jaeger via OpenTelemetry. Failed oracle checks each produce a child span for fine-grained tracing.

### Reflexion + Oracle feedback loop

When the verification gate fails assertions, the reflexion node:
1. Accumulates AST failure context into `episodic_memory`.
2. Queries `ExpectedLineageEvaluator` and `PathEvaluator` for which oracle-expected elements are still missing.
3. Injects both as structured hints into the next agent invocation — e.g. *"MISSING LINEAGE: check cobol_program:CRXMLGEN failed — re-examine the source code for this element"*.

```bash
make eval    # generates golden datasets, runs all 5 levels, saves report to evaluation/reports/
```

---

## API Endpoints

### Lineage — `/api/lineage`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/graph` | Full lineage graph (≤500 nodes, ≤1000 edges) for Cytoscape.js |
| `GET` | `/entity/{entity_id}` | Upstream + downstream subgraph for one entity (depth 1–10) |
| `GET` | `/column/{table}/{column}` | Column-level lineage for a specific table.column |
| `GET` | `/columns/flow` | Full column-level flow for the Column Lineage UI page |
| `GET` | `/end-to-end` | Full path from `?source=` to `?target=` |
| `GET` | `/impact/{entity_id}` | Downstream impact analysis (what breaks if this changes?) |
| `GET` | `/summary` | Node/edge count breakdown by type and language |
| `GET` | `/search?q=` | Full-text search over node names, IDs, systems |
| `POST` | `/extract` | Trigger async pipeline extraction for a repo path |
| `GET` | `/extract/{job_id}/status` | Poll extraction job status |

### RAG — `/api/rag`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/query` | Streaming RAG answer: vector search + graph traversal + Bedrock answer |
| `GET` | `/citations` | ChromaDB citation retrieval for the last query |
| `GET` | `/history` | Conversation history |

### Evaluation — `/api/eval`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/report` | Most recent evaluation report JSON |
| `GET` | `/human-review` | Assertions escalated to human review |
| `POST` | `/human-review/{item_id}` | Submit approve/reject decision |

### Health — `/api/health`

Checks Neo4j, ChromaDB, and Bedrock connectivity. Returns `{"status": "ok"}` or `{"status": "degraded", "services": {...}}`.

**Interactive docs:** `http://localhost:8000/docs`

---

## Neo4j Schema

### Node types

| Label | Represents | Key properties |
|---|---|---|
| `DB2Table` | IBM DB2 table | `name`, `schema_name`, `columns`, `system` |
| `FlatFile` | VSAM / sequential dataset | `name`, `dsn`, `lrecl`, `format` |
| `XMLFile` | XML intermediate file | `name`, `dsn`, `schema_url` |
| `OracleTable` | Oracle relational table | `name`, `schema_name`, `database` |
| `OracleView` | Oracle view | `name`, `schema_name`, `definition` |
| `ExternalTable` | Oracle external table | `name`, `access_driver`, `location` |
| `COBOLProgram` | COBOL batch program | `name`, `program_id`, `file_path` |
| `JCLJob` | JCL job | `name`, `job_name`, `file_path` |
| `JCLStep` | JCL step | `name`, `step_name`, `program`, `sequence` |
| `DFSORTStep` | DFSORT / JOINKEYS step | `name`, `step_name`, `operation` |
| `JavaClass` | Java class | `name`, `class_name`, `package`, `file_path` |
| `SQLProcedure` | SQL script / stored proc | `name`, `file_path`, `language` |
| `Column` | Column-level node | `name`, `data_type`, `entity`, `position` |

### Relationship types

| Type | Meaning |
|---|---|
| `READS_FROM` | Transformation reads a data entity |
| `WRITES_TO` | Transformation writes a data entity |
| `MAPS_TO` | Column-level value flow with `transformation_expression` |
| `EXECUTES` | JCL job executes a program |
| `CALLS` | Program calls another program |
| `JOINS_WITH` | DFSORT/JOINKEYS merge relationship |
| `DEFINED_IN` | Column is defined in an entity |
| `CROSS_LANGUAGE_LINK` | Cross-language resolved link (JCL DD → COBOL, etc.) |

### Useful Cypher queries

```cypher
-- Full lineage graph (capped)
MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 200

-- What does CRDB2EXT read and write?
MATCH (p:COBOLProgram {name: 'CRDB2EXT'})-[r]-(e) RETURN p, r, e

-- Upstream of the Oracle staging table
MATCH path = (n)-[*1..6]->(t:OracleTable {name: 'MI4014_TRANSACCIONES_STG'}) RETURN path

-- End-to-end path from DB2 to Oracle summary view
MATCH path = (s:DB2Table {name: 'CRISK.CUST_ACCOUNT_MASTER'})-[*1..10]->(v:OracleView)
RETURN path

-- Column-level: trace TRANSACTION_AMOUNT through all hops
MATCH path = (c:Column {name: 'TRANSACTION_AMT'})-[:MAPS_TO*1..10]->(t:Column)
RETURN path

-- Orphan detection
MATCH (n) WHERE NOT (n)-[]-() RETURN n.name, labels(n)
```

---

## Service Ports

| Service | URL |
|---|---|
| FastAPI backend | `http://localhost:8000` |
| FastAPI docs | `http://localhost:8000/docs` |
| React lineage UI | `http://localhost:3000` |
| Streamlit RAG chat | `http://localhost:8501` |
| Neo4j browser | `http://localhost:7474` |
| Neo4j bolt | `bolt://localhost:7687` |
| Jaeger tracing UI | `http://localhost:16686` |
| Jaeger OTLP gRPC | `grpc://localhost:4317` |

---

## Outputs

After `make pipeline`:

| Output | Location | Contents |
|---|---|---|
| OpenLineage JSON | `output/{stem}_lineage.json` | Per-file OpenLineage events (inputs, outputs, job) |
| Human review queue | `output/human_review.json` | Assertions that failed all Reflexion retries |
| Neo4j graph | `bolt://localhost:7687` | Full typed lineage graph |
| Evaluation report | `evaluation/reports/eval_YYYYMMDD_HHMMSS.json` | All five evaluation levels, oracle checklist, path results |

---

## Incremental Re-runs

The ingestion step uses a SQLite hash cache (`hash_cache.db`). Re-running `make ingest` only re-embeds files whose content has changed since the last run. For a large codebase this reduces subsequent ingestion from minutes to seconds.

---

## Make Targets Quick Reference

```bash
make help          # list all targets

# Setup
make setup         # install deps + create dirs
make start-neo4j   # verify Neo4j is running
make start-jaeger  # start Jaeger (Docker)

# Services
make all           # start everything (blocking, Ctrl+C to stop)
make start-backend
make start-streamlit
make frontend-dev
make status
make stop

# Pipeline
make ingest        # embed source files into ChromaDB
make pipeline      # extract lineage (ReAct + Reflexion)
make eval          # run 5-level evaluation

# Quality
make test          # pytest
make test-unit     # unit tests only
make check-imports # smoke-test all module imports
make frontend-check

# Clean
make clean         # remove output/, chroma_db/, hash_cache.db
make clean-all     # also removes frontend/node_modules/ and .venv/
```
