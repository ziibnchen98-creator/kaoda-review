# Weekly Review

Weekly exams are synthesis exams, not old-question bundles.

## Inputs

Read:

- `data/learners/<learner_id>/mistake_bank.jsonl`
- Recent `archive/*/archive_manifest.json`
- Archived `grade.json`, `exam.json`, `source.json`, `material_report.json`, and `deep_research.json`

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
- If fewer than 3 archived sessions are available, explicitly downgrade to a mistake-variant weekly review and do not claim cross-material synthesis.
- `weekly_exam.json` must include `exam_brief`, `review_design`, and `question_sections` so it can pass the normal exam validator.

## Weekly Report

The weekly report must include:

- Top 3 "most fake-understood" areas.
- Mistake tag distribution.
- High-frequency knowledge points.
- Next-week review advice.
- Evidence that questions were generated from weak points, not copied from old exams.
- How many questions came from historical mistakes, current-week material core knowledge, and transfer/synthesis.
