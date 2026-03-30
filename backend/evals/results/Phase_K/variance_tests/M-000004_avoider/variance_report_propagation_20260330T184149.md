# Editor→Judge Propagation Report

**Pre-editor input**: `run_001_20260330T181150`  
**Model**: `gpt-5.4`  
**Editor variants judged**: 10/10  
**Coached patterns**: 6

Each variant = same 1st-pass output, different editor run, judged once.
Measures whether editor flip decisions change judge ratings.

---

## Overall

- **Rating unanimous rate**: 100.0% (6/6 patterns same across all variants)
- Coaching value: {'medium': 10}
- Would approve: {'True': 10}

## Per-Pattern Rating Distribution (across editor variants)

| Pattern | Insightful | Adequate | Pedantic | Wrong |
|---------|-----------|----------|----------|-------|
| purposeful_framing | 0 | 10 | 0 | 0 |
| disagreement_navigation | 10 | 0 | 0 | 0 |
| trust_and_credibility | 10 | 0 | 0 | 0 |
| resolution_and_alignment | 0 | 10 | 0 | 0 |
| assignment_clarity | 0 | 10 | 0 | 0 |
| communication_clarity | 0 | 0 | 6 | 0 |

## Propagation Details

No rating changes across editor variants — editor variance does not propagate.

## Aggregate (mean +/- stdev across variants)

- **Insightful**: 36.0% +/- 3.4%
- **Adequate**: 54.0% +/- 5.2%
- **Pedantic**: 10.0% +/- 8.6%
- **Wrong**: 0.0% +/- 0.0%
