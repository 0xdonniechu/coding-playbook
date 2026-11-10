# Positioning matrix and chart

Use the positioning chart only when a common rubric and a comparable annual price can be documented for the selected products. The chart is a heuristic for comparing breadth and price efficiency; it does not measure product quality, satisfaction, outcomes, retention, or market demand. Do not draw a highlighted “open space” unless the evidence supports that interpretation; otherwise omit `highlight_zone`.

## Build the rubric

1. Choose a decision-relevant set of capability categories before scoring vendors (often 8–15; fewer or more may fit the market). Use the same definitions for all products and include the rubric in the report.
2. Score each category `1` only when first-party docs or a reproducible product test support it, `0.5` when coverage is partial or conditional, and `0` only when evidence supports a genuine lack of coverage. Record `?` when evidence is insufficient.
3. The chart script accepts a numeric total, so do not silently treat `?` as zero. If missing categories could materially change a point, exclude the product from the plot or show a min–max range in the report instead of a single point. Record per-category evidence and coding rationale in the report/companion table.
4. Use direct competitor product tiers and the smallest relevant standard package. State included accounts, seats, devices, credits, usage, limits, setup fees, discounts, tax, region and renewal price. Preserve the target buyer's currency/region; use a common currency only with a dated, sourced FX rate.
5. Annualize transparently: use renewal price when the first year is discounted; use a currently available price rather than a crossed-out anchor when no real end date is given; divide perpetual license price by an explicitly chosen useful life (the provided example uses three years, which is a convention, not a fact). Exclude a product if no defensible comparable basis exists.
6. Chart X is covered rubric points; chart Y is rubric points per $10/year. This ratio can favor low-cost narrow tools and can be distorted by category choice, package mismatch, or unknown features. Show the underlying matrix and price table alongside the plot; never present its ordering as an overall winner ranking.
7. A user's proposed product points/prices are scenario inputs. Label candidate prices and capability sets as assumptions; do not present them as validated positioning or evidence of demand.

## Generate

The bundled script uses only the Python standard library:

```bash
python3 assets/positioning_chart.py assets/positioning_example.json --out positioning.svg --inline positioning.inline.svg --table positioning.md
```

`--out` creates a standalone SVG; `--inline` creates a themeable SVG for HTML; `--table` creates a descriptive sorted score table. Keep the full rubric, source URLs, access dates and pricing basis in the report. The example JSON is a format illustration only; its dated sample values are not a current market dataset. Replace all example values before publishing research.
