"""Box-plot generation: one projected-price box plot per DTE bucket."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless backend; safe for Streamlit/servers
import matplotlib.pyplot as plt

from .models import BucketResult


def _bucket_box_stats(b: BucketResult, spot: float) -> dict | None:
    """Matplotlib bxp stats dict for a bucket's ±sigma projection."""
    if b.sigma is None:
        return None
    return {
        "label": f"{b.target_dte}d",
        "whislo": spot - 3 * b.sigma,
        "q1": spot - 1 * b.sigma,
        "med": spot,
        "q3": spot + 1 * b.sigma,
        "whishi": spot + 3 * b.sigma,
        "fliers": [],
    }


def build_box_plots(buckets: list[BucketResult], spot: float, theme: str = "light"):
    """Return a matplotlib Figure with 4 box plots (one per DTE bucket).

    Each box spans ±1 sigma (q1..q3) with whiskers at ±3 sigma, median at spot.
    Call Wall (green), Put Wall (red), Magnet/GEX blend (purple dashed), GEX Wall
    (orange dotted), and γ-Flip (teal dash-dot) are marked. `theme` ("light" or
    "dark") controls the background/foreground so it matches the app's mode.
    """
    dark = theme == "dark"
    bg = "#0f172a" if dark else "#ffffff"        # slate-900 / white
    fg = "#e2e8f0" if dark else "#333333"        # slate-200 / dark gray
    grid = "#334155" if dark else "#e5e7eb"
    box_face = "#1e3a5f" if dark else "#cfe3ff"
    spot_color = "#f8fafc" if dark else "#111111"

    n = len(buckets)
    cols = 2
    rows = max(1, (n + cols - 1) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(11, 4.5 * rows))
    fig.patch.set_facecolor(bg)
    axes = axes.flatten() if n > 1 else [axes]

    for ax, b in zip(axes, buckets):
        ax.set_facecolor(bg)
        stats = _bucket_box_stats(b, spot)
        if stats is None:
            ax.text(0.5, 0.5, f"{b.label}\n(no IV data)", ha="center", va="center",
                    color=fg)
            ax.set_axis_off()
            continue

        ax.bxp([stats], showfliers=False, patch_artist=True,
               boxprops=dict(facecolor=box_face, edgecolor="#3a7bd5"),
               medianprops=dict(color=fg), whiskerprops=dict(color=fg),
               capprops=dict(color=fg))
        magnet = b.blended_magnet_strike if b.blended_magnet_strike is not None else b.magneto_strike
        ax.axhline(b.call_wall.strike, color="#16a34a", lw=1.4,
                   label=f"Call Wall {b.call_wall.strike:.1f}")
        ax.axhline(b.put_wall.strike, color="#dc2626", lw=1.4,
                   label=f"Put Wall {b.put_wall.strike:.1f}")
        ax.axhline(magnet, color="#a855f7", ls="--", lw=1.8,
                   label=f"Magnet (GEX) {magnet:.1f}")
        if b.has_gex and b.gex_magnet_strike is not None:
            ax.axhline(b.gex_magnet_strike, color="darkorange", ls=":", lw=1.6,
                       label=f"GEX Wall {b.gex_magnet_strike:.1f}")
        if b.has_gex and b.gamma_flip is not None:
            ax.axhline(b.gamma_flip, color="teal", ls="-.", lw=1.4,
                       label=f"γ-Flip {b.gamma_flip:.1f}")
        ax.scatter([1], [spot], color=spot_color, zorder=5, label=f"Spot {spot:.1f}")
        regime = ("  ·  +GEX" if b.total_gex >= 0 else "  ·  −GEX") if b.has_gex else ""
        ax.set_title(f"{b.label}  (exp {b.expiration.isoformat()}, {b.actual_dte}d){regime}",
                     color=fg)
        ax.set_ylabel("Price", color=fg)
        ax.tick_params(colors=fg)
        for spine in ax.spines.values():
            spine.set_color(grid)
        leg = ax.legend(fontsize=7, loc="best", facecolor=bg, edgecolor=grid)
        for text in leg.get_texts():
            text.set_color(fg)

    for ax in axes[len(buckets):]:
        ax.set_axis_off()

    fig.suptitle("Projected price distribution by DTE bucket (spot ±σ, with GEX levels)",
                 fontsize=13, color=fg)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig
