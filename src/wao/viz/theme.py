"""P26: shared chart theme (light and dark), ported from Project 4 (sod.viz.theme).

Colours are assigned by role and never cycled. Okabe-Ito hues, validated with the dataviz skill's
validate_palette.js (adjacent pairs):
  light  #D55E00 #0072B2 #009E73   pass (worst CVD dE 18.0, normal 18.7)
  dark   #D55E00 #157BBB #009E73   pass (worst CVD dE 16.6, normal 17.4)
Roles: treated editions (vermillion), not-yet-treated / comparison editions (blue), a third
group when needed (green). The counterfactual is not a group, so it is neutral ink (dashed line +
grey band). Text uses ink tokens, never series colours.

Usage:
    from wao.viz import theme
    with theme.use("light"):
        fig, ax = plt.subplots(); ...; theme.save(fig, "hero_a")
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import matplotlib
import matplotlib.pyplot as plt

from wao import config

FONTS = ["Source Sans Pro", "Source Sans 3", "Helvetica Neue", "Arial", "DejaVu Sans"]


@dataclass(frozen=True)
class Palette:
    surface: str
    ink: str
    ink_muted: str
    grid: str
    band: str
    treated: str
    control: str
    third: str
    counterfactual: str


LIGHT = Palette(surface="#FCFCFB", ink="#1F2328", ink_muted="#5B636E", grid="#E6E6E3",
                band="#C9CED6", treated="#D55E00", control="#0072B2", third="#009E73",
                counterfactual="#4A525C")  # fmt: skip
DARK = Palette(surface="#1A1A19", ink="#ECEDEE", ink_muted="#A3A9B1", grid="#34363A",
               band="#4B5058", treated="#D55E00", control="#157BBB", third="#009E73",
               counterfactual="#B9C0C9")  # fmt: skip
PALETTES = {"light": LIGHT, "dark": DARK}
_current = LIGHT


def palette() -> Palette:
    return _current


def rc(p: Palette) -> dict:
    return {
        "font.family": "sans-serif",
        "font.sans-serif": FONTS,
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.labelsize": 10,
        "axes.labelcolor": p.ink_muted,
        "axes.edgecolor": p.ink_muted,
        "axes.facecolor": p.surface,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "grid.color": p.grid,
        "grid.linewidth": 0.8,
        "xtick.color": p.ink_muted,
        "ytick.color": p.ink_muted,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "text.color": p.ink,
        "figure.facecolor": p.surface,
        "savefig.facecolor": p.surface,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "svg.fonttype": "none",  # keep text as text in SVG
    }


@contextlib.contextmanager
def use(mode: str = "light"):
    global _current
    prev = _current
    _current = PALETTES[mode]
    with matplotlib.rc_context(rc(_current)):
        try:
            yield _current
        finally:
            _current = prev


def label_end(ax, x, y, text: str, color: str, dx: float = 6, **kw) -> None:
    """Direct label at a line's end: a colour swatch plus text in ink (never series colour)."""
    p = _current
    ax.annotate("—", (x, y), xytext=(dx, 0), textcoords="offset points", va="center",
                ha="left", color=color, fontsize=12, fontweight="bold",
                annotation_clip=False)  # fmt: skip
    ax.annotate(text, (x, y), xytext=(dx + 14, 0), textcoords="offset points", va="center",
                ha="left", color=p.ink, fontsize=kw.pop("fontsize", 9.5), annotation_clip=False,
                **kw)  # fmt: skip


def event(ax, x, text: str, y: float = 0.98, span_end=None, align: str = "left") -> None:
    """A dotted vertical rule (or a shaded span) with a small muted label near the top."""
    p = _current
    if span_end is not None:
        ax.axvspan(x, span_end, color=p.band, alpha=0.35, lw=0, zorder=0)
    else:
        ax.axvline(x, color=p.ink_muted, lw=0.9, ls=(0, (1, 2)), zorder=1)
    ax.text(x, y, (" " + text) if align == "left" else (text + " "),
            transform=ax.get_xaxis_transform(), va="top", ha=align, fontsize=8.5,
            color=p.ink_muted)  # fmt: skip


def title(fig, text: str, subtitle: str | None = None, x: float = 0.012) -> None:
    """Title and subtitle at fixed distances (inches) from the top, whatever the figure height."""
    p = _current
    h = fig.get_figheight()
    fig.text(x, 1 - 0.16 / h, text, ha="left", va="top", fontsize=15, fontweight="semibold",
             color=p.ink)  # fmt: skip
    if subtitle:
        fig.text(x, 1 - 0.55 / h, subtitle, ha="left", va="top", fontsize=10.5, color=p.ink_muted)


def source(fig, text: str, x: float = 0.012) -> None:
    fig.text(x, 0.015, text, ha="left", va="bottom", fontsize=8, color=_current.ink_muted)


def save(fig, name: str, mode: str | None = None) -> list:
    """Write PNG (200 dpi) and SVG to report/figures; dark versions get a _dark suffix."""
    mode = mode or ("dark" if _current is DARK else "light")
    stem = name if mode == "light" else f"{name}_dark"
    config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    paths = [config.FIGURE_DIR / f"{stem}.png", config.FIGURE_DIR / f"{stem}.svg"]
    fig.savefig(paths[0], dpi=200)
    fig.savefig(paths[1])
    plt.close(fig)
    return paths
