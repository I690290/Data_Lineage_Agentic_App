"""
Data Lineage Agentic App — CLI entry point.

Usage:
  python main.py ingest   [--repo REPO_PATH]
  python main.py agent    [--repo REPO_PATH]
  python main.py serve    [--host HOST] [--port PORT]
  python main.py pipeline [--repo REPO_PATH]   # ingest + agent in one shot
"""
import argparse
import sys


def cmd_ingest(args) -> None:
    from src.ingest import run_ingestion
    run_ingestion(repo_path=args.repo)


def cmd_agent(args) -> None:
    from src.agent import run_agent
    final_state = run_agent(repo_path=args.repo)
    errors = final_state.get("errors", [])
    nodes  = final_state.get("lineage_nodes", [])
    edges  = final_state.get("lineage_edges", [])
    print(f"\n=== Agent complete ===")
    print(f"  Nodes  : {len(nodes)}")
    print(f"  Edges  : {len(edges)}")
    print(f"  Issues : {len(errors)}")
    print(f"  JSON   : {final_state.get('output_json_path', 'N/A')}")
    if errors:
        print("  Errors :")
        for e in errors:
            print(f"    - {e}")


def cmd_serve(args) -> None:
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def cmd_pipeline(args) -> None:
    print("=== Step 1/2: Ingestion ===")
    cmd_ingest(args)
    print("\n=== Step 2/2: Agent pipeline ===")
    cmd_agent(args)


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Data Lineage Agentic App — LangGraph + Amazon Titan on Bedrock"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Chunk and embed source files into ChromaDB")
    p_ingest.add_argument("--repo", default=None, help="Path to repo (overrides REPO_PATH in .env)")

    # agent
    p_agent = sub.add_parser("agent", help="Run the LangGraph lineage extraction pipeline")
    p_agent.add_argument("--repo", default=None)

    # serve
    p_serve = sub.add_parser("serve", help="Start the FastAPI visualisation server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    # pipeline (ingest + agent)
    p_pipe = sub.add_parser("pipeline", help="Run full pipeline: ingest then agent")
    p_pipe.add_argument("--repo", default=None)

    args = parser.parse_args()
    dispatch = {
        "ingest":   cmd_ingest,
        "agent":    cmd_agent,
        "serve":    cmd_serve,
        "pipeline": cmd_pipeline,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    cli()
