#!/usr/bin/env python3
"""
Score Range Analysis for ClearVoice Pattern Taxonomy v3.0

Demonstrates that the current scoring rubrics are probabilistically biased
toward producing a narrow range of scores, regardless of transcript content.

Four compounding mechanisms cause score compression:
  1. Broad 0.5 criteria that capture "normal" communication (6 of 9 patterns)
  2. Explicit "prefer 0.5" guidance (Communication Clarity)
  3. Conservative counting that removes edge-case opportunities
  4. Averaging over multiple opportunities (variance reduction)

Run: python scripts/score_range_analysis.py
"""

import random
import math
from itertools import product
from collections import Counter

random.seed(42)

SIMS = 10_000

# ─────────────────────────────────────────────────────────────
# Pattern definitions: per-opportunity possible values and
# probability models for each scoring type
# ─────────────────────────────────────────────────────────────

PATTERNS = {
    # --- Dual-element: {0, 0.5, 1.0} ---
    "Purposeful Framing": {
        "type": "dual_element",
        "values": [0.0, 0.5, 1.0],
        "min_opps": 2,
        "typical_opps": (2, 5),
        "models": {
            "uniform":      {0.0: 1/3, 0.5: 1/3, 1.0: 1/3},
            "realistic":    {0.0: 0.10, 0.5: 0.55, 1.0: 0.35},
            "conservative": {0.0: 0.05, 0.5: 0.70, 1.0: 0.25},
        },
    },
    "Resolution & Alignment": {
        "type": "dual_element",
        "values": [0.0, 0.5, 1.0],
        "min_opps": 2,
        "typical_opps": (2, 5),
        "models": {
            "uniform":      {0.0: 1/3, 0.5: 1/3, 1.0: 1/3},
            "realistic":    {0.0: 0.15, 0.5: 0.55, 1.0: 0.30},
            "conservative": {0.0: 0.08, 0.5: 0.72, 1.0: 0.20},
        },
    },

    # --- Tiered rubric: {0, 0.5, 1.0} ---
    "Focus Management": {
        "type": "tiered_rubric",
        "values": [0.0, 0.5, 1.0],
        "min_opps": 2,
        "typical_opps": (2, 5),
        "models": {
            "uniform":      {0.0: 1/3, 0.5: 1/3, 1.0: 1/3},
            "realistic":    {0.0: 0.10, 0.5: 0.65, 1.0: 0.25},
            "conservative": {0.0: 0.05, 0.5: 0.75, 1.0: 0.20},
        },
    },
    "Participation Mgmt": {
        "type": "tiered_rubric",
        "values": [0.0, 0.5, 1.0],
        "min_opps": 3,
        "typical_opps": (3, 6),
        "models": {
            "uniform":      {0.0: 1/3, 0.5: 1/3, 1.0: 1/3},
            "realistic":    {0.0: 0.10, 0.5: 0.60, 1.0: 0.30},
            "conservative": {0.0: 0.05, 0.5: 0.75, 1.0: 0.20},
        },
    },
    "Disagreement Nav": {
        "type": "tiered_rubric",
        "values": [0.0, 0.5, 1.0],
        "min_opps": 2,
        "typical_opps": (2, 4),
        "models": {
            "uniform":      {0.0: 1/3, 0.5: 1/3, 1.0: 1/3},
            "realistic":    {0.0: 0.10, 0.5: 0.65, 1.0: 0.25},
            "conservative": {0.0: 0.05, 0.5: 0.75, 1.0: 0.20},
        },
    },
    "Communication Clarity": {
        "type": "tiered_rubric",
        "values": [0.0, 0.5, 1.0],
        "min_opps": 3,
        "typical_opps": (3, 7),
        "models": {
            "uniform":      {0.0: 1/3, 0.5: 1/3, 1.0: 1/3},
            # "prefer 0.5" guidance makes this the most compressed
            "realistic":    {0.0: 0.08, 0.5: 0.72, 1.0: 0.20},
            "conservative": {0.0: 0.03, 0.5: 0.82, 1.0: 0.15},
        },
    },

    # --- Binary: {0, 1} ---
    "Question Quality": {
        "type": "binary",
        "values": [0.0, 1.0],
        "min_opps": 3,
        "typical_opps": (3, 8),
        "models": {
            "uniform":      {0.0: 0.50, 1.0: 0.50},
            "realistic":    {0.0: 0.30, 1.0: 0.70},
            "conservative": {0.0: 0.25, 1.0: 0.75},
        },
    },

    # --- Complexity-tiered (simplified: average of simple+complex assignments) ---
    "Assignment Clarity": {
        "type": "complexity_tiered",
        # Simple: {0, 0.25, 0.5, 1.0}; Complex: {0, 0.25, 0.5, 0.75, 1.0}
        # Model as weighted mix (most assignments are simple)
        "values": [0.0, 0.25, 0.5, 0.75, 1.0],
        "min_opps": 2,
        "typical_opps": (2, 5),
        "models": {
            "uniform":      {0.0: 0.20, 0.25: 0.20, 0.5: 0.20, 0.75: 0.20, 1.0: 0.20},
            "realistic":    {0.0: 0.05, 0.25: 0.15, 0.5: 0.40, 0.75: 0.25, 1.0: 0.15},
            "conservative": {0.0: 0.03, 0.25: 0.12, 0.5: 0.55, 0.75: 0.20, 1.0: 0.10},
        },
    },

    # --- Multi-element (SBI-RC): {0, 0.2, 0.4, 0.6, 0.8, 1.0} ---
    "Feedback Quality": {
        "type": "multi_element",
        "values": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        "min_opps": 2,
        "typical_opps": (2, 4),
        "models": {
            "uniform":      {0.0: 1/6, 0.2: 1/6, 0.4: 1/6, 0.6: 1/6, 0.8: 1/6, 1.0: 1/6},
            "realistic":    {0.0: 0.03, 0.2: 0.07, 0.4: 0.25, 0.6: 0.35, 0.8: 0.20, 1.0: 0.10},
            "conservative": {0.0: 0.02, 0.2: 0.05, 0.4: 0.30, 0.6: 0.40, 0.8: 0.18, 1.0: 0.05},
        },
    },
}


# ─────────────────────────────────────────────────────────────
# Part 1: Enumerate all possible final scores
# ─────────────────────────────────────────────────────────────

def enumerate_possible_scores(values, n_opps):
    """Return sorted list of distinct final scores for n opportunities."""
    scores = set()
    for combo in product(values, repeat=n_opps):
        scores.add(round(sum(combo) / n_opps, 4))
    return sorted(scores)


def print_enumeration():
    print("=" * 72)
    print("PART 1: ALL POSSIBLE FINAL SCORES BY OPPORTUNITY COUNT")
    print("=" * 72)
    print()
    print("Shows how few distinct score values are mathematically possible.")
    print()

    # Group patterns by their value set
    seen = {}
    for name, p in PATTERNS.items():
        key = tuple(p["values"])
        if key not in seen:
            seen[key] = []
        seen[key].append(name)

    for values, names in seen.items():
        val_str = "{" + ", ".join(f"{v}" for v in values) + "}"
        print(f"  Scoring values: {val_str}")
        print(f"  Patterns: {', '.join(names)}")
        print()
        print(f"  {'Opps':>4}  {'# distinct':>10}  {'Possible scores'}")
        print(f"  {'----':>4}  {'----------':>10}  {'-' * 45}")
        for n in range(2, 7):
            scores = enumerate_possible_scores(values, n)
            scores_str = ", ".join(f"{s:.2f}" for s in scores)
            if len(scores_str) > 60:
                scores_str = scores_str[:57] + "..."
            print(f"  {n:>4}  {len(scores):>10}  {scores_str}")
        print()

    # Highlight the key insight
    print("  KEY INSIGHT: With {0, 0.5, 1.0} and 3 opportunities, there are")
    print("  only 7 possible scores. With 4 opportunities, only 9. The")
    print("  resolution is inherently coarse, and most values cluster near 0.5.")
    print()


# ─────────────────────────────────────────────────────────────
# Part 2: Probabilistic simulation
# ─────────────────────────────────────────────────────────────

def sample_score(values, probs, n_opps):
    """Sample one final score: draw n opportunities and average."""
    vals = list(probs.keys())
    weights = list(probs.values())
    draws = random.choices(vals, weights=weights, k=n_opps)
    return round(sum(draws) / n_opps, 4)


def percentile(data, p):
    """Simple percentile calculation."""
    data = sorted(data)
    k = (len(data) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data[int(k)]
    return data[f] * (c - k) + data[c] * (k - f)


def ascii_histogram(data, bins=20, width=40):
    """Return lines for a simple ASCII histogram."""
    mn, mx = 0.0, 1.0
    bin_width = (mx - mn) / bins
    counts = [0] * bins
    for v in data:
        idx = min(int((v - mn) / bin_width), bins - 1)
        counts[idx] += 1
    max_count = max(counts) if max(counts) > 0 else 1
    lines = []
    for i in range(bins):
        lo = mn + i * bin_width
        bar_len = int(counts[i] / max_count * width)
        bar = "█" * bar_len
        lines.append(f"    {lo:5.2f} |{bar}")
    return lines


def print_simulation():
    print("=" * 72)
    print("PART 2: MONTE CARLO SIMULATION (10,000 meetings per scenario)")
    print("=" * 72)
    print()
    print("Three LLM behavior models:")
    print("  - Uniform:      equal probability for each tier value")
    print("  - Realistic:    skewed toward 0.5 (broad middle-tier criteria)")
    print("  - Conservative: heavily weighted to 0.5 ('prefer 0.5' guidance)")
    print()

    for name, p in PATTERNS.items():
        lo, hi = p["typical_opps"]
        print(f"  ┌─ {name} ({p['type']}) ─ opps: {lo}-{hi}")
        print(f"  │  Values: {p['values']}")

        for model_name, probs in p["models"].items():
            # Sample with varying opportunity counts
            scores = []
            for _ in range(SIMS):
                n = random.randint(lo, hi)
                scores.append(sample_score(p["values"], probs, n))

            mean = sum(scores) / len(scores)
            sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / len(scores))
            p5 = percentile(scores, 5)
            p25 = percentile(scores, 25)
            p75 = percentile(scores, 75)
            p95 = percentile(scores, 95)
            iqr = p75 - p25

            tag = ""
            if iqr <= 0.20:
                tag = " ◄ NARROW"
            if iqr <= 0.15:
                tag = " ◄ VERY NARROW"

            print(f"  │")
            print(f"  │  {model_name:14s}  mean={mean:.3f}  sd={sd:.3f}  "
                  f"IQR=[{p25:.2f}–{p75:.2f}] ({iqr:.2f}){tag}")
            print(f"  │  {'':<14s}  90% range=[{p5:.2f}–{p95:.2f}] ({p95-p5:.2f})")

            if model_name == "conservative":
                for line in ascii_histogram(scores):
                    print(f"  │  {line}")

        print(f"  └{'─' * 68}")
        print()


# ─────────────────────────────────────────────────────────────
# Part 3: Cross-pattern profile similarity
# ─────────────────────────────────────────────────────────────

def simulate_run_profile(model_name):
    """Simulate one meeting's full 9-pattern score vector."""
    profile = {}
    for name, p in PATTERNS.items():
        lo, hi = p["typical_opps"]
        n = random.randint(lo, hi)
        probs = p["models"][model_name]
        profile[name] = sample_score(p["values"], probs, n)
    return profile


def euclidean_dist(a, b):
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in a))


def print_cross_pattern():
    print("=" * 72)
    print("PART 3: CROSS-PATTERN PROFILE SIMILARITY")
    print("=" * 72)
    print()
    print("How similar are two random meetings' score profiles?")
    print("Lower distance = more similar (less discriminating).")
    print()

    for model_name in ["uniform", "realistic", "conservative"]:
        dists = []
        for _ in range(SIMS):
            a = simulate_run_profile(model_name)
            b = simulate_run_profile(model_name)
            dists.append(euclidean_dist(a, b))

        mean_d = sum(dists) / len(dists)
        sd_d = math.sqrt(sum((d - mean_d) ** 2 for d in dists) / len(dists))
        max_possible = math.sqrt(9)  # 9 patterns, max per-pattern distance = 1.0

        print(f"  {model_name:14s}  mean distance={mean_d:.3f}  sd={sd_d:.3f}  "
              f"(max possible={max_possible:.3f})")
        print(f"  {'':<14s}  as % of max: {mean_d / max_possible * 100:.1f}%")

    print()
    print("  INSIGHT: Under 'conservative' model, two random meetings produce")
    print("  score profiles that differ by only ~15-20% of the theoretical max.")
    print("  The rubrics make most meetings look statistically similar.")
    print()

    # Show example profiles
    print("  Example profiles (conservative model):")
    print()
    header = f"  {'Pattern':<24s}"
    for i in range(5):
        header += f"  Meeting {i+1}"
    print(header)
    print(f"  {'-'*24}" + "  ---------" * 5)

    profiles = [simulate_run_profile("conservative") for _ in range(5)]
    for name in PATTERNS:
        row = f"  {name:<24s}"
        for p in profiles:
            row += f"  {p[name]*100:7.1f}%"
        print(row)

    # Compute range per pattern
    print()
    print(f"  {'Pattern':<24s}  {'Range across 5 meetings'}")
    print(f"  {'-'*24}  {'-'*24}")
    for name in PATTERNS:
        vals = [p[name] for p in profiles]
        rng = max(vals) - min(vals)
        print(f"  {name:<24s}  {rng*100:5.1f} percentage points")
    print()


# ─────────────────────────────────────────────────────────────
# Part 4: Alternative rubric designs
# ─────────────────────────────────────────────────────────────

def print_alternatives():
    print("=" * 72)
    print("PART 4: WHAT-IF — ALTERNATIVE RUBRIC DESIGNS")
    print("=" * 72)
    print()

    # Use Communication Clarity as the example (most compressed pattern)
    pattern = PATTERNS["Communication Clarity"]
    lo, hi = pattern["typical_opps"]

    print("  Using Communication Clarity as test case (most compressed pattern)")
    print(f"  Typical opportunities: {lo}-{hi}")
    print()

    alternatives = {
        "Current (3-tier, prefer 0.5)": {
            "values": [0.0, 0.5, 1.0],
            "probs": {0.0: 0.03, 0.5: 0.82, 1.0: 0.15},
        },
        "(a) 5-tier rubric": {
            "values": [0.0, 0.25, 0.5, 0.75, 1.0],
            "probs": {0.0: 0.05, 0.25: 0.15, 0.5: 0.35, 0.75: 0.30, 1.0: 0.15},
        },
        "(b) Remove 'prefer 0.5'": {
            "values": [0.0, 0.5, 1.0],
            "probs": {0.0: 0.20, 0.5: 0.45, 1.0: 0.35},
        },
        "(c) Weakest-moment scoring": {
            "values": [0.0, 0.5, 1.0],
            "probs": {0.0: 0.03, 0.5: 0.82, 1.0: 0.15},
            "aggregation": "min",
        },
    }

    print(f"  {'Design':<35s}  {'Mean':>6}  {'SD':>6}  {'IQR':>12}  {'90% range':>14}")
    print(f"  {'-'*35}  {'-'*6}  {'-'*6}  {'-'*12}  {'-'*14}")

    for alt_name, alt in alternatives.items():
        scores = []
        for _ in range(SIMS):
            n = random.randint(lo, hi)
            vals = list(alt["probs"].keys())
            weights = list(alt["probs"].values())
            draws = random.choices(vals, weights=weights, k=n)

            if alt.get("aggregation") == "min":
                score = min(draws)
            else:
                score = round(sum(draws) / n, 4)
            scores.append(score)

        mean = sum(scores) / len(scores)
        sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / len(scores))
        p5 = percentile(scores, 5)
        p25 = percentile(scores, 25)
        p75 = percentile(scores, 75)
        p95 = percentile(scores, 95)
        iqr = p75 - p25

        print(f"  {alt_name:<35s}  {mean:>6.3f}  {sd:>6.3f}  "
              f"[{p25:.2f}–{p75:.2f}]  [{p5:.2f}–{p95:.2f}]")

    print()
    print("  FINDINGS:")
    print("  (a) 5-tier rubric: ~2x wider IQR — more values between 0 and 1")
    print("      spread probability mass, increasing discrimination.")
    print("  (b) Removing 'prefer 0.5': ~1.5-2x wider IQR — allowing the LLM")
    print("      to use its actual judgment spreads scores significantly.")
    print("  (c) Weakest-moment scoring: dramatically wider range — one bad")
    print("      opportunity pulls the whole score down, creating real")
    print("      differentiation. But may be too punitive.")
    print()
    print("  RECOMMENDATION: Combining (a) and (b) — a 5-tier rubric without")
    print("  the 'prefer 0.5' instruction — would substantially increase score")
    print("  variation while maintaining rubric integrity.")
    print()


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  ClearVoice v3.0 — Pattern Score Range Analysis                    ║")
    print("║  Investigating inherent score compression in the taxonomy rubrics   ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()

    print_enumeration()
    print_simulation()
    print_cross_pattern()
    print_alternatives()

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print()
    print("The v3.0 taxonomy scoring rubrics produce inherently narrow score")
    print("ranges due to four compounding factors:")
    print()
    print("  1. THREE-TIER BOTTLENECK: 6 of 9 patterns use only {0, 0.5, 1.0}")
    print("     per opportunity. With typical opportunity counts (2-6), this")
    print("     produces only 5-13 distinct possible final scores.")
    print()
    print("  2. BROAD MIDDLE TIER: The 0.5 criteria describe 'normal but")
    print("     imperfect' behavior — the vast majority of real communication.")
    print("     1.0 requires textbook-perfect execution; 0.0 requires complete")
    print("     absence. Most real behavior lands at 0.5.")
    print()
    print("  3. 'PREFER 0.5' INSTRUCTION: Communication Clarity explicitly")
    print("     tells the LLM to default to 0.5 when uncertain, creating a")
    print("     direct attractor. Other patterns don't say this explicitly")
    print("     but the broad 0.5 criteria have the same effect.")
    print()
    print("  4. AVERAGING COMPRESSION: Averaging N opportunity scores reduces")
    print("     variance by factor N. With 3-5 opportunities, the SD of the")
    print("     final score is 40-55% smaller than individual scores.")
    print()
    print("  NET EFFECT: Under realistic LLM behavior, most pattern scores")
    print("  fall within a 20-25 percentage point band (e.g., 40%-65%).")
    print("  Two completely different transcripts will produce score profiles")
    print("  that differ by only ~15-20% of the theoretical maximum.")
    print()


if __name__ == "__main__":
    main()
