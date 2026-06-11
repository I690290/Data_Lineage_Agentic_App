"""
Data Lineage Agentic App — CLI entry point.

Usage:
  python main.py ingest   [--repo REPO_PATH]
  python main.py pipeline [--repo REPO_PATH]   # ingest + extract in one shot
  python main.py serve    [--host HOST] [--port PORT]
"""
import argparse


def cmd_ingest(args) -> None:
    from src.ingest import run_ingestion
    run_ingestion(repo_path=args.repo)


def cmd_pipeline(args) -> None:
    from agents.pipeline import run_pipeline
    final_state = run_pipeline(repo_path=args.repo)
    verified = final_state.get("verified_lineage", [])
    review = final_state.get("needs_human_review", [])
    errors = final_state.get("errors", [])
    print(f"\n=== Pipeline complete ===")
    print(f"  Verified : {len(verified)}")
    print(f"  Review   : {len(review)}")
    print(f"  Errors   : {len(errors)}")
    if errors:
        for e in errors:
            print(f"    - {e}")


def cmd_ingest_then_pipeline(args) -> None:
    print("=== Step 1/2: Ingestion ===")
    cmd_ingest(args)
    print("\n=== Step 2/2: Lineage extraction ===")
    cmd_pipeline(args)


def cmd_serve(args) -> None:
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Data Lineage Agentic App — LangGraph ReAct+Reflexion on Amazon Bedrock"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Chunk and embed source files into ChromaDB")
    p_ingest.add_argument("--repo", default=None, help="Path to repo (overrides REPO_PATH in .env)")

    # pipeline (ingest + extract)
    p_pipe = sub.add_parser("pipeline", help="Run full pipeline: ingest then ReAct+Reflexion extraction")
    p_pipe.add_argument("--repo", default=None)

    # serve
    p_serve = sub.add_parser("serve", help="Start the FastAPI visualisation server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    dispatch = {
        "ingest":   cmd_ingest,
        "pipeline": cmd_ingest_then_pipeline,
        "serve":    cmd_serve,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    cli()
