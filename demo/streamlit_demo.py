"""
SLO Recommendation Engine - Interactive Streamlit Demo
Walks through the full workflow with visual UI, editable inputs, and formatted results.

Usage:
    streamlit run scripts/streamlit_demo.py
"""

import json
from datetime import datetime

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import requests
import streamlit as st

from concept_renderer import render_circular_dep_concepts, render_reference_page, render_step_concepts

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEPS = [
    "1. Ingest Dependency Graph",
    "2. Query Subgraph",
    "3. SLO Recommendations",
    "4. Accept SLO",
    "5. Modify SLO",
    "6. Impact Analysis",
    "7. Audit History",
    "Concepts & Reference",
]

DEMO_DATA_BY_SOURCE = {
    "manual": {
        "nodes": [
            {"service_id": "api-gateway", "metadata": {"team": "platform", "criticality": "high"}},
            {"service_id": "checkout-service", "metadata": {"team": "commerce", "criticality": "high"}},
            {"service_id": "user-service", "metadata": {"team": "identity", "criticality": "high"}},
            {"service_id": "payment-service", "metadata": {"team": "payments", "criticality": "high"}},
            {"service_id": "inventory-service", "metadata": {"team": "commerce", "criticality": "medium"}},
            {"service_id": "auth-service", "metadata": {"team": "identity", "criticality": "high"}},
            {"service_id": "notification-service", "metadata": {"team": "platform", "criticality": "low"}},
            {"service_id": "analytics-service", "metadata": {"team": "data", "criticality": "low"}},
        ],
        "edges": [
            {"source": "api-gateway", "target": "checkout-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "api-gateway", "target": "user-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "checkout-service", "target": "payment-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "checkout-service", "target": "inventory-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "checkout-service", "target": "user-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "payment-service", "target": "auth-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "checkout-service", "target": "notification-service", "attributes": {"communication_mode": "async", "criticality": "soft"}},
            {"source": "api-gateway", "target": "analytics-service", "attributes": {"communication_mode": "async", "criticality": "soft"}},
            {"source": "inventory-service", "target": "notification-service", "attributes": {"communication_mode": "async", "criticality": "soft"}},
            {"source": "user-service", "target": "auth-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            # Circular dependency: auth-service -> user-service -> auth-service
            {"source": "auth-service", "target": "user-service", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            # Another cycle: payment-service -> checkout-service (completes a cycle)
            {"source": "payment-service", "target": "checkout-service", "attributes": {"communication_mode": "sync", "criticality": "degraded"}},
        ],
    },
    "otel_service_graph": {
        "nodes": [
            {"service_id": "frontend", "metadata": {"team": "platform", "criticality": "high", "instrumentation": "auto", "traces_per_min": 15000}},
            {"service_id": "api-server", "metadata": {"team": "platform", "criticality": "high", "instrumentation": "manual", "traces_per_min": 12000}},
            {"service_id": "order-processor", "metadata": {"team": "commerce", "criticality": "high", "instrumentation": "auto", "traces_per_min": 8000}},
            {"service_id": "payment-gateway", "metadata": {"team": "payments", "criticality": "high", "instrumentation": "manual", "traces_per_min": 5000}},
            {"service_id": "inventory-db", "metadata": {"team": "commerce", "criticality": "medium", "instrumentation": "auto", "traces_per_min": 3000}},
            {"service_id": "user-profile", "metadata": {"team": "identity", "criticality": "high", "instrumentation": "manual", "traces_per_min": 6000}},
            {"service_id": "email-worker", "metadata": {"team": "platform", "criticality": "low", "instrumentation": "auto", "traces_per_min": 500}},
        ],
        "edges": [
            {"source": "frontend", "target": "api-server", "attributes": {"communication_mode": "sync", "criticality": "hard", "avg_latency_ms": 45}},
            {"source": "api-server", "target": "order-processor", "attributes": {"communication_mode": "sync", "criticality": "hard", "avg_latency_ms": 120}},
            {"source": "api-server", "target": "user-profile", "attributes": {"communication_mode": "sync", "criticality": "hard", "avg_latency_ms": 30}},
            {"source": "order-processor", "target": "payment-gateway", "attributes": {"communication_mode": "sync", "criticality": "hard", "avg_latency_ms": 200}},
            {"source": "order-processor", "target": "inventory-db", "attributes": {"communication_mode": "sync", "criticality": "hard", "avg_latency_ms": 15}},
            {"source": "order-processor", "target": "email-worker", "attributes": {"communication_mode": "async", "criticality": "soft", "avg_latency_ms": 5}},
        ],
    },
    "kubernetes": {
        "nodes": [
            {"service_id": "ingress-nginx", "metadata": {"team": "platform", "criticality": "high", "namespace": "ingress", "replicas": 3, "cpu_request": "500m"}},
            {"service_id": "web-app", "metadata": {"team": "frontend", "criticality": "high", "namespace": "production", "replicas": 5, "cpu_request": "1000m"}},
            {"service_id": "order-service", "metadata": {"team": "commerce", "criticality": "high", "namespace": "production", "replicas": 4, "cpu_request": "2000m"}},
            {"service_id": "payment-processor", "metadata": {"team": "payments", "criticality": "high", "namespace": "production", "replicas": 3, "cpu_request": "1500m"}},
            {"service_id": "product-catalog", "metadata": {"team": "commerce", "criticality": "medium", "namespace": "production", "replicas": 2, "cpu_request": "1000m"}},
            {"service_id": "postgres-primary", "metadata": {"team": "platform", "criticality": "high", "namespace": "database", "replicas": 1, "cpu_request": "4000m"}},
            {"service_id": "redis-cache", "metadata": {"team": "platform", "criticality": "medium", "namespace": "cache", "replicas": 3, "cpu_request": "500m"}},
        ],
        "edges": [
            {"source": "ingress-nginx", "target": "web-app", "attributes": {"communication_mode": "sync", "criticality": "hard", "protocol": "http"}},
            {"source": "web-app", "target": "order-service", "attributes": {"communication_mode": "sync", "criticality": "hard", "protocol": "grpc"}},
            {"source": "web-app", "target": "product-catalog", "attributes": {"communication_mode": "sync", "criticality": "hard", "protocol": "http"}},
            {"source": "order-service", "target": "payment-processor", "attributes": {"communication_mode": "sync", "criticality": "hard", "protocol": "grpc"}},
            {"source": "order-service", "target": "postgres-primary", "attributes": {"communication_mode": "sync", "criticality": "hard", "protocol": "tcp"}},
            {"source": "web-app", "target": "redis-cache", "attributes": {"communication_mode": "sync", "criticality": "soft", "protocol": "tcp"}},
        ],
    },
    "service_mesh": {
        "nodes": [
            {"service_id": "gateway-proxy", "metadata": {"team": "platform", "criticality": "high", "mesh": "istio", "mtls_mode": "strict", "circuit_breaker": True}},
            {"service_id": "webapp-v1", "metadata": {"team": "frontend", "criticality": "high", "mesh": "istio", "mtls_mode": "strict", "circuit_breaker": False}},
            {"service_id": "orders-v2", "metadata": {"team": "commerce", "criticality": "high", "mesh": "istio", "mtls_mode": "strict", "circuit_breaker": True}},
            {"service_id": "payments-v1", "metadata": {"team": "payments", "criticality": "high", "mesh": "istio", "mtls_mode": "strict", "circuit_breaker": True}},
            {"service_id": "inventory-v1", "metadata": {"team": "commerce", "criticality": "medium", "mesh": "istio", "mtls_mode": "permissive", "circuit_breaker": False}},
            {"service_id": "notifications-v1", "metadata": {"team": "platform", "criticality": "low", "mesh": "istio", "mtls_mode": "permissive", "circuit_breaker": False}},
        ],
        "edges": [
            {"source": "gateway-proxy", "target": "webapp-v1", "attributes": {"communication_mode": "sync", "criticality": "hard", "retry_policy": "3x", "timeout_ms": 5000}},
            {"source": "webapp-v1", "target": "orders-v2", "attributes": {"communication_mode": "sync", "criticality": "hard", "retry_policy": "2x", "timeout_ms": 3000}},
            {"source": "orders-v2", "target": "payments-v1", "attributes": {"communication_mode": "sync", "criticality": "hard", "retry_policy": "1x", "timeout_ms": 10000}},
            {"source": "orders-v2", "target": "inventory-v1", "attributes": {"communication_mode": "sync", "criticality": "hard", "retry_policy": "3x", "timeout_ms": 2000}},
            {"source": "orders-v2", "target": "notifications-v1", "attributes": {"communication_mode": "async", "criticality": "soft", "retry_policy": "5x", "timeout_ms": 1000}},
        ],
    },
    "demo_with_issues": {
        "nodes": [
            # Intentionally define only 3 services, but reference 6 in edges to trigger warnings
            {"service_id": "api-gateway", "metadata": {"team": "platform", "criticality": "high"}},
            {"service_id": "service-a", "metadata": {"team": "team-a", "criticality": "high"}},
            {"service_id": "service-b", "metadata": {"team": "team-b", "criticality": "medium"}},
        ],
        "edges": [
            # Normal edges
            {"source": "api-gateway", "target": "service-a", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "api-gateway", "target": "service-b", "attributes": {"communication_mode": "sync", "criticality": "hard"}},

            # Edges to undefined services (will trigger warnings about auto-created services)
            {"source": "service-a", "target": "service-c", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "service-b", "target": "service-d", "attributes": {"communication_mode": "async", "criticality": "soft"}},
            {"source": "service-c", "target": "service-e", "attributes": {"communication_mode": "sync", "criticality": "degraded"}},

            # Create circular dependencies
            # Cycle 1: service-a -> service-c -> service-a
            {"source": "service-c", "target": "service-a", "attributes": {"communication_mode": "sync", "criticality": "hard"}},

            # Cycle 2: service-b -> service-d -> service-e -> service-b
            {"source": "service-d", "target": "service-e", "attributes": {"communication_mode": "sync", "criticality": "hard"}},
            {"source": "service-e", "target": "service-b", "attributes": {"communication_mode": "sync", "criticality": "hard"}},

            # Cycle 3: api-gateway -> service-a -> service-c -> api-gateway (larger cycle)
            {"source": "service-c", "target": "api-gateway", "attributes": {"communication_mode": "sync", "criticality": "degraded"}},
        ],
    },
}

# Backward compatibility - default to manual
DEMO_NODES = DEMO_DATA_BY_SOURCE["manual"]["nodes"]
DEMO_EDGES = DEMO_DATA_BY_SOURCE["manual"]["edges"]

# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


class SloEngineClient:
    """Thin wrapper around the SLO Engine REST API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        headers = {"Content-Type": "application/json"}
        # Only add Authorization header if API key is provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.session.headers.update(headers)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict | None:
        try:
            resp = self.session.request(method, self._url(path), timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError:
            st.error(f"Connection error: cannot reach {self.base_url}. Is the API running?")
        except requests.Timeout:
            st.error("Request timed out after 30s.")
        except requests.HTTPError as exc:
            detail = ""
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except Exception:
                detail = exc.response.text
            st.error(f"HTTP {exc.response.status_code}: {detail}")
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")
        return None

    def health(self) -> dict | None:
        return self._request("GET", "/api/v1/health")

    def ingest_dependencies(self, payload: dict) -> dict | None:
        # Use demo endpoint that includes circular dependency detection
        return self._request("POST", "/api/v1/demo/dependencies", json=payload)

    def query_subgraph(self, service_id: str, direction: str, depth: int) -> dict | None:
        return self._request(
            "GET",
            f"/api/v1/services/{service_id}/dependencies",
            params={"direction": direction, "depth": depth},
        )

    def get_recommendations(self, service_id: str, sli_type: str, lookback_days: int) -> dict | None:
        # Use demo endpoint that returns synthetic data without requiring telemetry
        return self._request(
            "GET",
            f"/api/v1/demo/services/{service_id}/slo-recommendations",
            params={"sli_type": sli_type, "lookback_days": lookback_days},
        )

    def manage_slo(self, service_id: str, payload: dict) -> dict | None:
        return self._request("POST", f"/api/v1/services/{service_id}/slos", json=payload)

    def get_active_slo(self, service_id: str) -> dict | None:
        return self._request("GET", f"/api/v1/services/{service_id}/slos")

    def impact_analysis(self, payload: dict) -> dict | None:
        return self._request("POST", "/api/v1/slos/impact-analysis", json=payload)

    def slo_history(self, service_id: str) -> dict | None:
        return self._request("GET", f"/api/v1/services/{service_id}/slo-history")

    def clear_all_data(self) -> dict | None:
        """Clear all graph data (demo helper - bypasses normal flow)."""
        return self._request("DELETE", "/api/v1/demo/clear-all")


def get_client() -> SloEngineClient:
    return SloEngineClient(st.session_state.base_url, st.session_state.api_key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def json_expander(label: str, data: dict | list | None):
    """Show raw JSON in a collapsed expander."""
    if data is not None:
        with st.expander(label):
            st.json(data)


def check_prereqs(required_steps: list[int], messages: dict[int, str]) -> bool:
    """Return True if all prerequisite steps are completed, else show warnings."""
    ok = True
    for step_num in required_steps:
        key = f"step_{step_num}_completed"
        if not st.session_state.get(key, False):
            st.warning(messages.get(step_num, f"Please complete step {step_num} first."))
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Graph Visualization
# ---------------------------------------------------------------------------


def draw_dependency_graph(nodes: list[dict], edges: list[dict]):
    """Render a NetworkX directed graph with matplotlib."""
    G = nx.DiGraph()

    criticality_colors = {"high": "#e74c3c", "medium": "#f39c12", "low": "#2ecc71"}
    default_color = "#95a5a6"

    for node in nodes:
        sid = node.get("service_id", node.get("id", ""))
        crit = node.get("criticality", node.get("metadata", {}).get("criticality", "medium"))
        G.add_node(sid, criticality=crit)

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        mode = edge.get("communication_mode", edge.get("attributes", {}).get("communication_mode", "sync"))
        crit = edge.get("criticality", edge.get("attributes", {}).get("criticality", "hard"))
        G.add_edge(src, tgt, communication_mode=mode, criticality=crit)

    if len(G.nodes) == 0:
        st.info("No nodes to display.")
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    pos = nx.spring_layout(G, seed=42, k=2.5)

    node_colors = [
        criticality_colors.get(G.nodes[n].get("criticality", "medium"), default_color)
        for n in G.nodes
    ]
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, node_size=1800, alpha=0.9)
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=7, font_weight="bold")

    sync_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("communication_mode") == "sync"]
    async_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("communication_mode") == "async"]
    hard_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("criticality") == "hard"]
    soft_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("criticality") != "hard"]

    nx.draw_networkx_edges(
        G, pos, edgelist=[e for e in sync_edges if e in hard_edges],
        ax=ax, style="solid", edge_color="#2c3e50", arrows=True,
        arrowsize=15, connectionstyle="arc3,rad=0.1", width=2,
    )
    nx.draw_networkx_edges(
        G, pos, edgelist=[e for e in sync_edges if e in soft_edges],
        ax=ax, style="solid", edge_color="#bdc3c7", arrows=True,
        arrowsize=15, connectionstyle="arc3,rad=0.1", width=1.5,
    )
    nx.draw_networkx_edges(
        G, pos, edgelist=[e for e in async_edges if e in hard_edges],
        ax=ax, style="dashed", edge_color="#2c3e50", arrows=True,
        arrowsize=15, connectionstyle="arc3,rad=0.1", width=2,
    )
    nx.draw_networkx_edges(
        G, pos, edgelist=[e for e in async_edges if e in soft_edges],
        ax=ax, style="dashed", edge_color="#bdc3c7", arrows=True,
        arrowsize=15, connectionstyle="arc3,rad=0.1", width=1.5,
    )

    legend_handles = [
        mpatches.Patch(color="#e74c3c", label="High criticality"),
        mpatches.Patch(color="#f39c12", label="Medium criticality"),
        mpatches.Patch(color="#2ecc71", label="Low criticality"),
        plt.Line2D([0], [0], color="#2c3e50", linewidth=2, label="Sync / Hard"),
        plt.Line2D([0], [0], color="#bdc3c7", linewidth=1.5, linestyle="--", label="Async / Soft"),
    ]
    ax.legend(handles=legend_handles, loc="upper left", fontsize=8)
    ax.set_title("Service Dependency Graph", fontsize=12, fontweight="bold")
    ax.axis("off")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def render_step_1():
    st.header("Step 1: Ingest Dependency Graph")
    st.caption("POST /api/v1/demo/dependencies (demo endpoint with immediate circular detection)")
    render_step_concepts(1)

    # Initialize demo_data_loaded flag if not present
    if "demo_data_loaded" not in st.session_state:
        st.session_state.demo_data_loaded = False

    # Controls row
    source = st.selectbox("Discovery source", ["otel_service_graph", "manual", "kubernetes", "service_mesh", "demo_with_issues"])

    col_load, col_clear = st.columns([1, 1])
    with col_load:
        if st.button("Load Demo Data", type="secondary"):
            # Load data based on selected source
            demo_data = DEMO_DATA_BY_SOURCE.get(source, DEMO_DATA_BY_SOURCE["manual"])

            # Extract all metadata fields dynamically from the first node
            if demo_data["nodes"]:
                first_node_metadata = demo_data["nodes"][0]["metadata"]
                node_columns = ["service_id"] + list(first_node_metadata.keys())

                st.session_state.step1_nodes_df = pd.DataFrame([
                    {"service_id": n["service_id"], **n["metadata"]}
                    for n in demo_data["nodes"]
                ])
            else:
                st.session_state.step1_nodes_df = pd.DataFrame()

            # Extract all edge attributes dynamically
            if demo_data["edges"]:
                first_edge_attrs = demo_data["edges"][0]["attributes"]
                edge_columns = ["source", "target"] + list(first_edge_attrs.keys())

                st.session_state.step1_edges_df = pd.DataFrame([
                    {"source": e["source"], "target": e["target"], **e["attributes"]}
                    for e in demo_data["edges"]
                ])
            else:
                st.session_state.step1_edges_df = pd.DataFrame()

            st.session_state.demo_data_loaded = True
            st.rerun()

    with col_clear:
        if st.button("🗑️ Clear All Data", type="secondary", help="Clear all services, edges, and alerts from database"):
            client = get_client()
            with st.spinner("Clearing all data..."):
                resp = client.clear_all_data()
            if resp:
                st.success("All data cleared!")
                # Reset session state
                st.session_state.demo_data_loaded = False
                st.session_state.step_1_completed = False
                if "ingested_services" in st.session_state:
                    del st.session_state["ingested_services"]
                st.rerun()
            else:
                st.warning("Clear endpoint not available (requires backend implementation)")

    st.divider()

    # Only show tables if demo data has been loaded
    if not st.session_state.demo_data_loaded:
        st.info("📝 Select a discovery source above and click 'Load Demo Data' to populate the tables with example services and dependencies")
        nodes_df = None
        edges_df = None
    else:
        st.subheader("Nodes")
        nodes_df = st.data_editor(
            st.session_state.step1_nodes_df,
            num_rows="dynamic",
            column_config={
                "criticality": st.column_config.SelectboxColumn(options=["high", "medium", "low"]),
            },
            key="nodes_editor",
        )

        st.subheader("Edges")
        edges_df = st.data_editor(
            st.session_state.step1_edges_df,
            num_rows="dynamic",
            column_config={
                "communication_mode": st.column_config.SelectboxColumn(options=["sync", "async"]),
                "criticality": st.column_config.SelectboxColumn(options=["hard", "soft", "degraded"]),
            },
            key="edges_editor",
        )

        st.divider()

    if st.button("Ingest Graph", type="primary", disabled=not st.session_state.demo_data_loaded):
        # Build nodes with all metadata fields (excluding service_id)
        nodes_payload = []
        for _, row in nodes_df.iterrows():
            metadata = {k: v for k, v in row.items() if k != "service_id"}
            nodes_payload.append({
                "service_id": row["service_id"],
                "metadata": metadata
            })

        # Build edges with all attribute fields (excluding source and target)
        edges_payload = []
        for _, row in edges_df.iterrows():
            attributes = {k: v for k, v in row.items() if k not in ["source", "target"]}
            edges_payload.append({
                "source": row["source"],
                "target": row["target"],
                "attributes": attributes
            })

        # Map demo_with_issues to manual source for backend compatibility
        backend_source = "manual" if source == "demo_with_issues" else source

        payload = {
            "source": backend_source,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "nodes": nodes_payload,
            "edges": edges_payload,
        }
        client = get_client()
        with st.spinner("Ingesting dependency graph..."):
            resp = client.ingest_dependencies(payload)

        if resp:
            st.session_state.step_1_completed = True
            st.session_state.step_1_response = resp
            services = list({n["service_id"] for _, n in nodes_df.iterrows()})
            services.sort()
            st.session_state.ingested_services = services

            st.success("Graph ingested successfully!")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Nodes Upserted", resp.get("nodes_upserted", 0))
            c2.metric("Edges Upserted", resp.get("edges_upserted", 0))
            circ = resp.get("circular_dependencies_detected", [])
            c3.metric("Circular Deps", len(circ))
            conflicts = resp.get("conflicts_resolved", [])
            c4.metric("Conflicts Resolved", len(conflicts))

            # Display warnings
            for w in resp.get("warnings", []):
                st.warning(w)

            # Display circular dependencies
            for cd in circ:
                st.warning(f"⚠️ Circular dependency: {' -> '.join(cd.get('cycle_path', []))}")

            if circ:
                render_circular_dep_concepts()

            # Display conflicts
            if conflicts:
                with st.expander(f"🔀 {len(conflicts)} Edge Conflict(s) Resolved", expanded=len(conflicts) > 0):
                    for conflict in conflicts:
                        edge_str = f"{conflict.get('edge', 'unknown')}"
                        st.info(
                            f"**Edge:** {edge_str}\n\n"
                            f"**Existing source:** {conflict.get('existing_source', 'N/A')}\n\n"
                            f"**New source:** {conflict.get('new_source', 'N/A')}\n\n"
                            f"**Resolution:** {conflict.get('resolution', 'N/A')}"
                        )

            json_expander("Raw JSON Response", resp)


def render_step_2():
    st.header("Step 2: Query Dependency Subgraph")
    st.caption("GET /api/v1/services/{service_id}/dependencies")
    render_step_concepts(2)

    if not check_prereqs([1], {1: "Please complete Step 1 (Ingest Graph) first."}):
        return

    services = st.session_state.get("ingested_services", [])
    default_idx = services.index("api-gateway") if "api-gateway" in services else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        service_id = st.selectbox("Service", services, index=default_idx, key="step2_svc")
    with col2:
        direction = st.selectbox("Direction", ["downstream", "upstream", "both"], key="step2_dir")
    with col3:
        depth = st.slider("Max depth", 1, 10, 3, key="step2_depth")

    if st.button("Query Subgraph", type="primary"):
        client = get_client()
        with st.spinner("Querying subgraph..."):
            resp = client.query_subgraph(service_id, direction, depth)

        if resp:
            st.session_state.step_2_completed = True
            st.session_state.step_2_response = resp

            stats = resp.get("statistics", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Nodes", stats.get("total_nodes", len(resp.get("nodes", []))))
            c2.metric("Total Edges", stats.get("total_edges", len(resp.get("edges", []))))
            c3.metric("Upstream", stats.get("upstream_services", 0))
            c4.metric("Downstream", stats.get("downstream_services", 0))

            draw_dependency_graph(resp.get("nodes", []), resp.get("edges", []))

            tab_nodes, tab_edges = st.tabs(["Nodes", "Edges"])
            with tab_nodes:
                if resp.get("nodes"):
                    st.dataframe(pd.DataFrame(resp["nodes"]), use_container_width=True)
            with tab_edges:
                if resp.get("edges"):
                    st.dataframe(pd.DataFrame(resp["edges"]), use_container_width=True)

            json_expander("Raw JSON Response", resp)


def _render_tier_card(tier_data: dict, sli_type: str):
    """Render a single tier card within a column."""
    level = tier_data.get("level", "?")
    target = tier_data.get("target", "?")
    breach = tier_data.get("estimated_breach_probability", 0)
    ci = tier_data.get("confidence_interval")

    if breach < 0.05:
        color = "green"
    elif breach < 0.15:
        color = "orange"
    else:
        color = "red"

    if sli_type == "availability":
        st.metric(f"{level.title()}", f"{target}%")
        budget = tier_data.get("error_budget_monthly_minutes")
        if budget is not None:
            st.caption(f"Error budget: {budget:.1f} min/month")
    else:
        target_ms = tier_data.get("target_ms", target)
        percentile = tier_data.get("percentile", "p99")
        st.metric(f"{level.title()}", f"{target_ms} ms")
        st.caption(f"Percentile: {percentile}")

    st.caption(f"Breach prob: :{color}[{breach:.0%}]")
    if ci:
        st.caption(f"CI: [{ci[0]}, {ci[1]}]")


def _render_cold_start_simulation(resp: dict):
    """Render an interactive simulation of the cold-start → mature SLO timeline."""
    st.subheader("Cold Start & SLO Timeline Simulation")
    st.caption(
        "Drag the slider to experience the full maturity journey. "
        "Day 0 uses dependency data only; later days blend in telemetry."
    )

    recommendations = resp.get("recommendations", [])
    if not recommendations:
        st.info("No recommendations available to anchor simulation.")
        return

    # --- Extract anchor values from real API response ---
    avail_rec = next((r for r in recommendations if r.get("sli_type") == "availability"), None)
    if avail_rec is None:
        avail_rec = recommendations[0]

    real_dq = avail_rec.get("data_quality", {})
    real_completeness = real_dq.get("data_completeness", 0.9)

    dep_impact = avail_rec.get("explanation", {}).get("dependency_impact") or {}
    composite_bound = dep_impact.get("composite_availability_bound", 99.9)
    bottleneck_service = dep_impact.get("bottleneck_service", "N/A")
    hard_dep_count = dep_impact.get("hard_dependency_count", "N/A")

    real_tiers = avail_rec.get("tiers", {})

    # --- Slider ---
    sim_day = st.slider("Service age (days since deploy)", 0, 45, 0, key="step3_sim_day")

    # --- Phase classification ---
    if sim_day == 0:
        phase = "Pre-Deploy"
        phase_color = "blue"
        phase_desc = "No telemetry yet. Ceiling derived from dependency graph alone."
    elif sim_day <= 7:
        phase = "Cold Start"
        phase_color = "orange"
        phase_desc = "Sparse telemetry. Wide confidence intervals. Conservative targets only."
    elif sim_day <= 30:
        phase = "Warming"
        phase_color = "yellow"
        phase_desc = "Baseline building. Confidence improving. Targets stabilising."
    else:
        phase = "Mature"
        phase_color = "green"
        phase_desc = "Stable baseline. Values match the live recommendation above."

    # --- Confidence interpolation ---
    if sim_day == 0:
        sim_confidence = 0.25
    elif sim_day <= 7:
        sim_confidence = 0.30 + (sim_day - 1) / 6 * (0.60 - 0.30)
    elif sim_day <= 30:
        sim_confidence = 0.60 + (sim_day - 8) / 22 * (real_completeness - 0.60)
    else:
        sim_confidence = real_completeness

    # --- Phase banner + confidence metric ---
    banner_col, metric_col = st.columns([3, 1])
    with banner_col:
        st.markdown(f"**Phase:** :{phase_color}[{phase}]")
        st.caption(phase_desc)
    with metric_col:
        st.metric("Confidence Score", f"{sim_confidence:.0%}")

    # --- Progress bar ---
    st.progress(min(sim_confidence, 1.0), text=f"Data completeness: {sim_confidence:.0%}")

    # --- Contextual inline message ---
    if phase == "Cold Start":
        st.warning("Wide confidence intervals: the system plays safe with lower targets until more data arrives.")
    elif phase == "Warming":
        st.info("Confidence intervals narrowing as baseline accumulates. Targets trending toward mature values.")
    elif phase == "Mature":
        st.success("Mature baseline reached. Values match actual recommendation above.")

    # --- Main panel ---
    if sim_day == 0:
        st.info("Pre-deployment mode: theoretical SLO ceiling from dependency data only.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Theoretical SLO Ceiling", f"{composite_bound}%")
        c2.metric("Ceiling Set By", str(bottleneck_service))
        c3.metric("Hard Dependencies", str(hard_dep_count))
        st.caption("Even perfect service code cannot exceed this ceiling.")
    else:
        # Synthesize simulated tier cards from real mature tiers
        # CI half-width shrinks from 8x (day 1) → 1x (day 31+)
        if sim_day <= 7:
            ci_factor = 8.0 - (sim_day - 1) / 6 * (8.0 - 3.0)   # 8x → 3x
            target_penalty = 0.05
        elif sim_day <= 30:
            ci_factor = 3.0 - (sim_day - 8) / 22 * (3.0 - 1.0)   # 3x → 1x
            target_penalty = 0.05 * (1 - (sim_day - 8) / 22)      # fades out
        else:
            ci_factor = 1.0
            target_penalty = 0.0

        tier_cols = st.columns(3)
        for i, tier_name in enumerate(["conservative", "balanced", "aggressive"]):
            real_tier = real_tiers.get(tier_name)
            if not real_tier:
                continue
            real_target = real_tier.get("target", 99.0)
            real_ci = real_tier.get("confidence_interval") or [real_target - 0.1, real_target + 0.1]
            real_breach = real_tier.get("estimated_breach_probability", 0.05)
            real_budget = real_tier.get("error_budget_monthly_minutes")

            sim_target = round(real_target - target_penalty, 3)
            ci_half = (real_ci[1] - real_ci[0]) / 2 * ci_factor
            sim_ci = [
                round(max(sim_target - ci_half, 0), 3),
                round(min(sim_target + ci_half, 100), 3),
            ]
            breach_scale = 1 + (ci_factor - 1) * 0.5
            sim_breach = min(real_breach * breach_scale, 0.95)
            sim_budget = round(real_budget * (sim_target / real_target), 1) if real_budget else None

            sim_tier_data = {
                "level": tier_name,
                "target": sim_target,
                "confidence_interval": sim_ci,
                "estimated_breach_probability": sim_breach,
                "error_budget_monthly_minutes": sim_budget,
            }
            with tier_cols[i]:
                _render_tier_card(sim_tier_data, "availability")

    # --- Phase timeline strip ---
    st.markdown("---")
    phases_meta = [
        ("Pre-Deploy", "blue",   "Day 0"),
        ("Cold Start", "orange", "Day 1-7"),
        ("Warming",    "yellow", "Day 8-30"),
        ("Mature",     "green",  "Day 31+"),
    ]
    timeline_cols = st.columns(4)
    for col, (p_name, p_color, p_range) in zip(timeline_cols, phases_meta):
        with col:
            active = p_name == phase
            label = f"**:{p_color}[{p_name}]**" if active else f":{p_color}[{p_name}]"
            st.markdown(label)
            st.caption(p_range)
            if active:
                st.caption("↑ You are here")


def render_step_3():
    st.header("Step 3: SLO Recommendations")
    st.caption("GET /api/v1/services/{service_id}/slo-recommendations")
    render_step_concepts(3)

    if not check_prereqs([1], {1: "Please complete Step 1 (Ingest Graph) first."}):
        return

    services = st.session_state.get("ingested_services", [])
    default_idx = services.index("payment-service") if "payment-service" in services else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        service_id = st.selectbox("Service", services, index=default_idx, key="step3_svc")
    with col2:
        sli_type = st.selectbox("SLI Type", ["all", "availability", "latency"], key="step3_sli")
    with col3:
        lookback = st.slider("Lookback days", 7, 365, 30, key="step3_lookback")

    if st.button("Get Recommendations", type="primary"):
        client = get_client()
        with st.spinner("Generating recommendations..."):
            resp = client.get_recommendations(service_id, sli_type, lookback)
        if resp:
            st.session_state.step_3_completed = True
            st.session_state.step_3_response = resp

    resp = st.session_state.get("step_3_response")
    if resp:
        for rec in resp.get("recommendations", []):
            rec_sli = rec.get("sli_type", "unknown")
            st.subheader(f"{rec_sli.title()} Recommendation")

            tiers = rec.get("tiers", {})
            tier_cols = st.columns(3)
            for i, tier_name in enumerate(["conservative", "balanced", "aggressive"]):
                tier_data = tiers.get(tier_name, {})
                if tier_data:
                    with tier_cols[i]:
                        _render_tier_card(tier_data, rec_sli)

            explanation = rec.get("explanation", {})
            if explanation:
                with st.expander("Explanation"):
                    st.write(explanation.get("summary", ""))

                    attrs = explanation.get("feature_attribution", [])
                    if attrs:
                        st.caption("Feature Attribution")
                        st.caption(
                            "**How this is calculated (current):** Each feature is assigned a "
                            "domain-expert weight (e.g. historical availability 40%, dependency risk 30%). "
                            "The feature's measured value is multiplied by its weight, then all contributions "
                            "are normalised to sum to 100%. This is a weighted linear decomposition — "
                            "deterministic and auditable, not learned from data. "
                            "**Future (SHAP-based):** An ML model would be trained on historical SLO outcomes. "
                            "SHAP values would then attribute each prediction to individual features by computing "
                            "their marginal contribution across all possible feature orderings, giving a "
                            "model-faithful explanation rather than a hand-tuned weight."
                        )
                        for attr in attrs:
                            feat = attr.get("feature", "")
                            contrib = attr.get("contribution", 0)
                            desc = attr.get("description", "")
                            st.progress(min(contrib, 1.0), text=f"{feat}: {contrib:.0%} - {desc}")

                    dep_impact = explanation.get("dependency_impact")
                    if dep_impact:
                        st.caption("Dependency Impact")
                        di1, di2 = st.columns(2)
                        di1.metric("Composite Bound", f"{dep_impact.get('composite_availability_bound', 'N/A')}%")
                        bottleneck = dep_impact.get("bottleneck_service", "None")
                        di2.metric("Bottleneck", bottleneck)

                counterfactuals = explanation.get("counterfactuals", [])
                if counterfactuals:
                    with st.expander("Counterfactual Explanations"):
                        st.info("What-if scenarios showing how changes affect recommendations")
                        for cf in counterfactuals:
                            condition = cf.get("condition", "")
                            condition = condition[3:] if condition.lower().startswith("if ") else condition
                            st.markdown(f"**If** {condition}")
                            st.markdown(f"**Then** {cf.get('result', '')}")
                            st.divider()

                provenance = explanation.get("provenance")
                if provenance:
                    with st.expander("Data Provenance"):
                        prov_df = pd.DataFrame([
                            {"Field": k, "Value": str(v)}
                            for k, v in provenance.items()
                        ])
                        st.dataframe(prov_df, use_container_width=True, hide_index=True)

            dq = rec.get("data_quality", {})
            if dq and dq.get("is_cold_start"):
                lookback_actual = dq.get("lookback_days_actual", "?")
                note = dq.get("confidence_note", "")
                warning_text = (
                    f"Cold Start Detected: Only {lookback_actual} days of telemetry available. "
                    "See the simulation below for the full maturity timeline."
                )
                if note:
                    warning_text += f" {note}"
                st.warning(warning_text)

            st.divider()

        _render_cold_start_simulation(resp)

        st.divider()
        json_expander("Raw JSON Response", resp)


_TIER_RATIONALE = {
    "conservative": "Conservative tier chosen to minimise risk during rollout; aligns with SRE sign-off requirements.",
    "balanced": "Balanced tier aligns with team risk tolerance and SRE review.",
    "aggressive": "Aggressive tier approved after load-test results confirmed headroom; accepted by service owner.",
}


def render_step_4():
    st.header("Step 4: Accept SLO Recommendation")
    st.caption("POST /api/v1/services/{service_id}/slos")

    if not check_prereqs([3], {3: "Please complete Step 3 (Get Recommendations) first."}):
        return

    services = st.session_state.get("ingested_services", [])
    default_idx = services.index("payment-service") if "payment-service" in services else 0

    service_id = st.selectbox("Service", services, index=default_idx, key="step4_svc")
    tier = st.selectbox("Tier", ["conservative", "balanced", "aggressive"], index=1, key="step4_tier")
    rationale = st.text_area("Rationale", _TIER_RATIONALE[tier], key="step4_rationale")
    actor = st.text_input("Actor email", "jane.doe@company.com", key="step4_actor")

    # Derive downstream services from the ingested edge list
    edges_df = st.session_state.get("step1_edges_df")
    if edges_df is not None and not edges_df.empty and service_id:
        downstream = edges_df.loc[edges_df["source"] == service_id, "target"].tolist()
    else:
        downstream = []

    also_accept = st.multiselect(
        "Also accept for downstream services",
        options=[s for s in services if s != service_id],
        default=[s for s in downstream if s in services],
        key="step4_also_accept",
    )

    if st.button("Accept SLO", type="primary"):
        client = get_client()

        payload = {
            "action": "accept",
            "selected_tier": tier,
            "rationale": rationale,
            "actor": actor,
        }
        with st.spinner(f"Accepting SLO for {service_id}..."):
            resp = client.manage_slo(service_id, payload)

        if resp:
            st.session_state.step_4_completed = True
            st.session_state.step_4_response = resp
            st.session_state.setdefault("services_with_slos", [])
            if service_id not in st.session_state.services_with_slos:
                st.session_state.services_with_slos.append(service_id)

            st.success(resp.get("message", "SLO accepted!"))
            active = resp.get("active_slo", {})
            if active:
                c1, c2, c3 = st.columns(3)
                c1.metric("Availability", f"{active.get('availability_target', 'N/A')}%")
                latency = active.get("latency_p99_target_ms")
                c2.metric("Latency P99", f"{latency} ms" if latency else "N/A")
                c3.metric("Tier", active.get("selected_tier", "N/A").title())
                st.caption(f"Activated by {active.get('activated_by')} at {active.get('activated_at')}")

            json_expander("Raw JSON Response", resp)

        for downstream_svc in also_accept:
            downstream_payload = {
                "action": "accept",
                "selected_tier": tier,
                "rationale": f"{_TIER_RATIONALE[tier]} (cascaded from {service_id})",
                "actor": actor,
            }
            with st.spinner(f"Accepting SLO for {downstream_svc}..."):
                resp_ds = client.manage_slo(downstream_svc, downstream_payload)
            if resp_ds:
                if downstream_svc not in st.session_state.services_with_slos:
                    st.session_state.services_with_slos.append(downstream_svc)
                st.success(resp_ds.get("message", f"SLO accepted for {downstream_svc}!"))
                json_expander(f"{downstream_svc} JSON Response", resp_ds)

        # Verify active SLO
        if resp:
            st.subheader("Verify Active SLO")
            with st.spinner("Fetching active SLO..."):
                active_resp = client.get_active_slo(service_id)
            if active_resp:
                st.json(active_resp)


def render_step_5():
    st.header("Step 5: Modify SLO")
    st.caption("POST /api/v1/services/{service_id}/slos (action=modify)")
    render_step_concepts(5)

    if not check_prereqs([4], {4: "Please complete Step 4 (Accept SLO) first."}):
        return

    slo_services = st.session_state.get("services_with_slos", [])
    if not slo_services:
        st.warning("No services have active SLOs yet.")
        return

    default_idx = slo_services.index("payment-service") if "payment-service" in slo_services else 0
    service_id = st.selectbox("Service (with active SLO)", slo_services, index=default_idx, key="step5_svc")

    # Show current SLO
    client = get_client()
    current = client.get_active_slo(service_id)
    if current:
        st.info(
            f"Current SLO: availability={current.get('availability_target', 'N/A')}%, "
            f"latency_p99={current.get('latency_p99_target_ms', 'N/A')} ms, "
            f"tier={current.get('selected_tier', 'N/A')}"
        )

    tier = st.selectbox("Tier", ["conservative", "balanced", "aggressive"], index=1, key="step5_tier")
    new_avail = st.number_input("New availability target (%)", value=99.95, step=0.01, format="%.2f", key="step5_avail")
    new_p99 = st.number_input("New latency P99 target (ms, 0 to skip)", value=0, step=50, key="step5_p99")
    rationale = st.text_area("Rationale", "Tightening after PCI compliance review", key="step5_rationale")
    actor = st.text_input("Actor email", "security-team@company.com", key="step5_actor")

    if st.button("Modify SLO", type="primary"):
        modifications: dict = {"availability_target": new_avail}
        if new_p99 > 0:
            modifications["latency_p99_target_ms"] = int(new_p99)

        payload = {
            "action": "modify",
            "selected_tier": tier,
            "modifications": modifications,
            "rationale": rationale,
            "actor": actor,
        }

        with st.spinner("Modifying SLO..."):
            resp = client.manage_slo(service_id, payload)

        if resp:
            st.session_state.step_5_completed = True
            st.session_state.step_5_response = resp

            st.success(resp.get("message", "SLO modified!"))

            delta = resp.get("modification_delta")
            if delta:
                st.subheader("Modification Delta")
                before_data = {}
                after_data = {}
                for field, diff in delta.items():
                    if current:
                        old_val = current.get(field, "N/A")
                    else:
                        old_val = "N/A"
                    before_data[field] = old_val
                    if old_val != "N/A":
                        after_data[field] = old_val + diff if isinstance(old_val, (int, float)) and isinstance(diff, (int, float)) else "N/A"
                    else:
                        after_data[field] = "N/A"

                delta_df = pd.DataFrame({
                    "Field": list(delta.keys()),
                    "Delta": list(delta.values()),
                })
                st.dataframe(delta_df, use_container_width=True, hide_index=True)

            active = resp.get("active_slo", {})
            if active:
                st.subheader("Updated SLO")
                c1, c2, c3 = st.columns(3)
                c1.metric("Availability", f"{active.get('availability_target', 'N/A')}%")
                latency = active.get("latency_p99_target_ms")
                c2.metric("Latency P99", f"{latency} ms" if latency else "N/A")
                c3.metric("Tier", active.get("selected_tier", "N/A").title())

            json_expander("Raw JSON Response", resp)


def render_step_6():
    st.header("Step 6: Impact Analysis")
    st.caption("POST /api/v1/slos/impact-analysis")
    render_step_concepts(6)

    if not check_prereqs([4], {4: "Please complete Step 4 (Accept SLO) first."}):
        return

    services = st.session_state.get("ingested_services", [])
    default_idx = services.index("payment-service") if "payment-service" in services else 0

    col1, col2 = st.columns(2)
    with col1:
        service_id = st.selectbox("Service", services, index=default_idx, key="step6_svc")
        sli_type = st.selectbox("SLI Type", ["availability", "latency"], key="step6_sli")
    with col2:
        current_target = st.number_input("Current target", value=99.95, step=0.01, format="%.2f", key="step6_current")
        proposed_target = st.number_input("Proposed target", value=99.5, step=0.01, format="%.2f", key="step6_proposed")

    max_depth = st.slider("Max depth", 1, 10, 3, key="step6_depth")

    if st.button("Run Impact Analysis", type="primary"):
        payload = {
            "service_id": service_id,
            "proposed_change": {
                "sli_type": sli_type,
                "current_target": current_target,
                "proposed_target": proposed_target,
            },
            "max_depth": max_depth,
        }

        client = get_client()
        with st.spinner("Running impact analysis..."):
            resp = client.impact_analysis(payload)

        if resp:
            st.session_state.step_6_completed = True
            st.session_state.step_6_response = resp

            summary = resp.get("summary", {})
            total_impacted = summary.get("total_impacted", 0)
            slos_at_risk = summary.get("slos_at_risk", 0)

            c1, c2 = st.columns(2)
            c1.metric("Total Impacted Services", total_impacted)
            c2.metric("SLOs at Risk", slos_at_risk)

            if slos_at_risk > 0:
                st.error(f"WARNING: {slos_at_risk} upstream service(s) at risk of SLO breach!")
            else:
                st.success("No upstream SLOs are at risk from this change.")

            if summary.get("recommendation"):
                st.info(summary["recommendation"])

            for svc in resp.get("impacted_services", []):
                with st.expander(f"{svc.get('service_id', '?')} ({svc.get('relationship', '?')})"):
                    ic1, ic2, ic3 = st.columns(3)
                    ic1.metric("Current Composite", f"{svc.get('current_composite_availability', 'N/A')}%")
                    ic2.metric("Projected Composite", f"{svc.get('projected_composite_availability', 'N/A')}%")
                    delta = svc.get("delta", 0)
                    ic3.metric("Delta", f"{delta:+.2f}%")
                    if svc.get("slo_at_risk"):
                        st.error(svc.get("risk_detail", "SLO at risk"))
                    elif svc.get("current_slo_target"):
                        st.success("SLO remains safe")

            json_expander("Raw JSON Response", resp)


def render_step_7():
    st.header("Step 7: Audit History")
    st.caption("GET /api/v1/services/{service_id}/slo-history")

    if not check_prereqs([4], {4: "Please complete Step 4 (Accept SLO) first."}):
        return

    slo_services = st.session_state.get("services_with_slos", [])
    if not slo_services:
        slo_services = st.session_state.get("ingested_services", [])

    default_idx = slo_services.index("payment-service") if "payment-service" in slo_services else 0
    service_id = st.selectbox("Service", slo_services, index=default_idx, key="step7_svc")

    if st.button("Fetch Audit History", type="primary"):
        client = get_client()
        with st.spinner("Fetching audit history..."):
            resp = client.slo_history(service_id)

        if resp:
            st.session_state.step_7_completed = True
            st.session_state.step_7_response = resp

            total = resp.get("total_count", len(resp.get("entries", [])))
            st.metric("Total Entries", total)

            action_icons = {"accept": "✅", "modify": "✏️", "reject": "❌"}

            for entry in resp.get("entries", []):
                action = entry.get("action", "unknown")
                icon = action_icons.get(action, "📝")
                ts = entry.get("timestamp", "")
                actor = entry.get("actor", "unknown")

                with st.container(border=True):
                    c1, c2, c3 = st.columns([1, 2, 2])
                    c1.markdown(f"### {icon} {action.title()}")
                    c2.caption(f"**Actor:** {actor}")
                    c3.caption(f"**Time:** {ts}")

                    if entry.get("rationale"):
                        st.caption(f"Rationale: {entry['rationale']}")
                    if entry.get("selected_tier"):
                        st.caption(f"Tier: {entry['selected_tier']}")

                    delta = entry.get("modification_delta")
                    if delta:
                        with st.expander("Modification Delta"):
                            st.json(delta)

                    prev = entry.get("previous_slo")
                    new = entry.get("new_slo")
                    if prev or new:
                        with st.expander("SLO Snapshot"):
                            sc1, sc2 = st.columns(2)
                            with sc1:
                                st.caption("Previous")
                                if prev:
                                    st.json(prev)
                                else:
                                    st.caption("None")
                            with sc2:
                                st.caption("New")
                                if new:
                                    st.json(new)
                                else:
                                    st.caption("None")

            json_expander("Raw JSON Response", resp)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def render_sidebar():
    with st.sidebar:
        st.title("SLO Engine Demo")

        st.subheader("Configuration")
        base_url = st.text_input("API Base URL", value=st.session_state.get("base_url", "http://localhost:8000"))
        st.session_state.base_url = base_url
        # No API key needed for demo endpoints
        st.session_state.api_key = ""

        # Connection status
        if st.button("Check Connection", type="secondary"):
            client = get_client()
            health = client.health()
            if health:
                st.success("Connected")
            else:
                st.error("Not connected")

        st.divider()

        st.subheader("Navigation")
        step = st.radio("Step", STEPS, label_visibility="collapsed")

        st.divider()

        if st.button("Reset All", type="secondary"):
            keys_to_clear = [k for k in st.session_state if k.startswith("step_") or k in (
                "ingested_services", "services_with_slos", "step1_nodes_df", "step1_edges_df",
            )]
            for k in keys_to_clear:
                del st.session_state[k]
            st.rerun()

    return step


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    st.set_page_config(
        page_title="SLO Recommendation Engine Demo",
        page_icon="🎯",
        layout="wide",
    )

    step = render_sidebar()

    st.title("SLO Recommendation Engine")

    st.divider()

    # Dispatch to selected step
    step_idx = STEPS.index(step) + 1 if step in STEPS else 1
    step_renderers = {
        1: render_step_1,
        2: render_step_2,
        3: render_step_3,
        4: render_step_4,
        5: render_step_5,
        6: render_step_6,
        7: render_step_7,
        8: render_reference_page,
    }
    step_renderers[step_idx]()


if __name__ == "__main__":
    main()
