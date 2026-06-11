"""Individual citation card component for the RAG chat UI."""
from __future__ import annotations

import streamlit as st


_LANG_MAP: dict[str, str] = {
    ".cbl": "cobol",
    ".cob": "cobol",
    ".cpy": "cobol",
    ".jcl": "text",
    ".java": "java",
    ".sql": "sql",
    ".xml": "xml",
    ".yml": "yaml",
    ".json": "json",
}

_BADGE_COLOURS: dict[str, str] = {
    "graph":  "#28a745",  # green  — Neo4j result
    "vector": "#007bff",  # blue   — ChromaDB chunk
    "cobol":  "#6f42c1",  # purple
    "sql":    "#fd7e14",  # orange
    "jcl":    "#20c997",  # teal
    "java":   "#e83e8c",  # pink
}


def render_citation_card(citation: dict, index: int) -> None:
    """Render a single citation card.

    Args:
        citation: Citation dictionary with source_file, chunk_type, snippet, etc.
        index: Card index for unique keys.
    """
    source_file = citation.get("source_file", "unknown")
    chunk_type = citation.get("chunk_type", "vector")
    language = citation.get("language", "")
    snippet = citation.get("snippet", "")
    key = citation.get("key", f"[{index + 1}]")
    relevance = citation.get("relevance_score")

    # Determine syntax language from file extension
    lower_source = source_file.lower()
    display_lang = "text"
    for ext, lang in _LANG_MAP.items():
        if lower_source.endswith(ext):
            display_lang = lang
            break
    if language and display_lang == "text":
        display_lang = language.lower()

    # Badge colour — prefer chunk_type, then language
    badge_key = chunk_type if chunk_type in _BADGE_COLOURS else language.lower()
    badge_colour = _BADGE_COLOURS.get(badge_key, "#6c757d")
    badge_html = (
        f'<span style="background:{badge_colour};color:white;padding:2px 8px;'
        f'border-radius:12px;font-size:0.75rem;">{chunk_type}</span>'
    )

    relevance_html = ""
    if relevance is not None:
        pct = int(relevance * 100)
        relevance_html = (
            f' &nbsp; <span style="color:#888;font-size:0.75rem;">relevance {pct}%</span>'
        )

    file_name = source_file.split("/")[-1]

    with st.container():
        st.markdown(
            f"**{key}** &nbsp; `{file_name}` &nbsp; {badge_html}{relevance_html}",
            unsafe_allow_html=True,
        )
        if snippet:
            st.code(snippet[:600], language=display_lang)
        with st.expander("Details", expanded=False):
            st.write(f"**Full path:** `{source_file}`")
            st.write(f"**Language:** {language or display_lang}")
            st.write(f"**Chunk type:** {chunk_type}")
            if relevance is not None:
                st.write(f"**Relevance:** {relevance:.4f}")
        st.divider()
