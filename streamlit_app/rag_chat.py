"""
Lineage RAG Assistant — Streamlit chat application.
Communicates with the FastAPI backend for retrieval-augmented answers.
Run with: streamlit run streamlit_app/rag_chat.py --server.port 8501
"""
from __future__ import annotations

import streamlit as st

from streamlit_app.components.chat_panel import render_message
from streamlit_app.components.citation_card import render_citation_card
from streamlit_app.components.sidebar import render_sidebar
from streamlit_app.config import FASTAPI_BASE_URL
from streamlit_app.utils.api_client import APIClientError, LineageAPIClient
from streamlit_app.utils.streaming import CitationsPayload, stream_rag_response

st.set_page_config(
    page_title="Lineage RAG Assistant",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init_session_state() -> None:
    """Initialise Streamlit session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_citations" not in st.session_state:
        st.session_state.current_citations = []
    if "stream_mode" not in st.session_state:
        st.session_state.stream_mode = True
    if "show_graph_chunks" not in st.session_state:
        st.session_state.show_graph_chunks = False
    if "max_chunks" not in st.session_state:
        st.session_state.max_chunks = 8


def _check_api_health(client: LineageAPIClient) -> bool:
    """Check whether the FastAPI backend is reachable."""
    try:
        import httpx

        response = httpx.get(f"{FASTAPI_BASE_URL}/api/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def main() -> None:
    """Run the Streamlit application."""
    _init_session_state()
    api_client = LineageAPIClient(base_url=FASTAPI_BASE_URL)

    if not _check_api_health(api_client):
        st.error(
            f"⚠️ Cannot connect to FastAPI backend at `{FASTAPI_BASE_URL}`. "
            "Start the server with `uv run python main.py serve` and reload."
        )
        if st.button("🔄 Retry Connection"):
            st.rerun()
        return

    render_sidebar(api_client)
    chat_col, citation_col = st.columns([3, 1])

    with chat_col:
        st.title("🔍 Lineage RAG Assistant")
        st.caption(
            "Ask questions about data lineage, transformations, source fields, and COBOL/Java pipelines."
        )

        for message in st.session_state.messages:
            render_message(message["role"], message["content"], message.get("citations"))

        user_input = st.chat_input("Ask about data lineage, transformations, or source fields…")
        if user_input:
            st.session_state.messages.append(
                {"role": "user", "content": user_input, "citations": []}
            )
            render_message("user", user_input)

            stream_mode = st.session_state.get("stream_mode", True)
            max_chunks = st.session_state.get("max_chunks", 8)
            with st.chat_message("assistant"):
                placeholder = st.empty()
                full_answer = ""
                citations: list[dict] = []

                if stream_mode:
                    for token in stream_rag_response(
                        user_input,
                        api_base_url=FASTAPI_BASE_URL,
                        max_chunks=max_chunks,
                    ):
                        if isinstance(token, CitationsPayload):
                            citations = token.citations
                        else:
                            full_answer += token
                            placeholder.markdown(full_answer + "▌")
                    placeholder.markdown(full_answer)
                else:
                    placeholder.markdown("_Thinking…_")
                    try:
                        result = api_client.ask_sync(user_input, max_chunks=max_chunks)
                        full_answer = result.answer
                        citations = result.citations
                        placeholder.markdown(full_answer)
                    except APIClientError as exc:
                        full_answer = f"Error: {exc}"
                        placeholder.markdown(full_answer)

            st.session_state.messages.append(
                {"role": "assistant", "content": full_answer, "citations": citations}
            )
            st.session_state.current_citations = citations
            st.rerun()

    with citation_col:
        st.markdown("### 📎 Citations")
        citations_to_show = st.session_state.current_citations
        if st.session_state.get("show_graph_chunks", False):
            citations_to_show = [
                citation for citation in citations_to_show if citation.get("chunk_type") == "graph"
            ]

        if citations_to_show:
            for index, citation in enumerate(citations_to_show):
                render_citation_card(citation, index)
        else:
            st.caption("Citations from the most recent answer will appear here.")


if __name__ == "__main__":
    main()
