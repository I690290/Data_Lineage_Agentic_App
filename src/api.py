"""FastAPI visualisation and RAG API."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from models.lineage_models import Citation, RagAnswer
from rag.answer_generator import AnswerGenerator
from rag.hybrid_retriever import HybridRetriever
from src.config import settings
from src.neo4j_writer import (
    fetch_column_lineage,
    fetch_entity_subgraph,
    fetch_full_lineage,
    fetch_lineage_summary,
    fetch_transformation_snippet,
)

app = FastAPI(
    title='Data Lineage API',
    description='Serves COBOL and Java data lineage graphs for Cytoscape.js visualisation',
    version='0.1.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

_rag_history_db = Path(__file__).parent.parent / 'rag_history.db'


def _init_rag_db() -> None:
    """Initialise the RAG history database."""
    conn = sqlite3.connect(str(_rag_history_db))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations_json TEXT DEFAULT '[]',
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


_init_rag_db()
_retriever: HybridRetriever | None = None
_generator: AnswerGenerator | None = None


def _get_rag_components() -> tuple[HybridRetriever, AnswerGenerator]:
    """Lazily initialise the retriever and answer generator."""
    global _retriever, _generator
    if _retriever is None:
        _retriever = HybridRetriever()
    if _generator is None:
        _generator = AnswerGenerator()
    return _retriever, _generator


_static_dir = Path(__file__).parent.parent / 'static'
if _static_dir.exists():
    app.mount('/static', StaticFiles(directory=str(_static_dir)), name='static')


@app.get('/', response_model=None)
async def root():
    """Redirect root to the visualisation UI."""
    index = _static_dir / 'index.html'
    if index.exists():
        return FileResponse(str(index))
    return {'message': 'Data Lineage API — visit /docs for endpoint reference'}


@app.get('/health')
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {'status': 'ok'}


@app.get('/lineage')
async def get_full_lineage() -> JSONResponse:
    """Return the full lineage graph, falling back to the last JSON export."""
    try:
        return JSONResponse(content=fetch_full_lineage())
    except Exception as neo4j_err:
        json_path = Path(settings.lineage_json_path)
        if json_path.exists():
            try:
                return JSONResponse(content=json.loads(json_path.read_text(encoding='utf-8')))
            except Exception as parse_err:
                raise HTTPException(status_code=500, detail=f'Lineage JSON file is corrupt: {parse_err}')
        raise HTTPException(status_code=503, detail=f'Neo4j unavailable and no fallback JSON found: {neo4j_err}')


@app.get('/lineage/entity/{name}')
async def get_entity_subgraph(name: str, depth: int = 3) -> JSONResponse:
    """Return a subgraph centered on a named entity."""
    try:
        data = fetch_entity_subgraph(name, depth=depth)
        if not data['nodes']:
            raise HTTPException(status_code=404, detail=f"Entity '{name}' not found in lineage graph")
        return JSONResponse(content=data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/lineage/json')
async def get_lineage_json() -> JSONResponse:
    """Serve the raw lineage JSON output file."""
    json_path = Path(settings.lineage_json_path)
    if not json_path.exists():
        raise HTTPException(
            status_code=404,
            detail='No lineage JSON found — run the agent pipeline first (python main.py agent)',
        )
    return JSONResponse(content=json.loads(json_path.read_text(encoding='utf-8')))


@app.get('/lineage/entities')
async def list_entities() -> dict[str, list[str]]:
    """List all entity names in the lineage graph."""
    try:
        data = fetch_full_lineage()
        entities = [
            node['data'].get('name', '')
            for node in data['nodes']
            if node['data'].get('type') == 'DataEntity' or node['data'].get('node_type') == 'DataEntity'
        ]
        return {'entities': sorted(set(entity for entity in entities if entity))}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get('/lineage/summary')
async def get_lineage_summary() -> JSONResponse:
    """Return summary counts for the lineage graph."""
    try:
        return JSONResponse(content=fetch_lineage_summary())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get('/lineage/column/{output_file:path}')
async def get_column_lineage(output_file: str, include_low_confidence: bool = False) -> JSONResponse:
    """Return Cytoscape.js JSON for column-level lineage."""
    try:
        data = fetch_column_lineage(output_file)
        if not include_low_confidence:
            kept_nodes = [node for node in data['nodes'] if not node['data'].get('low_confidence', False)]
            kept_ids = {node['data']['id'] for node in kept_nodes}
            data['nodes'] = kept_nodes
            data['edges'] = [
                edge
                for edge in data['edges']
                if edge['data']['source'] in kept_ids and edge['data']['target'] in kept_ids
            ]
        return JSONResponse(content=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/lineage/snippet/{transformation_id}')
async def get_transformation_snippet(transformation_id: str) -> JSONResponse:
    """Retrieve a transformation code snippet by step ID."""
    try:
        result = fetch_transformation_snippet(transformation_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Transformation '{transformation_id}' not found")
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post('/rag/ask')
async def rag_ask(payload: dict = Body(...)):
    """Answer a lineage question using hybrid RAG."""
    question = payload.get('question', '').strip()
    stream_mode = payload.get('stream', False)
    max_chunks = int(payload.get('max_chunks', 8))
    if not question:
        raise HTTPException(status_code=400, detail='question is required')

    retriever, generator = _get_rag_components()
    try:
        chunks = await retriever.retrieve(question, max_chunks=max_chunks)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Retrieval failed: {exc}')

    if stream_mode:
        async def event_stream():
            full_text = ''
            citations_data: list[dict] = []
            token_gen = generator.generate(question, chunks, stream=True)
            for token in token_gen:
                if '__CITATIONS__' in token:
                    parts = token.split('__CITATIONS__', 1)
                    if parts[0]:
                        full_text += parts[0]
                        yield {'event': 'token', 'data': parts[0]}
                    try:
                        citations_data = json.loads(parts[1].replace('__END_CITATIONS__', ''))
                    except Exception:
                        citations_data = []
                    break
                full_text += token
                yield {'event': 'token', 'data': token}
            try:
                conn = sqlite3.connect(str(_rag_history_db))
                conn.execute(
                    'INSERT INTO rag_history (question, answer, citations_json, timestamp) VALUES (?, ?, ?, ?)',
                    (question, full_text, json.dumps(citations_data), datetime.utcnow().isoformat()),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            yield {'event': 'citations', 'data': json.dumps(citations_data)}

        return EventSourceResponse(event_stream())

    result = generator.generate(question, chunks, stream=False)
    if not isinstance(result, RagAnswer):
        raise HTTPException(status_code=500, detail='Unexpected streaming result')
    citations_data = [
        {
            'key': citation.key,
            'source_file': citation.source_file,
            'chunk_type': citation.chunk_type,
            'snippet': citation.snippet,
        }
        for citation in result.citations
    ]
    try:
        conn = sqlite3.connect(str(_rag_history_db))
        conn.execute(
            'INSERT INTO rag_history (question, answer, citations_json, timestamp) VALUES (?, ?, ?, ?)',
            (question, result.answer_text, json.dumps(citations_data), datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return {'answer': result.answer_text, 'citations': citations_data}


@app.get('/rag/history')
async def get_rag_history() -> list[dict]:
    """Return the last 20 RAG question and answer pairs."""
    try:
        conn = sqlite3.connect(str(_rag_history_db))
        rows = conn.execute(
            'SELECT id, question, answer, citations_json, timestamp FROM rag_history ORDER BY id DESC LIMIT 20'
        ).fetchall()
        conn.close()
        return [
            {
                'id': row[0],
                'question': row[1],
                'answer': row[2],
                'citations': json.loads(row[3] or '[]'),
                'timestamp': row[4],
            }
            for row in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete('/rag/history')
async def delete_rag_history() -> dict[str, str]:
    """Clear all RAG conversation history."""
    try:
        conn = sqlite3.connect(str(_rag_history_db))
        conn.execute('DELETE FROM rag_history')
        conn.commit()
        conn.close()
        return {'status': 'cleared'}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
