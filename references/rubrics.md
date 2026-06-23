# Rubrics

## Open Answer Scale

Score open answers by level, not by exact match.

| Level | Meaning | Observable Evidence |
| ---: | --- | --- |
| 0 | 答非所问或核心概念错误 | Misstates the concept, empty answer, or contradicts source. |
| 1 | 只复述材料 | Repeats terms but gives no mechanism or condition. |
| 2 | 能解释原文，但缺少边界 | Explains the source case but cannot state failure cases. |
| 3 | 能迁移到新场景 | Applies the concept with some tradeoffs or steps. |
| 4 | 能识别反例、风险、限制和错误理解 | Includes mechanism, boundary, counterexample, validation, and a realistic action. |

## Judge Output Contract

For every open question, output:

```json
{
  "question_id": "q05",
  "score": 3,
  "max_score": 4,
  "rubric_level": 3,
  "evidence": ["Specific phrase from learner answer"],
  "deduction_reason": "What is missing and why it matters",
  "mistake_tag": "boundary_blindness",
  "improvement": "Concrete next step",
  "learn_from": {
    "knowledge_point": "Concept name",
    "source_segment_id": "source segment id",
    "source_excerpt": "Short source excerpt",
    "suggested_action": "What to review next"
  }
}
```

## Scoring Rules

- Evidence before score.
- Penalize confident but unsupported answers.
- Penalize long answers that do not answer mechanism, boundary, or transfer.
- Do not give level 4 without a counterexample or failure signal.
- If source evidence is unavailable, mark the question as invalid instead of guessing.
- For every wrong answer, point the learner back to a knowledge point, source segment, or research note section.

## Agent Judge Bias Controls

- Do not prefer longer answers.
- Do not prefer confident tone.
- Do not reward repeating the material without explaining it.
- Use the same rubric level boundaries across the whole exam.
- When uncertain between two adjacent levels, choose the lower level and explain what would raise it.
