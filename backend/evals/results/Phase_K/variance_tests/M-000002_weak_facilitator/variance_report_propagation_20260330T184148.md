# Editor→Judge Propagation Report

**Pre-editor input**: `run_001_20260330T181147`  
**Model**: `gpt-5.4`  
**Editor variants judged**: 10/10  
**Coached patterns**: 9

Each variant = same 1st-pass output, different editor run, judged once.
Measures whether editor flip decisions change judge ratings.

---

## Overall

- **Rating unanimous rate**: 77.8% (7/9 patterns same across all variants)
- Coaching value: {'medium': 10}
- Would approve: {'True': 10}

## Per-Pattern Rating Distribution (across editor variants)

| Pattern | Insightful | Adequate | Pedantic | Wrong |
|---------|-----------|----------|----------|-------|
| purposeful_framing | 10 | 0 | 0 | 0 |
| focus_management | 10 | 0 | 0 | 0 |
| participation_management | 0 | 9 | 0 | 0 |
| disagreement_navigation | 10 | 0 | 0 | 0 |
| trust_and_credibility | 10 | 0 | 0 | 0 |
| resolution_and_alignment | 9 | 1 | 0 | 0 |
| assignment_clarity | 1 | 7 | 0 | 0 |
| question_quality | 0 | 10 | 0 | 0 |
| communication_clarity | 0 | 10 | 0 | 0 |

## Propagation Details (editor action → judge rating)

### resolution_and_alignment

| Variant | Editor notes | Editor cnote | Judge rating |
|---------|-------------|-------------|-------------|
| 1 | suppress | pass | insightful |
| 2 | rewrite | pass | insightful |
| 3 | suppress | pass | insightful |
| 4 | rewrite | pass | insightful |
| 5 | pass | pass | insightful |
| 6 | rewrite | pass | adequate |
| 7 | pass | pass | insightful |
| 8 | suppress | pass | insightful |
| 9 | suppress | pass | insightful |
| 10 | pass | pass | insightful |

### assignment_clarity

| Variant | Editor notes | Editor cnote | Judge rating |
|---------|-------------|-------------|-------------|
| 1 | suppress | suppress | n/a |
| 2 | suppress | pass | adequate |
| 3 | suppress | rewrite | adequate |
| 4 | rewrite | rewrite | adequate |
| 5 | suppress | rewrite | adequate |
| 6 | suppress | rewrite | insightful |
| 7 | suppress | pass | adequate |
| 8 | suppress | pass | adequate |
| 9 | suppress | pass | adequate |
| 10 | suppress | suppress | n/a |

## Aggregate (mean +/- stdev across variants)

- **Insightful**: 57.6% +/- 3.4%
- **Adequate**: 42.4% +/- 3.4%
- **Pedantic**: 0.0% +/- 0.0%
- **Wrong**: 0.0% +/- 0.0%
