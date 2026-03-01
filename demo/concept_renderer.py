"""
Thin rendering helpers for concept content in the Streamlit demo.
"""

import streamlit as st
from concepts import ALL_CONCEPTS, CIRCULAR_DEP_CONCEPTS, STEP_CONCEPTS, Concept


def _render_concept_summary(concept: Concept) -> None:
    """Render a single concept as icon + title + summary."""
    st.markdown(f"**{concept.icon} {concept.title}**")
    st.markdown(concept.summary)


def render_step_concepts(step_number: int) -> None:
    """Render a collapsed expander with concept summaries for a given step."""
    concepts = STEP_CONCEPTS.get(step_number)
    if not concepts:
        return
    with st.expander("Key Concepts", expanded=False):
        for concept in concepts:
            _render_concept_summary(concept)
            st.divider()


def render_circular_dep_concepts() -> None:
    """Render circular dependency remediation concepts (shown after cycle detection)."""
    with st.expander("Understanding Circular Dependencies", expanded=False):
        for concept in CIRCULAR_DEP_CONCEPTS:
            _render_concept_summary(concept)
            st.divider()


def render_reference_page() -> None:
    """Render the full concept reference page (8th nav item)."""
    st.header("Concepts & Reference")
    st.caption("Key SLO engineering concepts used throughout this demo")

    for concept in ALL_CONCEPTS:
        with st.expander(f"{concept.icon} {concept.title}", expanded=False):
            st.markdown(concept.detail)
