# Editor→Judge Propagation Report

**Pre-editor input**: `run_001_20260330T180655`  
**Model**: `gpt-5.4`  
**Editor variants judged**: 10/10  
**Coached patterns**: 8

Each variant = same 1st-pass output, different editor run, judged once.
Measures whether editor flip decisions change judge ratings.

---

## Overall

- **Rating unanimous rate**: 37.5% (3/8 patterns same across all variants)
- Coaching value: {'medium': 10}
- Would approve: {'True': 10}

## Per-Pattern Rating Distribution (across editor variants)

| Pattern | Insightful | Adequate | Pedantic | Wrong |
|---------|-----------|----------|----------|-------|
| purposeful_framing | 3 | 7 | 0 | 0 |
| focus_management | 10 | 0 | 0 | 0 |
| participation_management | 2 | 8 | 0 | 0 |
| disagreement_navigation | 0 | 10 | 0 | 0 |
| resolution_and_alignment | 0 | 1 | 9 | 0 |
| assignment_clarity | 0 | 10 | 0 | 0 |
| question_quality | 8 | 2 | 0 | 0 |
| communication_clarity | 1 | 9 | 0 | 0 |

## Propagation Details (editor action → judge rating)

### purposeful_framing

| Variant | Editor notes | Editor cnote | Judge rating |
|---------|-------------|-------------|-------------|
| 1 | pass | pass | adequate |
| 2 | pass | pass | insightful |
| 3 | pass | pass | adequate |
| 4 | pass | pass | insightful |
| 5 | pass | pass | adequate |
| 6 | pass | pass | insightful |
| 7 | pass | pass | adequate |
| 8 | pass | pass | adequate |
| 9 | pass | pass | adequate |
| 10 | pass | pass | adequate |

### participation_management

| Variant | Editor notes | Editor cnote | Judge rating |
|---------|-------------|-------------|-------------|
| 1 | pass | pass | adequate |
| 2 | pass | pass | adequate |
| 3 | pass | pass | adequate |
| 4 | pass | pass | insightful |
| 5 | pass | pass | adequate |
| 6 | pass | pass | insightful |
| 7 | pass | pass | adequate |
| 8 | pass | pass | adequate |
| 9 | pass | pass | adequate |
| 10 | pass | pass | adequate |

### resolution_and_alignment

| Variant | Editor notes | Editor cnote | Judge rating |
|---------|-------------|-------------|-------------|
| 1 | pass | pass | pedantic |
| 2 | pass | pass | pedantic |
| 3 | pass | pass | pedantic |
| 4 | pass | pass | adequate |
| 5 | pass | pass | pedantic |
| 6 | pass | pass | pedantic |
| 7 | pass | pass | pedantic |
| 8 | pass | pass | pedantic |
| 9 | pass | pass | pedantic |
| 10 | pass | pass | pedantic |

### question_quality

| Variant | Editor notes | Editor cnote | Judge rating |
|---------|-------------|-------------|-------------|
| 1 | pass | pass | insightful |
| 2 | pass | pass | insightful |
| 3 | pass | pass | insightful |
| 4 | pass | pass | insightful |
| 5 | pass | pass | insightful |
| 6 | pass | pass | insightful |
| 7 | pass | pass | insightful |
| 8 | pass | pass | adequate |
| 9 | pass | pass | insightful |
| 10 | pass | pass | adequate |

### communication_clarity

| Variant | Editor notes | Editor cnote | Judge rating |
|---------|-------------|-------------|-------------|
| 1 | pass | pass | adequate |
| 2 | pass | pass | adequate |
| 3 | pass | pass | adequate |
| 4 | pass | pass | insightful |
| 5 | pass | pass | adequate |
| 6 | pass | pass | adequate |
| 7 | pass | pass | adequate |
| 8 | pass | pass | adequate |
| 9 | pass | pass | adequate |
| 10 | pass | pass | adequate |

## Aggregate (mean +/- stdev across variants)

- **Insightful**: 30.0% +/- 15.8%
- **Adequate**: 58.8% +/- 13.2%
- **Pedantic**: 11.2% +/- 4.0%
- **Wrong**: 0.0% +/- 0.0%
