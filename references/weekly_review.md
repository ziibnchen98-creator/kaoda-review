# Weekly Review

Weekly exams are synthesis exams, not old-question bundles.

## Inputs

Read:

- `data/learners/<learner_id>/mistake_bank.jsonl`
- Recent `grade.json` files when available
- Recent `material_report.json` files when available

## Default Mix

- 60% weak-point variants from mistake bank.
- 25% core knowledge from this week's materials.
- 15% high-transfer challenge questions.

## Generation Rules

- Do not reuse old question text.
- Do not reuse the same scenario consecutively.
- Do not use the same question type more than 2 times in a row.
- Keep the same knowledge point if it is weak, but change task, angle, or scenario.
- Prefer real application, failure diagnosis, and decision scenarios over recall.

## Weekly Report

The weekly report must include:

- Top 3 "most fake-understood" areas.
- Mistake tag distribution.
- High-frequency knowledge points.
- Next-week review advice.
- Evidence that questions were generated from weak points, not copied from old exams.
