"""Plotly charts. Each function returns a figure; the app decides where to show it."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

PORT_COLOR = "#2563EB"   # portfolio
BENCH_COLOR = "#9CA3AF"  # benchmark
LOSS_COLOR = "#DC2626"
PALETTE = ["#2563EB", "#0EA5E9", "#14B8A6", "#F59E0B", "#8B5CF6", "#EC4899", "#64748B", "#84CC16",
           "#F97316", "#06B6D4"]


def _layout(fig: go.Figure, title: str, y_fmt: str | None = None, height: int = 380) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=16)), height=height,
        margin=dict(l=10, r=10, t=50, b=40), hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", tickformat=y_fmt)
    return fig


def allocation_donut(weights: dict[str, float], amounts: dict[str, float] | None = None) -> go.Figure:
    labels = list(weights)
    values = [amounts[t] for t in labels] if amounts else [weights[t] for t in labels]
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.55, sort=False,
                           marker=dict(colors=PALETTE[:len(labels)]),
                           textinfo="label+percent", hovertemplate="%{label}: %{percent}<extra></extra>"))
    fig.update_layout(showlegend=False)
    return _layout(fig, "Allocation", height=340)


def growth_chart(port_value: pd.Series, bench_value: pd.Series, benchmark: str, start_amount: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bench_value.index, y=bench_value * start_amount, name=benchmark,
                             line=dict(color=BENCH_COLOR, width=2)))
    fig.add_trace(go.Scatter(x=port_value.index, y=port_value * start_amount, name="Portfolio",
                             line=dict(color=PORT_COLOR, width=2.5)))
    return _layout(fig, f"Growth of ${start_amount:,.0f}: portfolio vs {benchmark}", "$,.0f")


def drawdown_chart(port_dd: pd.Series, bench_dd: pd.Series, benchmark: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bench_dd.index, y=bench_dd, name=benchmark, line=dict(color=BENCH_COLOR, width=1.5)))
    fig.add_trace(go.Scatter(x=port_dd.index, y=port_dd, name="Portfolio", fill="tozeroy",
                             line=dict(color=LOSS_COLOR, width=1.5), fillcolor="rgba(220,38,38,0.15)"))
    return _layout(fig, "Drawdown: % below previous peak", ".0%")


def rolling_vol_chart(port_vol: pd.Series, bench_vol: pd.Series, benchmark: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bench_vol.index, y=bench_vol, name=benchmark, line=dict(color=BENCH_COLOR, width=1.5)))
    fig.add_trace(go.Scatter(x=port_vol.index, y=port_vol, name="Portfolio", line=dict(color=PORT_COLOR, width=2)))
    return _layout(fig, "Rolling 3-month annualized volatility", ".0%")


def risk_vs_weight_chart(weights: dict[str, float], rc: pd.Series) -> go.Figure:
    tickers = list(weights)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=tickers, y=[weights[t] for t in tickers], name="Share of money", marker_color=BENCH_COLOR))
    fig.add_trace(go.Bar(x=tickers, y=[rc[t] for t in tickers], name="Share of risk", marker_color=PORT_COLOR))
    fig.update_layout(barmode="group", hovermode="x")
    return _layout(fig, "Share of money vs share of risk", ".0%")


def correlation_heatmap(corr: pd.DataFrame) -> go.Figure:
    fig = px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r", aspect="auto")
    fig.update_layout(coloraxis_showscale=False)
    fig = _layout(fig, "Correlation of daily returns", height=max(320, 60 * len(corr)))
    fig.update_layout(hovermode="closest")
    return fig


def risk_return_scatter(asset_stats: pd.DataFrame, port_point: tuple[float, float],
                        bench_point: tuple[float, float], benchmark: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=asset_stats["Annualized volatility"], y=asset_stats["Annualized return"], mode="markers+text",
        text=asset_stats.index, textposition="top center", name="Holdings",
        marker=dict(size=11, color="#64748B"),
        hovertemplate="%{text}<br>Vol %{x:.1%}<br>Return %{y:.1%}<extra></extra>"))
    if benchmark not in asset_stats.index:   # don't plot the same point twice
        fig.add_trace(go.Scatter(x=[bench_point[0]], y=[bench_point[1]], mode="markers+text", text=[benchmark],
                                 textposition="bottom center", name=benchmark,
                                 marker=dict(size=14, color=BENCH_COLOR, symbol="diamond")))
    fig.add_trace(go.Scatter(x=[port_point[0]], y=[port_point[1]], mode="markers+text", text=["Portfolio"],
                             textposition="bottom center", name="Portfolio",
                             marker=dict(size=16, color=PORT_COLOR, symbol="star")))
    fig.update_layout(hovermode="closest", showlegend=False)
    fig.update_xaxes(tickformat=".0%", title="Annualized volatility (risk)", showgrid=True,
                     gridcolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(title="Annualized return")
    return _layout(fig, "Risk vs return", ".0%", height=420)


def whatif_bars(current: dict, proposed: dict, keys: list[str]) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=keys, y=[current[k] for k in keys], name="Current", marker_color=BENCH_COLOR))
    fig.add_trace(go.Bar(x=keys, y=[proposed[k] for k in keys], name="What-if", marker_color=PORT_COLOR))
    fig.update_layout(barmode="group", hovermode="x")
    return _layout(fig, "Current vs what-if: return and risk", ".1%", height=340)
