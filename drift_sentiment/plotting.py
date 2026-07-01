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


def build_box_plots(buckets: list[BucketResult], spot: float):
    """Return a matplotlib Figure with 4 box plots (one per DTE bucket).

    Each box spans ±1 sigma (q1..q3) with whiskers at ±3 sigma, median at spot.
    Call Wall (green), Put Wall (red), Magnet/GEX blend (purple dashed), GEX Wall
    (orange dotted), and γ-Flip (teal dash-dot) are marked.
    """
    n = len(buckets)
    cols = 2
    rows = max(1, (n + cols - 1) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(11, 4.5 * rows))
    axes = axes.flatten() if n > 1 else [axes]

    for ax, b in zip(axes, buckets):
        stats = _bucket_box_stats(b, spot)
        if stats is None:
            ax.text(0.5, 0.5, f"{b.label}\n(no IV data)", ha="center", va="center")
            ax.set_axis_off()
            continue

        ax.bxp([stats], showfliers=False, patch_artist=True,
               boxprops=dict(facecolor="#cfe3ff", edgecolor="#3a7bd5"))
        magnet = b.blended_magnet_strike if b.blended_magnet_strike is not None else b.magneto_strike
        ax.axhline(b.call_wall.strike, color="green", lw=1.4,
                   label=f"Call Wall {b.call_wall.strike:.1f}")
        ax.axhline(b.put_wall.strike, color="red", lw=1.4,
                   label=f"Put Wall {b.put_wall.strike:.1f}")
        ax.axhline(magnet, color="purple", ls="--", lw=1.8,
                   label=f"Magnet (GEX) {magnet:.1f}")
        if b.has_gex and b.gex_magnet_strike is not None:
            ax.axhline(b.gex_magnet_strike, color="darkorange", ls=":", lw=1.6,
                       label=f"GEX Wall {b.gex_magnet_strike:.1f}")
        if b.has_gex and b.gamma_flip is not None:
            ax.axhline(b.gamma_flip, color="teal", ls="-.", lw=1.4,
                       label=f"γ-Flip {b.gamma_flip:.1f}")
        ax.scatter([1], [spot], color="black", zorder=5, label=f"Spot {spot:.1f}")
        regime = ("  ·  +GEX" if b.total_gex >= 0 else "  ·  −GEX") if b.has_gex else ""
        ax.set_title(f"{b.label}  (exp {b.expiration.isoformat()}, {b.actual_dte}d){regime}")
        ax.set_ylabel("Price")
        ax.legend(fontsize=7, loc="best")

    for ax in axes[len(buckets):]:
        ax.set_axis_off()

    fig.suptitle("Projected price distribution by DTE bucket (spot ±σ, with GEX levels)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig
