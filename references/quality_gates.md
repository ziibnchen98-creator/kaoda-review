# Quality Gates

Run these checks before presenting a generated review checklist or report.

## Source Integrity

- Every source-derived question has `source.segment_id`.
- Every PDF segment has a page locator.
- Every subtitle segment has timestamp information.
- Article segments have URL locator.
- When video/PDF/article/media extraction is blocked, `source_status.json` and a manual text file exist; no exam is generated until `ingest-manual` creates `segments.jsonl`.
- Local audio/video files use same-name transcript sidecars or manual transcript fallback; file names alone are never source evidence.
- Extension content is marked `extension: true`.
- Topic-only reviews have `topic_research.md` and `source_links.json`; the bare topic string is not treated as source evidence.

## Planning Integrity

- `exam_brief.json` exists before `exam.json`.
- `deep_research.json` exists before `plan-exam`.
- `deep_research.json.research.status` is `completed`.
- Every deep-research item has `mechanism`, `boundary`, `misconception`, `counterexample`, `transfer_scenario`, and non-empty `source_refs`.
- `extended` deep research includes at least one `origin: "extension"` item with a source URL; `source_only` deep research includes no extension items.
- `exam_brief.review_selection.status` is `confirmed`.
- `exam_brief.review_mode` is one of `复盘模式`, `正常模式`, `拷打模式`, or `深度拷打`.
- `exam_brief.duration_minutes` matches the selected mode unless explicitly overridden.
- `exam_brief.question_style` is one of the supported style options.
- `exam_brief.research.status` is `completed`.
- `exam_brief.research.mandatory` is `true`.
- `exam_brief.research.mode` is `extended` or `source_only`.
- Source-only runs do not include `origin: "extension"` research items.
- The exam mode and style match `exam_brief.review_mode` and `exam_brief.question_style` unless the user explicitly changed them after planning.
- Mistake-bank knowledge appears only when `mistake_knowledge.available` is true and the selected policy is not `只复盘当前材料`.

## Review Quality

- No duplicate question prompts.
- Generated reviews stay within 15-50 checkpoints.
- Visible question prompts do not expose internal source-layer labels, style labels, question-type prefixes, or cue sentences.
- Visible prompts do not contain `原文校准｜`, `线索：`, `最稳`, `哪种理解最稳`, `明显是在装懂`, `别急着`, `这题不哄人`, `一眼假`, or `伪理解`.
- Questions are grouped by type in the rendered HTML: single-choice, multiple-choice, true/false, fill-in, then short/oral.
- Objective answer positions are not all the same; single-choice, multiple-choice, and mistake-variant answers should be distributed across option IDs.
- `复盘模式` has no open or fill-in prompts by default and can be fully scored in the browser.
- `正常模式` has no open prompts by default and can be fully scored in the browser.
- `拷打模式` and `深度拷打` may include short/oral prompts and therefore need agent review for open answers.
- Questions rotate style families instead of repeating the same teacher-style prompt shape.
- Fill-in checkpoints include `answer` and, when useful, `accepted_answers`.
- Objective questions have one valid answer for single-choice/true-false and at least one answer for multiple-choice.
- Open questions have rubrics.
- Oral review prompts have `voice_enabled: true` but text input must remain available.
- At least 3 ability types are present.
- The ability types reflect the review mode and source risks.
- At least one question asks for boundary or failure.
- At least one question asks for transfer.
- Explanations say why wrong answers are wrong.

## Grading Quality

- Objective-only reviews produce a complete browser score without requiring a downloaded agent package.
- The visible HTML action flow is simple: before submission only `提交试卷`; after submission only `导出报告给 Agent`.
- Submission asks for confirmation before scoring and switching to the report page.
- After submission, the HTML shows a report with total score, type-level score, wrong questions, weak knowledge points, and next-step instructions.
- The exported Agent report package includes report summary, objective pregrade, full answers, `attempt.json`, `exam.json`, and instructions to generate `grade.json` and run `record`.
- Open-answer reviews clearly say the browser score is an objective pregrade and Agent review is needed for short/oral answers.
- `grade-report <kaoda_agent_report.md>` parses the exported report and writes `attempt.json`, `exam.json`, `grading_prompt.md`, and `grade.json`.
- `grade.json.open_review.status` is `not_required` for objective-only reviews, `pending_agent_review` before open-answer rubric review, or `completed` after Agent review.
- `record` must refuse `pending_agent_review` so heuristic open pregrades are not archived as final scores.
- `record` must also refuse `open_review.status: completed` when any open result still has `score_status: pending_agent_review`.
- Before Agent review, open-question scores are not counted in `score.total`; the total is objective pregrade only and `score.open` is `null`.
- Before `record`, `score.total` and `score.max_total` must match the sum of `question_results[].score` and `question_results[].max_score`.
- Every open result includes evidence before score.
- Every wrong answer has a mistake tag.
- Every wrong answer has `learn_from` or equivalent source/knowledge-point guidance.
- Every deduction reason is specific.
- Scores use rubric levels, not vibes.
- Low-confidence agent judgments are marked for human review.

## Memory Quality

- Mistake bank entries preserve knowledge point and mistake tag.
- `record` archives exam, HTML exam, attempt, grade, source, material report, deep research, and wrong questions under `data/learners/<id>/archive/`.
- Review exams use variants, not copied prompts.
- Weekly exams aggregate across recent archive files and mistake bank entries; when fewer than 3 archive sessions exist, the analysis must state the downgrade to mistake-variant weekly review.
- Old stale mistakes are not deleted silently; mark status instead.

## Dashboard Quality

- `python scripts/kaoda.py dashboard <learner_id>` creates `index.html`, `exams.html`, `mistakes.html`, `notes.html`, and `notes_agent_pack.md`.
- Dashboard totals match archived `grade.json` question results: answered, correct, wrong, and accuracy.
- Exam collection rows come from `archive/*/archive_manifest.json` and link only to files that exist.
- Wrong-question board comes from `mistake_bank.jsonl`, keeps active/stale status visible, and does not delete old rows.
- Notes are grouped from real wrong-question knowledge points and mistake tags; they must not invent facts beyond mistakes, evidence, grades, or sources.
- Empty learner history renders friendly empty states instead of failing.
