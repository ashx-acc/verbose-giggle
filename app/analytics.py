"""Dashboard analytics, Matplotlib charts, insights, and PNG report export."""

from __future__ import annotations

import sqlite3
import textwrap
import time
from datetime import datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .config import CHARTS_DIR, DB_PATH, SCREENSHOTS_DIR

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

NAVY = "#0f172a"
TEAL = "#0f766e"
AMBER = "#d97706"
ROSE = "#be123c"
BLUE = "#1d4ed8"
SLATE = "#64748b"
GRID = "#e2e8f0"

DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
MONTH_LABELS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

sns.set_theme(style="whitegrid", context="notebook", font_scale=1.0)
plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": GRID,
        "axes.labelcolor": "#334155",
        "xtick.color": "#475569",
        "ytick.color": "#475569",
        "text.color": NAVY,
        "font.family": "DejaVu Sans",
    }
)

CHART_DEFINITIONS = [
    ("trend", "Crime trend over years", "Reported crimes per calendar year."),
    ("top_crimes", "Top 10 crime categories", "Primary type share of all records."),
    ("arrest_by_year", "Arrest rate by year", "Percentage of records ending in arrest."),
    ("heatmap", "Month × day heatmap", "Crime frequency by month and weekday."),
    ("top_communities", "Top 10 community areas", "Highest crime volume by community."),
    ("hourly", "Crime by hour of day", "Synthetic hour profile (seed = 42)."),
    ("outliers", "Community-area outliers", "IQR upper fence highlights extreme areas."),
    ("correlation", "Correlation matrix", "Relationships between numeric features."),
]


# ---------------------------------------------------------------------------
# Data loading and analysis
# ---------------------------------------------------------------------------


def _read_sql(query: str) -> pd.DataFrame:
    try:
        with sqlite3.connect(DB_PATH) as connection:
            return pd.read_sql_query(query, connection)
    except Exception:
        return pd.DataFrame()


def load_crime_data() -> pd.DataFrame:
    """Load the fact table and enrich it with community names."""

    frame = _read_sql("SELECT * FROM crime ORDER BY id")
    if frame.empty:
        return frame

    # The notebook's crime table does not store the synthetic hour column.
    # Recreate the same seeded profile when it is absent so the dashboard works
    # against both the notebook database and a freshly seeded database.
    if "synthetic_hour" not in frame.columns:
        rng = np.random.default_rng(seed=42)
        frame["synthetic_hour"] = rng.integers(0, 24, size=len(frame))

    for column in ("arrest", "domestic"):
        if column in frame.columns:
            frame[column] = (
                pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
            )

    for column in ("Year", "Month", "synthetic_hour"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    for column in ("Year", "Month", "synthetic_hour"):
        if column in frame.columns:
            frame[column] = frame[column].astype("Int64")

    if "DayOfWeek" not in frame.columns:
        frame["DayOfWeek"] = "Unknown"
    frame["DayOfWeek"] = frame["DayOfWeek"].fillna("Unknown").astype(str)

    if "primary_type" not in frame.columns:
        frame["primary_type"] = "UNKNOWN"
    frame["primary_type"] = (
        frame["primary_type"].fillna("UNKNOWN").astype(str).str.strip().str.upper()
    )

    communities = _read_sql("SELECT community_code, community_name FROM community")
    if not communities.empty and "community_code" in frame.columns:
        frame = frame.merge(communities, on="community_code", how="left")

    if "community_name" not in frame.columns:
        fallback = (
            frame["community_code"]
            if "community_code" in frame.columns
            else pd.Series("Unknown", index=frame.index)
        )
        frame["community_name"] = fallback.astype(str)
    frame["community_name"] = frame["community_name"].fillna("Unknown").astype(str)

    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")

    return frame


def _empty_analysis() -> dict[str, Any]:
    empty = pd.DataFrame()
    return {
        "frame": empty,
        "yearly": empty,
        "arrest_by_year": empty,
        "top_categories": empty,
        "community_counts": empty,
        "outliers": empty,
        "month_day": empty,
        "hourly": empty,
        "correlation": empty,
        "kpis": {
            "total_crimes": 0,
            "arrest_rate": 0.0,
            "unique_crime_types": 0,
            "top_crime_type": "N/A",
            "top_crime_count": 0,
            "top_crime_share": 0.0,
            "top_community": "N/A",
            "top_community_count": 0,
            "peak_year": None,
            "peak_year_count": 0,
            "peak_month": None,
            "peak_month_name": "N/A",
            "peak_month_count": 0,
            "peak_day": "N/A",
            "peak_day_count": 0,
            "peak_hour": None,
            "peak_hour_count": 0,
            "domestic_rate": 0.0,
            "community_count": 0,
            "outlier_count": 0,
            "outlier_upper": 0.0,
            "year_min": None,
            "year_max": None,
        },
    }


def build_analysis(frame: pd.DataFrame | None = None) -> dict[str, Any]:
    """Compute every table and KPI used by the dashboard."""

    if frame is None:
        frame = load_crime_data()
    if frame.empty:
        return _empty_analysis()

    working = frame.copy()

    yearly = (
        working.dropna(subset=["Year"])
        .groupby("Year")
        .size()
        .reset_index(name="crime_count")
        .sort_values("Year")
    )

    arrest_by_year = (
        working.dropna(subset=["Year"])
        .groupby("Year")
        .agg(
            crime_count=("arrest", "size"),
            arrest_count=("arrest", "sum"),
        )
        .reset_index()
    )
    arrest_by_year["arrest_rate"] = np.where(
        arrest_by_year["crime_count"] > 0,
        arrest_by_year["arrest_count"] / arrest_by_year["crime_count"] * 100,
        0.0,
    ).round(2)

    category_counts = (
        working["primary_type"]
        .value_counts()
        .rename_axis("primary_type")
        .reset_index(name="crime_count")
    )
    category_counts["percentage"] = (
        category_counts["crime_count"] / len(working) * 100
    ).round(2)
    top_categories = category_counts.head(10).copy()

    community_counts = (
        working.groupby(["community_code", "community_name"], dropna=False)
        .size()
        .reset_index(name="crime_count")
        .sort_values("crime_count", ascending=False)
        .reset_index(drop=True)
    )

    if len(community_counts) >= 4:
        q1, q3 = np.percentile(community_counts["crime_count"], [25, 75])
    else:
        q1, q3 = 0.0, 0.0
    iqr = q3 - q1
    lower_limit = max(0.0, q1 - 1.5 * iqr)
    upper_limit = q3 + 1.5 * iqr
    outliers = community_counts[
        community_counts["crime_count"] > upper_limit
    ].reset_index(drop=True)

    month_day = pd.crosstab(working["Month"], working["DayOfWeek"])
    month_day = month_day.reindex(
        index=range(1, 13),
        columns=DAY_ORDER,
        fill_value=0,
    )
    month_day.index = [MONTH_LABELS[int(month) - 1] for month in month_day.index]

    hourly = (
        working.dropna(subset=["synthetic_hour"])
        .groupby("synthetic_hour")
        .size()
        .reindex(range(24), fill_value=0)
        .reset_index(name="crime_count")
        .rename(columns={"synthetic_hour": "Hour"})
    )

    correlation_columns = [
        column
        for column in [
            "Year",
            "Month",
            "arrest",
            "domestic",
            "synthetic_hour",
            "community_code",
            "district_code",
            "ward_no",
            "latitude",
            "longitude",
        ]
        if column in working.columns
    ]
    correlation = (
        working[correlation_columns]
        .apply(pd.to_numeric, errors="coerce")
        .corr()
    )

    year_counts = yearly.set_index("Year")["crime_count"]
    month_counts = working["Month"].value_counts()
    day_counts = working["DayOfWeek"].value_counts()
    hour_counts = working["synthetic_hour"].value_counts()

    top_type = category_counts.iloc[0]
    top_community = community_counts.iloc[0]
    peak_month = int(month_counts.idxmax()) if not month_counts.empty else None

    kpis = {
        "total_crimes": int(len(working)),
        "arrest_rate": round(float(working["arrest"].mean() * 100), 2),
        "unique_crime_types": int(working["primary_type"].nunique()),
        "top_crime_type": str(top_type["primary_type"]),
        "top_crime_count": int(top_type["crime_count"]),
        "top_crime_share": float(top_type["percentage"]),
        "top_community": str(top_community["community_name"]),
        "top_community_count": int(top_community["crime_count"]),
        "peak_year": int(year_counts.idxmax()) if not year_counts.empty else None,
        "peak_year_count": int(year_counts.max()) if not year_counts.empty else 0,
        "peak_month": peak_month,
        "peak_month_name": MONTH_LABELS[peak_month - 1] if peak_month else "N/A",
        "peak_month_count": int(month_counts.max()) if not month_counts.empty else 0,
        "peak_day": str(day_counts.idxmax()) if not day_counts.empty else "N/A",
        "peak_day_count": int(day_counts.max()) if not day_counts.empty else 0,
        "peak_hour": int(hour_counts.idxmax()) if not hour_counts.empty else None,
        "peak_hour_count": int(hour_counts.max()) if not hour_counts.empty else 0,
        "domestic_rate": round(float(working["domestic"].mean() * 100), 2),
        "community_count": int(len(community_counts)),
        "outlier_count": int(len(outliers)),
        "outlier_upper": round(float(upper_limit), 2),
        "year_min": int(yearly["Year"].min()) if not yearly.empty else None,
        "year_max": int(yearly["Year"].max()) if not yearly.empty else None,
    }

    analysis = {
        "frame": working,
        "yearly": yearly,
        "arrest_by_year": arrest_by_year,
        "top_categories": top_categories,
        "community_counts": community_counts,
        "outliers": outliers,
        "month_day": month_day,
        "hourly": hourly,
        "correlation": correlation,
        "kpis": kpis,
        "iqr": {
            "q1": float(q1),
            "q3": float(q3),
            "iqr": float(iqr),
            "lower_limit": float(lower_limit),
            "upper_limit": float(upper_limit),
        },
    }
    analysis["insights"] = build_insights(analysis)
    return analysis


def build_insights(analysis: dict[str, Any]) -> list[str]:
    """Turn the computed analysis into plain-English executive insights."""

    kpis = analysis["kpis"]
    yearly = analysis["yearly"]
    insights: list[str] = []

    if not kpis["total_crimes"]:
        return ["No crime records are available in the warehouse yet."]

    insights.append(
        f"The warehouse contains {kpis['total_crimes']:,} crime records "
        f"across {kpis['unique_crime_types']} unique primary crime types."
    )

    if not yearly.empty:
        top_year = yearly.sort_values("crime_count", ascending=False).iloc[0]
        share = top_year["crime_count"] / kpis["total_crimes"] * 100
        if share >= 70:
            insights.append(
                f"The sample is heavily concentrated in {int(top_year['Year'])}: "
                f"{int(top_year['crime_count']):,} of {kpis['total_crimes']:,} "
                f"records ({share:.1f}%). Treat year-over-year movement as "
                "directional rather than a true citywide trend."
            )
        else:
            insights.append(
                f"Crime reports peaked in {int(top_year['Year'])} with "
                f"{int(top_year['crime_count']):,} records."
            )

    insights.append(
        f"{kpis['top_crime_type'].title()} is the most frequent primary type "
        f"with {kpis['top_crime_count']:,} cases "
        f"({kpis['top_crime_share']:.1f}% of all records)."
    )

    insights.append(
        f"The overall arrest rate is {kpis['arrest_rate']:.1f}%. It is not "
        "consistent across years, and the early-year rates are unstable because "
        "2012–2015 contain only a handful of records."
    )

    insights.append(
        f"{kpis['top_community']} has the highest crime volume "
        f"({kpis['top_community_count']:,} records), so it is a priority area "
        "for patrol allocation and prevention programmes."
    )

    insights.append(
        f"{kpis['peak_month_name']} is the busiest month "
        f"({kpis['peak_month_count']:,} records) and {kpis['peak_day']} is the "
        f"busiest weekday ({kpis['peak_day_count']:,} records)."
    )

    if kpis["peak_hour"] is not None:
        insights.append(
            f"The synthetic hour profile peaks at {kpis['peak_hour']:02d}:00 "
            f"({kpis['peak_hour_count']:,} records). The source CSV has no time "
            "field, so this hourly view is a seeded simulation, not an observed "
            "timestamp."
        )

    if not analysis["outliers"].empty:
        names = ", ".join(
            f"{row.community_name} ({row.crime_count})"
            for row in analysis["outliers"].itertuples()
        )
        insights.append(
            f"Using the IQR rule (upper fence = {kpis['outlier_upper']:.1f}), "
            f"{kpis['outlier_count']} community areas are extreme outliers: {names}."
        )

    correlation = analysis["correlation"]
    if not correlation.empty:
        pairs = (
            correlation.where(
                np.triu(np.ones(correlation.shape), k=1).astype(bool)
            )
            .stack()
            .dropna()
        )
        if not pairs.empty:
            pairs = pairs.reindex(pairs.abs().sort_values(ascending=False).index)
            (left, right), value = pairs.index[0], float(pairs.iloc[0])
            insights.append(
                f"The strongest numeric relationship is {left} vs {right} "
                f"(r = {value:.2f}). Correlation is not causation; use it to "
                "guide further investigation."
            )

    return insights


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------


def _style_axes(ax: plt.Axes, title: str, subtitle: str | None = None) -> None:
    ax.set_title(
        title,
        loc="left",
        fontsize=15,
        fontweight="bold",
        color=NAVY,
        pad=18,
    )
    if subtitle:
        ax.text(
            0,
            1.015,
            subtitle,
            transform=ax.transAxes,
            fontsize=9.5,
            color=SLATE,
            va="bottom",
        )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _save(fig: plt.Figure, filename: str) -> str:
    path = CHARTS_DIR / filename
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(path)


def build_charts(analysis: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Create all dashboard PNGs and return URL + file-path maps."""

    yearly = analysis["yearly"]
    top_categories = analysis["top_categories"]
    arrest_by_year = analysis["arrest_by_year"]
    month_day = analysis["month_day"]
    community_counts = analysis["community_counts"]
    outliers = analysis["outliers"]
    hourly = analysis["hourly"]
    correlation = analysis["correlation"]

    paths: dict[str, str] = {}

    # 1. Crime trend over years
    fig, ax = plt.subplots(figsize=(10, 5.4))
    if not yearly.empty:
        sns.lineplot(
            data=yearly,
            x="Year",
            y="crime_count",
            marker="o",
            markersize=8,
            linewidth=3,
            color=TEAL,
            ax=ax,
        )
        ax.fill_between(
            yearly["Year"].astype(int),
            yearly["crime_count"],
            color=TEAL,
            alpha=0.12,
        )
        for row in yearly.itertuples():
            ax.annotate(
                f"{int(row.crime_count):,}",
                (int(row.Year), row.crime_count),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=9,
                color=NAVY,
            )
        ax.set_xticks(yearly["Year"].astype(int))
    _style_axes(ax, "Reported crimes per year", "Total records in the warehouse")
    ax.set_xlabel("Year")
    ax.set_ylabel("Reported crimes")
    paths["trend"] = _save(fig, "crime_trend.png")

    # 2. Top 10 crime categories
    fig, ax = plt.subplots(figsize=(10, 5.4))
    if not top_categories.empty:
        plot_data = top_categories.sort_values("crime_count")
        sns.barplot(
            data=plot_data,
            x="crime_count",
            y="primary_type",
            hue="primary_type",
            palette="crest",
            legend=False,
            ax=ax,
        )
        max_value = plot_data["crime_count"].max()
        for index, row in enumerate(plot_data.itertuples()):
            ax.text(
                row.crime_count + max_value * 0.01,
                index,
                f"{row.percentage:.1f}%",
                va="center",
                fontsize=9,
                color=SLATE,
            )
    _style_axes(ax, "Top 10 crime categories", "Primary type, with share of total")
    ax.set_xlabel("Number of crimes")
    ax.set_ylabel("")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    paths["top_crimes"] = _save(fig, "top_crimes.png")

    # 3. Arrest rate by year
    fig, ax = plt.subplots(figsize=(10, 5.4))
    if not arrest_by_year.empty:
        sns.barplot(
            data=arrest_by_year,
            x="Year",
            y="arrest_rate",
            color=AMBER,
            ax=ax,
        )
        for index, row in enumerate(arrest_by_year.itertuples()):
            ax.text(
                index,
                min(row.arrest_rate + 3, 101),
                f"{row.arrest_rate:.1f}%",
                ha="center",
                fontsize=9,
                color=NAVY,
            )
        ax.set_ylim(0, 110)
    _style_axes(ax, "Arrest rate by year", "Share of records with arrest = true")
    ax.set_xlabel("Year")
    ax.set_ylabel("Arrest rate (%)")
    paths["arrest_by_year"] = _save(fig, "arrest_by_year.png")

    # 4. Month × day heatmap
    fig, ax = plt.subplots(figsize=(10, 6.2))
    if not month_day.empty:
        sns.heatmap(
            month_day,
            annot=True,
            fmt="d",
            cmap="YlGnBu",
            linewidths=0.6,
            linecolor="white",
            cbar_kws={"label": "Crimes"},
            ax=ax,
        )
    _style_axes(ax, "Crime frequency by month and weekday", "Darker cells mean more crimes")
    ax.set_xlabel("Day of week")
    ax.set_ylabel("Month")
    ax.grid(False)
    paths["heatmap"] = _save(fig, "month_day_heatmap.png")

    # 5. Top community areas
    fig, ax = plt.subplots(figsize=(10, 5.4))
    if not community_counts.empty:
        plot_data = community_counts.head(10).sort_values("crime_count")
        sns.barplot(
            data=plot_data,
            x="crime_count",
            y="community_name",
            hue="community_name",
            palette="flare",
            legend=False,
            ax=ax,
        )
    _style_axes(ax, "Top 10 community areas", "Highest crime volume by community")
    ax.set_xlabel("Number of crimes")
    ax.set_ylabel("")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    paths["top_communities"] = _save(fig, "top_communities.png")

    # 6. Hourly profile
    fig, ax = plt.subplots(figsize=(10, 5.4))
    if not hourly.empty:
        sns.lineplot(
            data=hourly,
            x="Hour",
            y="crime_count",
            marker="o",
            linewidth=3,
            color=BLUE,
            ax=ax,
        )
        ax.fill_between(
            hourly["Hour"].astype(int),
            hourly["crime_count"],
            color=BLUE,
            alpha=0.10,
        )
        ax.set_xticks(range(0, 24, 2))
    _style_axes(ax, "Crime by hour of day", "Synthetic hour (seed = 42)")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Reported crimes")
    paths["hourly"] = _save(fig, "crime_by_hour.png")

    # 7. Community-area outliers
    fig, ax = plt.subplots(figsize=(10, 5.4))
    if not community_counts.empty:
        sns.boxplot(
            data=community_counts,
            x="crime_count",
            color="#cbd5e1",
            width=0.5,
            ax=ax,
        )
        if not outliers.empty:
            sns.stripplot(
                data=outliers,
                x="crime_count",
                color=ROSE,
                size=9,
                ax=ax,
            )
            for row in outliers.itertuples():
                ax.annotate(
                    row.community_name,
                    (row.crime_count, 0),
                    textcoords="offset points",
                    xytext=(0, 16),
                    ha="center",
                    fontsize=8,
                    color=ROSE,
                )
    _style_axes(
        ax,
        "Community-area outliers (IQR)",
        f"Upper fence = {analysis['kpis']['outlier_upper']:.1f} crimes",
    )
    ax.set_xlabel("Crimes per community area")
    ax.set_yticks([])
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    paths["outliers"] = _save(fig, "community_outliers.png")

    # 8. Correlation matrix
    fig, ax = plt.subplots(figsize=(10, 6.4))
    if not correlation.empty:
        sns.heatmap(
            correlation,
            annot=True,
            fmt=".2f",
            cmap="vlag",
            center=0,
            linewidths=0.5,
            linecolor="white",
            cbar_kws={"label": "Correlation"},
            ax=ax,
        )
    _style_axes(ax, "Correlation matrix", "Numeric features in the cleaned data")
    ax.grid(False)
    paths["correlation"] = _save(fig, "correlation_matrix.png")

    urls = {
        key: f"/exports/charts/{path.replace(chr(92), '/').split('/')[-1]}"
        for key, path in paths.items()
    }
    return urls, paths


# ---------------------------------------------------------------------------
# Dashboard context, JSON payload, and report image
# ---------------------------------------------------------------------------


def _native(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {key: _native(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def build_dashboard_context() -> dict[str, Any]:
    """Build the template context for the dashboard page."""

    analysis = build_analysis()
    chart_urls, chart_paths = build_charts(analysis)

    if analysis["yearly"].empty or analysis["arrest_by_year"].empty:
        yearly_view = analysis["yearly"]
    else:
        yearly_view = analysis["yearly"].merge(
            analysis["arrest_by_year"][["Year", "arrest_count", "arrest_rate"]],
            on="Year",
            how="left",
        )

    chart_cards = [
        {
            "key": key,
            "url": chart_urls[key],
            "title": title,
            "caption": caption,
        }
        for key, title, caption in CHART_DEFINITIONS
    ]

    return {
        "kpis": analysis["kpis"],
        "insights": analysis["insights"],
        "charts": chart_urls,
        "chart_paths": chart_paths,
        "chart_cards": chart_cards,
        "chart_version": int(time.time()),
        "top_categories": _records(analysis["top_categories"]),
        "top_communities": _records(analysis["community_counts"].head(10)),
        "outliers": _records(analysis["outliers"]),
        "yearly": _records(yearly_view),
        "arrest_by_year": _records(analysis["arrest_by_year"]),
        "iqr": analysis.get("iqr", {}),
    }


def get_insights_payload() -> dict[str, Any]:
    """Small JSON payload for API clients (no chart generation)."""

    analysis = build_analysis()
    if analysis["yearly"].empty or analysis["arrest_by_year"].empty:
        yearly_view = analysis["yearly"]
    else:
        yearly_view = analysis["yearly"].merge(
            analysis["arrest_by_year"][["Year", "arrest_count", "arrest_rate"]],
            on="Year",
            how="left",
        )
    return {
        "kpis": analysis["kpis"],
        "insights": analysis["insights"],
        "top_categories": _records(analysis["top_categories"]),
        "top_communities": _records(analysis["community_counts"].head(10)),
        "outliers": _records(analysis["outliers"]),
        "yearly": _records(yearly_view),
        "arrest_by_year": _records(analysis["arrest_by_year"]),
        "iqr": analysis.get("iqr", {}),
    }


def build_report_image(context: dict[str, Any] | None = None) -> str:
    """Compose a tall PNG with KPIs, all charts, and the insight bullets."""

    if context is None:
        context = build_dashboard_context()

    kpis = context["kpis"]
    insights = context["insights"]
    chart_paths = context["chart_paths"]
    chart_keys = [key for key, _, _ in CHART_DEFINITIONS]

    fig = plt.figure(figsize=(17, 25), facecolor="white")
    grid = fig.add_gridspec(
        6,
        2,
        height_ratios=[0.75, 1, 1, 1, 1, 1.0],
        hspace=0.28,
        wspace=0.08,
        left=0.04,
        right=0.96,
        top=0.97,
        bottom=0.03,
    )

    title_ax = fig.add_subplot(grid[0, :])
    title_ax.axis("off")
    title_ax.text(
        0.0,
        0.92,
        "Chicago Crime Intelligence Dashboard",
        fontsize=30,
        fontweight="bold",
        color=NAVY,
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.0,
        0.68,
        (
            f"Accenture × Chicago Police Department  ·  "
            f"{kpis['total_crimes']:,} records  ·  "
            f"{kpis['year_min']}–{kpis['year_max']}  ·  "
            f"generated {datetime.now():%d %b %Y %H:%M}"
        ),
        fontsize=11,
        color=SLATE,
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.0,
        0.38,
        (
            f"Arrest rate  {kpis['arrest_rate']:.1f}%     |     "
            f"Top crime  {kpis['top_crime_type'].title()} "
            f"({kpis['top_crime_share']:.1f}%)     |     "
            f"Top community  {kpis['top_community']} "
            f"({kpis['top_community_count']:,})     |     "
            f"Peak hour  {kpis['peak_hour']:02d}:00"
        ),
        fontsize=11.5,
        color=TEAL,
        fontweight="bold",
        transform=title_ax.transAxes,
    )
    title_ax.text(
        0.0,
        0.13,
        (
            "Data note: the source sample is concentrated in 2016; hourly values "
            "are synthetic (seed = 42) because the raw CSV has no time-of-day field."
        ),
        fontsize=9.5,
        color=ROSE,
        transform=title_ax.transAxes,
    )

    for index, key in enumerate(chart_keys):
        row = 1 + index // 2
        column = index % 2
        chart_ax = fig.add_subplot(grid[row, column])
        chart_ax.imshow(plt.imread(chart_paths[key]))
        chart_ax.axis("off")

    insight_ax = fig.add_subplot(grid[5, :])
    insight_ax.axis("off")
    insight_ax.text(
        0.0,
        0.98,
        "Key insights",
        fontsize=16,
        fontweight="bold",
        color=NAVY,
        transform=insight_ax.transAxes,
        va="top",
    )
    wrapped = "\n".join(
        textwrap.fill(f"• {insight}", width=145) for insight in insights
    )
    insight_ax.text(
        0.0,
        0.82,
        wrapped,
        fontsize=9.8,
        color="#334155",
        transform=insight_ax.transAxes,
        va="top",
        linespacing=1.55,
    )

    output = SCREENSHOTS_DIR / "chicago_crime_dashboard_report.png"
    fig.savefig(
        output,
        dpi=125,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "Chicago Crime Analytics"},
    )
    plt.close(fig)
    return str(output)
