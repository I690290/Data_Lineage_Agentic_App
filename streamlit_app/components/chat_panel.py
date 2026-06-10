"""Chat message rendering with citation support."""
from __future__ import annotations

import streamlit as st


def render_message(role: str, content: str, citations: list[dict] | None = None) -> None:
    """Render a chat message.

    Args:
        role: Chat role.
        content: Message content.
        citations: Optional citation list.
    """
    with st.chat_message(role):
        st.markdown(content)
        if citations and role == "assistant":
            st.caption(f"📎 {len(citations)} source(s) cited — see citation panel →")
