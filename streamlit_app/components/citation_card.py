"""Individual citation card component for the RAG chat UI."""
from __future__ import annotations

import streamlit as st


def render_citation_card(citation: dict, index: int) -> None:
    """Render a single citation card.

    Args:
        citation: Citation dictionary.
        index: Card index.
    """
    source_file = citation.get("source_file", "unknown")
    chunk_type = citation.get("chunk_type", "vector")
    snippet = citation.get("snippet", "")
    key = citation.get("key", f"[{index}]")

    lang = "text"
    lower_source = source_file.lower()
    if any(lower_source.endswith(ext) for ext in (".cbl", ".cob")):
        lang = "cobol"
    elif lower_source.endswith(".java"):
        lang = "java"

    badge_colour = "#28a745" if chunk_type == "graph" else "#007bff"
    badge_html = (
        f'<span style="background:{badge_colour};color:white;padding:2px 8px;'
        f'border-radius:12px;font-size:0.75rem;">{chunk_type}</span>'
    )

    with st.container():
        st.markdown(
            f"**{key}** &nbsp; **{source_file.split('/')[-1]}** &nbsp; {badge_html}",
            unsafe_allow_html=True,
        )
        if snippet:
            st.code(snippet[:500], language=lang)
        with st.expander("Details", expanded=False):
            st.write(f"**Full path:** `{source_file}`")
            st.write(f"**Chunk type:** {chunk_type}")
        st.divider()
