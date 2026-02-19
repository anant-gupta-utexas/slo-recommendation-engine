"""
SLO Recommendation Engine - Interactive Streamlit Demo
Walks through FR-1 through FR-7 with visual UI, editable inputs, and formatted results.

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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEPS = [
    "1. Ingest Dependency Graph (FR-1)",
    "2. Query Subgraph (FR-1)",
    "3. SLO Recommendations (FR-2 + FR-7)",
    "4. Accept SLO (FR-5)",
    "5. Modify SLO (FR-5)",
    "6. Impact Analysis (FR-4)",
    "7. Audit History (FR-5)",
]

DEMO_NODES = [
    {"service_id": "api-gateway", "metadata": {"team": "platform", "criticality": "high"}},
    {"service_id": "checkout-service", "metadata": {"team": "commerce", "criticality": "high"}},
    {"service_id": "user-service", "metadata": {"team": "identity", "criticality": "high"}},
    {"service_id": "payment-service", "metadata": {"team": "payments", "criticality": "high"}},
    {"service_id": "inventory-service", "metadata": {"team": "commerce", "criticality": "medium"}},
    {"service_id": "auth-service", "metadata": {"team": "identity", "criticality": "high"}},
    {"service_id": "notification-service", "metadata": {"team": "platform", "criticality": "low"}},
    {"service_id": "analytics-service", "metadata": {"team": "data", "criticality": "low"}},
]

DEMO_EDGES = [
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
]

# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


class SloEngineClient:
    """Thin wrapper around the SLO Engine REST API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })

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
        return self._request("POST", "/api/v1/services/dependencies", json=payload)

    def query_subgraph(self, service_id: str, direction: str, depth: int) -> dict | None:
        return self._request(
            "GET",
            f"/api/v1/services/{service_id}/dependencies",
            params={"direction": direction, "depth": depth},
        )

    def get_recommendations(self, service_id: str, sli_type: str, lookback_days: int) -> dict | None:
        return self._request(
            "GET",
            f"/api/v1/services/{service_id}/slo-recommendations",
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


def _draw_feature_flow():
    """Render the feature flow diagram using matplotlib."""
    fig, ax = plt.subplots(figsize=(10, 3))

    boxes = {
        "FR-1\nDependency\nGraph":     (0.08, 0.5),
        "FR-2\nRecommend-\nations":     (0.30, 0.7),
        "FR-7\nExplain-\nability":      (0.30, 0.25),
        "FR-5\nAccept /\nModify":       (0.52, 0.7),
        "FR-4\nImpact\nAnalysis":       (0.52, 0.25),
        "Audit\nHistory":               (0.74, 0.5),
    }
    colors = {
        "FR-1\nDependency\nGraph":  "#3498db",
        "FR-2\nRecommend-\nations":  "#2ecc71",
        "FR-7\nExplain-\nability":   "#9b59b6",
        "FR-5\nAccept /\nModify":    "#e67e22",
        "FR-4\nImpact\nAnalysis":    "#e74c3c",
        "Audit\nHistory":            "#1abc9c",
    }

    for label, (x, y) in boxes.items():
        color = colors[label]
        bbox = dict(boxstyle="round,pad=0.4", facecolor=color, edgecolor="white", alpha=0.9)
        ax.text(x, y, label, ha="center", va="center", fontsize=8, fontweight="bold",
                color="white", bbox=bbox, transform=ax.transAxes)

    arrows = [
        ("FR-1\nDependency\nGraph", "FR-2\nRecommend-\nations"),
        ("FR-1\nDependency\nGraph", "FR-4\nImpact\nAnalysis"),
        ("FR-2\nRecommend-\nations", "FR-5\nAccept /\nModify"),
        ("FR-2\nRecommend-\nations", "FR-7\nExplain-\nability"),
        ("FR-5\nAccept /\nModify", "FR-4\nImpact\nAnalysis"),
        ("FR-5\nAccept /\nModify", "Audit\nHistory"),
    ]

    for src, tgt in arrows:
        sx, sy = boxes[src]
        tx, ty = boxes[tgt]
        ax.annotate("", xy=(tx, ty), xytext=(sx, sy),
                     xycoords="axes fraction", textcoords="axes fraction",
                     arrowprops=dict(arrowstyle="->", color="#ecf0f1", lw=1.5,
                                     connectionstyle="arc3,rad=0.1"))

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


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
    st.header("Step 1: Ingest Dependency Graph (FR-1)")
    st.caption("POST /api/v1/services/dependencies")

    if "step1_nodes_df" not in st.session_state:
        st.session_state.step1_nodes_df = pd.DataFrame([
            {"service_id": n["service_id"], "team": n["metadata"]["team"], "criticality": n["metadata"]["criticality"]}
            for n in DEMO_NODES
        ])
    if "step1_edges_df" not in st.session_state:
        st.session_state.step1_edges_df = pd.DataFrame([
            {"source": e["source"], "target": e["target"],
             "communication_mode": e["attributes"]["communication_mode"],
             "criticality": e["attributes"]["criticality"]}
            for e in DEMO_EDGES
        ])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Load Demo Data", type="secondary"):
            st.session_state.step1_nodes_df = pd.DataFrame([
                {"service_id": n["service_id"], "team": n["metadata"]["team"], "criticality": n["metadata"]["criticality"]}
                for n in DEMO_NODES
            ])
            st.session_state.step1_edges_df = pd.DataFrame([
                {"source": e["source"], "target": e["target"],
                 "communication_mode": e["attributes"]["communication_mode"],
                 "criticality": e["attributes"]["criticality"]}
                for e in DEMO_EDGES
            ])
            st.rerun()
    with col2:
        source = st.selectbox("Discovery source", ["otel_service_graph", "manual", "kubernetes", "service_mesh"])

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

    if st.button("Ingest Graph", type="primary"):
        payload = {
            "source": source,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "nodes": [
                {"service_id": row["service_id"], "metadata": {"team": row.get("team", ""), "criticality": row.get("criticality", "medium")}}
                for _, row in nodes_df.iterrows()
            ],
            "edges": [
                {"source": row["source"], "target": row["target"],
                 "attributes": {"communication_mode": row.get("communication_mode", "sync"),
                                "criticality": row.get("criticality", "hard")}}
                for _, row in edges_df.iterrows()
            ],
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
            c1, c2, c3 = st.columns(3)
            c1.metric("Nodes Upserted", resp.get("nodes_upserted", 0))
            c2.metric("Edges Upserted", resp.get("edges_upserted", 0))
            circ = resp.get("circular_dependencies_detected", [])
            c3.metric("Circular Deps", len(circ))

            for w in resp.get("warnings", []):
                st.warning(w)
            for cd in circ:
                st.warning(f"Circular dependency: {' -> '.join(cd.get('cycle_path', []))}")

            json_expander("Raw JSON Response", resp)


def render_step_2():
    st.header("Step 2: Query Dependency Subgraph (FR-1)")
    st.caption("GET /api/v1/services/{service_id}/dependencies")

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


def render_step_3():
    st.header("Step 3: SLO Recommendations (FR-2 + FR-7)")
    st.caption("GET /api/v1/services/{service_id}/slo-recommendations")

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
                        with st.expander("FR-7: Counterfactual Explanations"):
                            st.info("What-if scenarios showing how changes affect recommendations")
                            for cf in counterfactuals:
                                st.markdown(f"**If** {cf.get('condition', '')}")
                                st.markdown(f"**Then** {cf.get('result', '')}")
                                st.divider()

                    provenance = explanation.get("provenance")
                    if provenance:
                        with st.expander("FR-7: Data Provenance"):
                            prov_df = pd.DataFrame([
                                {"Field": k, "Value": str(v)}
                                for k, v in provenance.items()
                            ])
                            st.dataframe(prov_df, use_container_width=True, hide_index=True)

                dq = rec.get("data_quality", {})
                if dq:
                    with st.expander("Data Quality"):
                        completeness = dq.get("data_completeness", 0)
                        st.progress(min(completeness, 1.0), text=f"Completeness: {completeness:.0%}")
                        if dq.get("confidence_note"):
                            st.caption(dq["confidence_note"])
                        if dq.get("is_cold_start"):
                            st.warning("Cold start: limited historical data available.")

                st.divider()

            json_expander("Raw JSON Response", resp)


def render_step_4():
    st.header("Step 4: Accept SLO Recommendation (FR-5)")
    st.caption("POST /api/v1/services/{service_id}/slos")

    if not check_prereqs([3], {3: "Please complete Step 3 (Get Recommendations) first."}):
        return

    services = st.session_state.get("ingested_services", [])
    default_idx = services.index("payment-service") if "payment-service" in services else 0

    service_id = st.selectbox("Service", services, index=default_idx, key="step4_svc")
    tier = st.selectbox("Tier", ["conservative", "balanced", "aggressive"], index=1, key="step4_tier")
    rationale = st.text_area("Rationale", "Balanced tier aligns with team risk tolerance and SRE review", key="step4_rationale")
    actor = st.text_input("Actor email", "jane.doe@company.com", key="step4_actor")

    accept_second = st.checkbox("Also accept for checkout-service", value=True, key="step4_also_checkout")

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

        if accept_second and "checkout-service" in services:
            payload2 = {
                "action": "accept",
                "selected_tier": "balanced",
                "rationale": "Standard balanced target for checkout flow",
                "actor": "john.smith@company.com",
            }
            with st.spinner("Accepting SLO for checkout-service..."):
                resp2 = client.manage_slo("checkout-service", payload2)
            if resp2:
                if "checkout-service" not in st.session_state.services_with_slos:
                    st.session_state.services_with_slos.append("checkout-service")
                st.success(resp2.get("message", "SLO accepted for checkout-service!"))
                json_expander("checkout-service JSON Response", resp2)

        # Verify active SLO
        if resp:
            st.subheader("Verify Active SLO")
            with st.spinner("Fetching active SLO..."):
                active_resp = client.get_active_slo(service_id)
            if active_resp:
                st.json(active_resp)


def render_step_5():
    st.header("Step 5: Modify SLO (FR-5)")
    st.caption("POST /api/v1/services/{service_id}/slos (action=modify)")

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
    st.header("Step 6: Impact Analysis (FR-4)")
    st.caption("POST /api/v1/slos/impact-analysis")

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
    st.header("Step 7: Audit History (FR-5)")
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
        api_key = st.text_input("API Key", value=st.session_state.get("api_key", "demo-api-key-for-testing"), type="password")
        st.session_state.base_url = base_url
        st.session_state.api_key = api_key

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

        st.subheader("Progress")
        for i, s in enumerate(STEPS, 1):
            completed = st.session_state.get(f"step_{i}_completed", False)
            icon = "✅" if completed else "⬜"
            st.caption(f"{icon} {s}")

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

    # Header with feature flow
    st.title("SLO Recommendation Engine")
    st.caption("Interactive demo walking through FR-1 through FR-7")

    with st.expander("Feature Flow Diagram", expanded=False):
        _draw_feature_flow()

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
    }
    step_renderers[step_idx]()


if __name__ == "__main__":
    main()
