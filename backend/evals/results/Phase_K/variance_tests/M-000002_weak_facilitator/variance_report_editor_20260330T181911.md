# Editor Variance Report

**Input**: `run_001_20260330T181147`  
**Model**: `gpt-5.4`  
**Runs**: 10/10 valid  
**Evaluable patterns**: 9

---

## Overall Consistency

- **Unanimous rate**: 61.1% (11/18 pattern+field decisions)
- Executive summary changed: 40% of runs
- Coaching themes changed: 0% of runs
- Focus message changed: 60% of runs
- Changes/run: min=3, max=11, mean=7.4

## Per-Pattern Action Distribution

| Pattern | Notes:sup | Notes:rew | Notes:pass | CNote:sup | CNote:rew | CNote:pass |
|---------|-----------|-----------|------------|-----------|-----------|------------|
| purposeful_framing | 6 | 0 | 4 | 0 | 0 | 10 |
| focus_management | 0 | 0 | 10 | 0 | 0 | 10 |
| participation_management | 8 | 0 | 2 | 1 | 1 | 8 |
| disagreement_navigation | 0 | 0 | 10 | 0 | 0 | 10 |
| trust_and_credibility | 0 | 0 | 10 | 0 | 0 | 10 |
| resolution_and_alignment | 4 | 3 | 3 | 0 | 0 | 10 |
| assignment_clarity | 9 | 1 | 0 | 2 | 4 | 4 |
| question_quality | 0 | 0 | 10 | 0 | 0 | 10 |
| communication_clarity | 1 | 0 | 9 | 0 | 0 | 10 |

## Flip Patterns (mixed decisions)

| Pattern | Field | Distribution |
|---------|-------|-------------|
| purposeful_framing | notes | pass=4, suppress=6 |
| participation_management | notes | pass=2, suppress=8 |
| participation_management | coaching_note | pass=8, rewrite=1, suppress=1 |
| resolution_and_alignment | notes | pass=3, rewrite=3, suppress=4 |
| assignment_clarity | notes | rewrite=1, suppress=9 |
| assignment_clarity | coaching_note | pass=4, rewrite=4, suppress=2 |
| communication_clarity | notes | pass=9, suppress=1 |

## OE Removal Agreement

Overall agreement rate: 0.0%

| Pattern | OE Index | Flagged In |
|---------|----------|-----------|
| assignment_clarity | 5 | 4/10 |
| assignment_clarity | 7 | 3/10 |
| assignment_clarity | 8 | 2/10 |
| resolution_and_alignment | 0 | 2/10 |
| resolution_and_alignment | 4 | 6/10 |
