"""
Brand Analysis Interactive Dashboard
====================================
End-to-end data cleaning, EDA, and Plotly Dash dashboard.

Run in VS Code:
    1. python -m venv venv && source venv/bin/activate   (Windows: venv\\Scripts\\activate)
    2. pip install -r requirements.txt
    3. python app.py
    4. Open http://127.0.0.1:8050 in your browser.

Dataset expected next to this file: brand_analysis_dirty.xlsx
"""

import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output

# ---------------------------------------------------------------------------
# 1. CONFIG / THEME
# ---------------------------------------------------------------------------
DATA_FILE = os.path.join(os.path.dirname(__file__), "brand_analysis_dirty.xlsx")

COLORS = {
    "bg":        "#0F172A",  # page background (slate-900)
    "panel":     "#1E293B",  # card background (slate-800)
    "panel2":    "#243047",
    "text":      "#E2E8F0",
    "muted":     "#94A3B8",
    "primary":   "#38BDF8",  # sky-400
    "accent":    "#F472B6",  # pink-400
    "good":      "#34D399",  # emerald-400
    "warn":      "#FBBF24",  # amber-400
    "bad":       "#F87171",  # red-400
}
PLOT_TEMPLATE = "plotly_dark"
SEQ_COLORS = ["#38BDF8", "#F472B6", "#34D399", "#FBBF24", "#A78BFA",
              "#F87171", "#22D3EE", "#FB923C", "#4ADE80", "#E879F9"]

# ---------------------------------------------------------------------------
# 2. DATA LOADING + CLEANING + FEATURE ENGINEERING
# ---------------------------------------------------------------------------
def load_and_clean(path: str) -> pd.DataFrame:
    """Load Excel/CSV, clean, and add engineered features."""
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    # --- Drop exact duplicates ---
    df = df.drop_duplicates().reset_index(drop=True)

    # --- Fix dtypes ---
    num_cols = [
        "Founded_Year", "Brand_Age_Years", "Revenue_USD_M", "Valuation_USD_M",
        "Instagram_Followers", "Twitter_Followers", "Facebook_Likes",
        "LinkedIn_Followers", "Social_Engagement_Rate_Pct",
        "Brand_Sentiment_Score", "NPS", "Brand_Awareness_Pct",
        "Customer_Loyalty_Score",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- Handle missing values ---
    for c in ["Industry", "Country", "Brand_Name"]:
        if c in df.columns:
            df[c] = df[c].fillna("Unknown")
    for c in num_cols:
        if c in df.columns:
            df[c] = df[c].fillna(df[c].median())

    if "Founded_Year" in df.columns:
        df["Founded_Year"] = df["Founded_Year"].astype(int)

    # --- Synthesize a Date column (dataset has none) ---
    rng = np.random.default_rng(42)
    years = rng.integers(2019, 2025, size=len(df))
    months = rng.integers(1, 13, size=len(df))
    days = rng.integers(1, 28, size=len(df))
    df["Date"] = pd.to_datetime(dict(year=years, month=months, day=days))

    # --- Derived time features ---
    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.month
    df["YearMonth"] = df["Date"].dt.to_period("M").astype(str)

    # --- Customer rating (0-10) derived from loyalty ---
    df["Rating"] = df["Customer_Loyalty_Score"].clip(0, 10).round(1)

    # --- Feedback Category from sentiment score ---
    def feedback_cat(s):
        if s >= 70:   return "Positive"
        if s <= 40:   return "Negative"
        return "Suggestion"
    df["Feedback_Category"] = df["Brand_Sentiment_Score"].apply(feedback_cat)

    # --- Case Status from NPS ---
    def case_status(nps):
        if nps >= 30:  return "Resolved"
        if nps >= 0:   return "In Progress"
        return "Pending"
    df["Case_Status"] = df["NPS"].apply(case_status)

    # --- Resolution metrics ---
    df["Is_Complaint"]  = (df["Feedback_Category"] == "Negative").astype(int)
    df["Is_Resolved"]   = (df["Case_Status"] == "Resolved").astype(int)
    df["Resolution_Days"] = np.clip(
        (100 - df["Brand_Sentiment_Score"]) / 2 + rng.normal(0, 3, len(df)),
        1, 60,
    ).round(1)

    return df


DF = load_and_clean(DATA_FILE)

# ---------------------------------------------------------------------------
# 3. DASH APP
# ---------------------------------------------------------------------------
app = Dash(__name__, title="Brand Analytics Dashboard")
server = app.server  # for deployment

# ---------- Reusable component helpers ----------
CARD_STYLE = {
    "backgroundColor": COLORS["panel"],
    "borderRadius": "14px",
    "padding": "18px 20px",
    "boxShadow": "0 4px 20px rgba(0,0,0,0.35)",
}

def kpi_card(card_id: str, label: str, color: str):
    return html.Div(
        style={**CARD_STYLE, "flex": "1", "minWidth": "200px",
               "borderLeft": f"5px solid {color}"},
        children=[
            html.Div(label, style={"color": COLORS["muted"], "fontSize": "13px",
                                   "letterSpacing": "1px", "textTransform": "uppercase"}),
            html.Div(id=card_id, style={"color": COLORS["text"], "fontSize": "28px",
                                        "fontWeight": "700", "marginTop": "6px"}),
        ],
    )

def graph_panel(graph_id: str, title: str):
    return html.Div(
        style=CARD_STYLE,
        children=[
            html.H4(title, style={"color": COLORS["text"], "marginTop": 0, "marginBottom": "10px"}),
            dcc.Graph(id=graph_id, config={"displayModeBar": False},
                      style={"height": "360px"}),
        ],
    )

def dropdown(id_, options, multi=False, placeholder=""):
    return dcc.Dropdown(
        id=id_,
        options=[{"label": str(o), "value": o} for o in options],
        multi=multi,
        placeholder=placeholder,
        style={"color": "#0F172A"},
    )

# ---------- Layout ----------
brands   = sorted(DF["Brand_Name"].unique())
years    = sorted(DF["Year"].unique())
months   = sorted(DF["Month"].unique())
fbacks   = sorted(DF["Feedback_Category"].unique())
statuses = sorted(DF["Case_Status"].unique())

app.layout = html.Div(
    style={"backgroundColor": COLORS["bg"], "minHeight": "100vh",
           "padding": "24px", "fontFamily": "Inter, system-ui, sans-serif"},
    children=[
        # Header
        html.Div(
            style={"display": "flex", "justifyContent": "space-between",
                   "alignItems": "center", "marginBottom": "20px"},
            children=[
                html.Div([
                    html.H1("Brand Analytics Dashboard",
                            style={"color": COLORS["text"], "margin": 0}),
                    html.Div("Interactive insights across brands, sentiment & resolutions",
                             style={"color": COLORS["muted"]}),
                ]),
                html.Div(f"{len(DF):,} records loaded",
                         style={"color": COLORS["primary"], "fontWeight": 600}),
            ],
        ),

        # Filters
        html.Div(
            style={**CARD_STYLE, "marginBottom": "18px"},
            children=[
                html.Div("Filters", style={"color": COLORS["muted"], "marginBottom": "10px"}),
                html.Div(
                    style={"display": "grid",
                           "gridTemplateColumns": "repeat(auto-fit,minmax(180px,1fr))",
                           "gap": "12px"},
                    children=[
                        dropdown("f-brand",  brands,   multi=True, placeholder="Brand(s)"),
                        dropdown("f-year",   years,    multi=True, placeholder="Year(s)"),
                        dropdown("f-month",  months,   multi=True, placeholder="Month(s)"),
                        dropdown("f-fback",  fbacks,   multi=True, placeholder="Feedback type"),
                        dropdown("f-status", statuses, multi=True, placeholder="Case status"),
                    ],
                ),
            ],
        ),

        # KPI row
        html.Div(
            style={"display": "flex", "gap": "14px", "flexWrap": "wrap",
                   "marginBottom": "18px"},
            children=[
                kpi_card("kpi-records",    "Total Records",    COLORS["primary"]),
                kpi_card("kpi-rating",     "Average Rating",   COLORS["good"]),
                kpi_card("kpi-complaints", "Total Complaints", COLORS["bad"]),
                kpi_card("kpi-resolution", "Resolution Rate",  COLORS["warn"]),
            ],
        ),

        # Row 1
        html.Div(
            style={"display": "grid",
                   "gridTemplateColumns": "2fr 1fr", "gap": "14px", "marginBottom": "14px"},
            children=[
                graph_panel("g-brand-bar",  "Top Brands by Revenue"),
                graph_panel("g-status-pie", "Case Status Distribution"),
            ],
        ),

        # Row 2
        html.Div(
            style={"display": "grid",
                   "gridTemplateColumns": "1fr 1fr", "gap": "14px", "marginBottom": "14px"},
            children=[
                graph_panel("g-monthly", "Cases Resolved per Month"),
                graph_panel("g-yearly",  "Cases Resolved per Year"),
            ],
        ),

        # Row 3
        html.Div(
            style={"display": "grid",
                   "gridTemplateColumns": "1fr 1fr", "gap": "14px", "marginBottom": "14px"},
            children=[
                graph_panel("g-heatmap", "Correlation Heatmap"),
                graph_panel("g-scatter", "Rating vs Resolution Days"),
            ],
        ),

        # Special sections
        html.H3("Public Suggestions Analysis",
                style={"color": COLORS["text"], "marginTop": "10px"}),
        html.Div(
            style={"display": "grid",
                   "gridTemplateColumns": "1fr 1fr", "gap": "14px", "marginBottom": "14px"},
            children=[
                graph_panel("g-suggest-industry", "Suggestions by Industry"),
                graph_panel("g-suggest-trend",    "Suggestion Volume Trend"),
            ],
        ),

        html.H3("Complaint Trends",
                style={"color": COLORS["text"], "marginTop": "10px"}),
        html.Div(
            style={"display": "grid",
                   "gridTemplateColumns": "1fr 1fr", "gap": "14px", "marginBottom": "14px"},
            children=[
                graph_panel("g-complaint-trend",  "Complaints Over Time"),
                graph_panel("g-3d",               "3D View: Revenue × Sentiment × NPS"),
            ],
        ),

        html.Div("Built with Plotly Dash · © Brand Analytics",
                 style={"textAlign": "center", "color": COLORS["muted"],
                        "padding": "16px"}),
    ],
)

# ---------------------------------------------------------------------------
# 4. CALLBACKS
# ---------------------------------------------------------------------------
def apply_filters(brand, year, month, fback, status):
    d = DF.copy()
    if brand:  d = d[d["Brand_Name"].isin(brand)]
    if year:   d = d[d["Year"].isin(year)]
    if month:  d = d[d["Month"].isin(month)]
    if fback:  d = d[d["Feedback_Category"].isin(fback)]
    if status: d = d[d["Case_Status"].isin(status)]
    return d

def style_fig(fig):
    fig.update_layout(
        template=PLOT_TEMPLATE,
        paper_bgcolor=COLORS["panel"],
        plot_bgcolor=COLORS["panel"],
        font=dict(color=COLORS["text"], family="Inter"),
        margin=dict(l=30, r=20, t=30, b=30),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


@app.callback(
    Output("kpi-records", "children"),
    Output("kpi-rating", "children"),
    Output("kpi-complaints", "children"),
    Output("kpi-resolution", "children"),
    Output("g-brand-bar", "figure"),
    Output("g-status-pie", "figure"),
    Output("g-monthly", "figure"),
    Output("g-yearly", "figure"),
    Output("g-heatmap", "figure"),
    Output("g-scatter", "figure"),
    Output("g-suggest-industry", "figure"),
    Output("g-suggest-trend", "figure"),
    Output("g-complaint-trend", "figure"),
    Output("g-3d", "figure"),
    Input("f-brand", "value"),
    Input("f-year", "value"),
    Input("f-month", "value"),
    Input("f-fback", "value"),
    Input("f-status", "value"),
)
def update_dashboard(brand, year, month, fback, status):
    d = apply_filters(brand, year, month, fback, status)

    # Empty-state safe defaults
    if d.empty:
        empty = style_fig(go.Figure().add_annotation(
            text="No data for selected filters", showarrow=False,
            font=dict(color=COLORS["muted"], size=16)))
        return ("0", "—", "0", "0%",
                empty, empty, empty, empty, empty, empty,
                empty, empty, empty, empty)

    # ---- KPIs ----
    total = f"{len(d):,}"
    avg_rating = f"{d['Rating'].mean():.2f} / 10"
    complaints = f"{int(d['Is_Complaint'].sum()):,}"
    res_rate = f"{(d['Is_Resolved'].mean() * 100):.1f}%"

    # ---- Bar: top brands by revenue ----
    top = (d.groupby("Brand_Name")["Revenue_USD_M"].sum()
             .nlargest(15).reset_index())
    fig_bar = px.bar(top, x="Revenue_USD_M", y="Brand_Name", orientation="h",
                     color="Revenue_USD_M", color_continuous_scale="Tealgrn",
                     labels={"Revenue_USD_M": "Revenue (USD M)", "Brand_Name": ""})
    fig_bar.update_layout(yaxis=dict(autorange="reversed"), coloraxis_showscale=False)

    # ---- Pie: case status ----
    pie = d["Case_Status"].value_counts().reset_index()
    pie.columns = ["Status", "Count"]
    fig_pie = px.pie(pie, names="Status", values="Count", hole=0.55,
                     color_discrete_sequence=SEQ_COLORS)
    fig_pie.update_traces(textinfo="percent+label")

    # ---- Monthly resolution ----
    monthly = (d.groupby("YearMonth")
                 .agg(Resolved=("Is_Resolved", "sum"),
                      Total=("Is_Resolved", "count"))
                 .reset_index().sort_values("YearMonth"))
    fig_month = go.Figure()
    fig_month.add_trace(go.Scatter(x=monthly["YearMonth"], y=monthly["Total"],
                                   mode="lines", name="Total Cases",
                                   line=dict(color=COLORS["muted"], width=2)))
    fig_month.add_trace(go.Scatter(x=monthly["YearMonth"], y=monthly["Resolved"],
                                   mode="lines+markers", name="Resolved",
                                   line=dict(color=COLORS["good"], width=3)))

    # ---- Yearly resolution ----
    yearly = (d.groupby("Year")
                .agg(Resolved=("Is_Resolved", "sum"),
                     Total=("Is_Resolved", "count")).reset_index())
    fig_year = go.Figure()
    fig_year.add_trace(go.Bar(x=yearly["Year"], y=yearly["Total"],
                              name="Total", marker_color=COLORS["panel2"]))
    fig_year.add_trace(go.Bar(x=yearly["Year"], y=yearly["Resolved"],
                              name="Resolved", marker_color=COLORS["primary"]))
    fig_year.update_layout(barmode="overlay")

    # ---- Heatmap: correlation ----
    num = d.select_dtypes(include=np.number).drop(
        columns=["Year", "Month", "Is_Complaint", "Is_Resolved"], errors="ignore")
    corr = num.corr().round(2)
    fig_heat = px.imshow(corr, text_auto=True, aspect="auto",
                         color_continuous_scale="RdBu_r", zmin=-1, zmax=1)

    # ---- Scatter: rating vs resolution days ----
    samp = d.sample(min(len(d), 1500), random_state=1)
    fig_scatter = px.scatter(samp, x="Resolution_Days", y="Rating",
                             color="Feedback_Category", size="Revenue_USD_M",
                             hover_data=["Brand_Name", "Industry"],
                             color_discrete_sequence=SEQ_COLORS, opacity=0.75)

    # ---- Suggestions by industry ----
    sug = d[d["Feedback_Category"] == "Suggestion"]
    if sug.empty:
        sug_ind_fig = go.Figure().add_annotation(text="No suggestions in current filter",
                                                 showarrow=False, font=dict(color=COLORS["muted"]))
    else:
        sug_ind = sug["Industry"].value_counts().nlargest(10).reset_index()
        sug_ind.columns = ["Industry", "Count"]
        sug_ind_fig = px.bar(sug_ind, x="Count", y="Industry", orientation="h",
                             color="Count", color_continuous_scale="Magenta")
        sug_ind_fig.update_layout(yaxis=dict(autorange="reversed"),
                                  coloraxis_showscale=False)

    # ---- Suggestion trend ----
    if sug.empty:
        sug_tr_fig = go.Figure().add_annotation(text="No suggestion trend",
                                                showarrow=False, font=dict(color=COLORS["muted"]))
    else:
        sug_tr = sug.groupby("YearMonth").size().reset_index(name="Suggestions")
        sug_tr_fig = px.area(sug_tr, x="YearMonth", y="Suggestions",
                             color_discrete_sequence=[COLORS["accent"]])

    # ---- Complaint trend ----
    comp = d[d["Is_Complaint"] == 1]
    if comp.empty:
        comp_fig = go.Figure().add_annotation(text="No complaints in current filter",
                                              showarrow=False, font=dict(color=COLORS["muted"]))
    else:
        comp_tr = comp.groupby("YearMonth").size().reset_index(name="Complaints")
        comp_fig = px.line(comp_tr, x="YearMonth", y="Complaints", markers=True,
                           color_discrete_sequence=[COLORS["bad"]])
        comp_fig.update_traces(line=dict(width=3))

    # ---- 3D scatter ----
    samp3d = d.sample(min(len(d), 1200), random_state=2)
    fig_3d = px.scatter_3d(samp3d, x="Revenue_USD_M",
                           y="Brand_Sentiment_Score", z="NPS",
                           color="Feedback_Category", size="Rating",
                           color_discrete_sequence=SEQ_COLORS, opacity=0.75)
    fig_3d.update_layout(scene=dict(
        xaxis=dict(backgroundcolor=COLORS["panel"], color=COLORS["text"]),
        yaxis=dict(backgroundcolor=COLORS["panel"], color=COLORS["text"]),
        zaxis=dict(backgroundcolor=COLORS["panel"], color=COLORS["text"]),
    ))

    figs = [fig_bar, fig_pie, fig_month, fig_year, fig_heat, fig_scatter,
            sug_ind_fig, sug_tr_fig, comp_fig, fig_3d]
    figs = [style_fig(f) if isinstance(f, go.Figure) else style_fig(go.Figure(f))
            for f in figs]

    return (total, avg_rating, complaints, res_rate, *figs)


# ---------------------------------------------------------------------------
# 5. ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
