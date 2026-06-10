"""Configuration, history, and controls sidebar for the RAG chat app."""
from __future__ import annotations

import streamlit as st

from streamlit_app.config import LINEAGE_VIEWER_URL
from streamlit_app.utils.api_client import APIClientError, LineageAPIClient


@st.cache_data(ttl=300)
def _cached_summary(base_url: str) -> dict:
    """Fetch and cache lineage summary stats."""
    client = LineageAPIClient(base_url=base_url)
    return client.get_summary()


def render_sidebar(api_client: LineageAPIClient) -> None:
    """Render the full Streamlit sidebar."""
    with st.sidebar:
        st.markdown("### 🗺️ Navigation")
        st.markdown(f"**[🔍 Lineage Explorer]({LINEAGE_VIEWER_URL})**")
        st.divider()

        st.markdown("### ⚙️ RAG Settings")
        st.toggle("Streaming mode", key="stream_mode", value=True)
        st.toggle("Show graph citations only", key="show_graph_chunks", value=False)
        st.slider("Max retrieved chunks", min_value=4, max_value=12, value=8, key="max_chunks")
        st.divider()

        st.markdown("### 📜 Conversation History")
        try:
            history = api_client.get_history()
        except APIClientError:
            history = []

        if history:
            for entry in history[:10]:
                question = entry.get("question", "")
                label = f"{question[:60]}…" if len(question) > 60 else question
                with st.expander(label):
                    st.markdown(f"**Q:** {question}")
                    st.markdown(f"**A:** {entry.get('answer', '')[:300]}")
                    if st.button("Load this conversation", key=f"load_{entry.get('id')}"):
                        st.session_state.messages = [
                            {"role": "user", "content": entry.get("question", ""), "citations": []},
                            {
                                "role": "assistant",
                                "content": entry.get("answer", ""),
                                "citations": entry.get("citations", []),
                            },
                        ]
                        st.rerun()
        else:
            st.caption("No conversation history yet.")

        if st.button("🗑️ Clear History"):
            try:
                api_client.delete_history()
                st.session_state.messages = []
                st.success("History cleared")
                st.rerun()
            except APIClientError:
                st.session_state.messages = []
                st.rerun()

        st.divider()
        st.markdown("### 📊 Graph Stats")
        try:
            summary = _cached_summary(api_client._base_url)
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Entities", summary.get("entity_count", 0))
                st.metric("JCL Jobs", summary.get("job_count", 0))
            with col2:
                st.metric("COBOL Programs", summary.get("cobol_count", 0))
                st.metric("Java Classes", summary.get("java_count", 0))
            total = summary.get("total_nodes", 0)
            edges = summary.get("edge_count", 0)
            if total:
                st.caption(f"{total} nodes · {edges} relationships in graph")
