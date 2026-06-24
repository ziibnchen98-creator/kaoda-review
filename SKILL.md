---
name: kaoda-review
description: "Use when a learner wants to convert YouTube/Bilibili videos, PDFs, articles, subtitles, notes, or a topic they want to understand into a “拷打式复盘” diagnostic: research-backed interactive HTML review checklists, single-choice/multiple-choice/true-false/fill-in checkpoints, a small number of rubric-scored short or oral answers, one-click Agent report export, archived attempts, mistake-bank records, variant review, and weekly synthesis reviews that expose fake understanding, weak transfer, misconception, and boundary-blindness."
---

# 拷打式复盘

Turn passive learning material into an interactive review checklist that exposes whether the learner truly understands, can transfer, can identify wrong interpretations, and can survive follow-up questioning.

## Core Principle

Do not behave like a summarizer or a normal quiz generator. The product promise is:

> 看完了，不代表你懂。你还要经得起拷问。

Every output must help diagnose fake understanding:

- Can the learner explain the mechanism?
- Can they state boundaries and failure cases?
- Can they identify another person's wrong understanding?
- Can they transfer the idea into a different scenario?
- Can they turn the concept into a usable decision or action?

Default output is a low-stakes review checklist, not a formal exam. The default recommendation is `正常模式 · 10分钟`: about 20 checkpoints, mostly objective, and no short/oral prompts unless the learner chooses a heavier mode.

## Workflow

1. If the user provides a concrete material, run `python scripts/kaoda.py ingest <input>` to create `data/runs/<run_id>/segments.jsonl`.
2. If the user only gives a title or topic, run `python scripts/kaoda.py research-topic "<topic>"`, perform focused research, write `topic_research.md` and `source_links.json`, then run `python scripts/kaoda.py ingest-topic <run_id>`.
3. Read `data/runs/<run_id>/material_report.json`.
4. Read `references/intake_and_research.md`.
5. Complete source analysis and mandatory core research/deepening before asking mode/style questions. Default to extended research; if the learner explicitly says "只按原文/source-only", do source-internal research only. Write the result to `data/runs/<run_id>/deep_research.json`.
6. After research, ask only the lightweight choices: review mode/time, question style, and mistake-knowledge policy when the learner has active mistake history.
7. Run `python scripts/kaoda.py plan-exam <run_id> ...` to create `review_choices.md`, `research_prompt.md`, and `exam_brief.json`.
8. 🔴 CHECKPOINT: `plan-exam` must fail unless `deep_research.json` exists and contains completed research with source refs. Do not run `build-exam` unless `exam_brief.json` contains `review_mode`, `question_style`, `review_selection.status`, and mandatory research status `completed`.
9. For review-checkpoint design rules, read `references/question_design.md`.
10. For open-answer grading, read `references/rubrics.md`.
11. Run `python scripts/kaoda.py build-exam <run_id>` to create `exam.json`, `exam.html`, and `grading_prompt.md`.
12. Let the learner complete the review in `exam.html`. The visible UI should keep the flow simple: `提交试卷`, then a report page with `导出报告给 Agent`.
13. Read the exported `kaoda_agent_report.md`; it contains `attempt.json`, `exam.json`, objective pregrade, answers, and instructions for agent scoring/recording. Run `python scripts/kaoda.py grade-report <kaoda_agent_report.md> --learner-id <id>` to generate `attempt.json`, `exam.json`, `grading_prompt.md`, and `grade.json`.
14. If `grade.json.open_review.status` is `pending_agent_review`, use `agent_open_review.md` to rubric-score short/oral answers, then set `open_review.status` to `completed` and update open-question results before recording.
15. Run `python scripts/kaoda.py record <grade.json>` to append mistakes and archive the full exam/attempt/grade/HTML plus source/material/deep-research files under `data/learners/<id>/archive/`. `record` refuses pending open-answer pregrades.
16. Run `python scripts/kaoda.py dashboard <id>` to refresh the static learner hub: total score board, exam collection, wrong-question board, and plain-language notes.
17. Run `python scripts/kaoda.py review <id>` for variant review or `python scripts/kaoda.py weekly <id> --since 7d` for the weekly synthesis exam.

## Research-First Choice Gate

Do not ask whether research is allowed. It is required. Research directions are not a fixed checklist: mechanism, boundary, misconception, counterexample, and transfer are the minimum; add background, controversy, risks, alternatives, upstream/downstream knowledge, realistic applications, tools, metrics, history, or domain context when the material calls for them.

After research, ask or confirm:

- Review mode/time: `复盘模式 · 5分钟`, `正常模式 · 10分钟`, `拷打模式 · 30分钟`, or `深度拷打 · 45分钟`.
- Question style: `正经复盘`, `趣味拷打`, `毒舌拷打`, `面试官追问`, `老板追问`, `朋友吐槽`, `反例猎人`, `概念诈骗识别`, `弹幕判断`, or `混合风格`.
- Mistake-knowledge policy only when active history exists: `只复盘当前材料`, `加入历史错题`, `重点拷最近错题`, or `当前材料为主，错题为辅`.

Default recommendation: `正常模式 · 10分钟` with `混合风格`. Do not silently mix historical mistakes; ask when they exist.

## Question Readability Contract

Questions must read like a clear review sheet, not like an agent exposing its prompt scaffolding.

- Keep source layer, style family, ability type, and difficulty as JSON metadata only; never print them in the visible question prompt.
- Do not prefix prompts with labels such as `原文校准｜正经复盘｜单选`, style cue sentences, or `线索：`.
- Avoid self-conscious AI phrases such as `最稳`, `哪种理解最稳`, `明显是在装懂`, `别急着`, `这题不哄人`, `一眼假`, or `伪理解`.
- Use plain, answerable wording: ask which statement fits the material, which statements are wrong, whether a statement is true, what concept matches a description, or how to apply a concept in a scenario.
- Render questions by type section: single-choice, multiple-choice, true/false, fill-in, then short/oral.
- Distribute objective correct-answer positions across option IDs in main exams and mistake/weekly variants; never let a generated sheet look like every answer is A.
- After confirmation-based submission, the HTML must switch to a report page with score, type-level score, wrong questions, weak knowledge points, and one export button for an Agent-readable report package.
- Do not expose multiple export buttons for internal artifacts. `attempt.json`, `exam.json`, and grading instructions belong inside the single exported Agent report.

## Source Handling

Read `references/source_ingestion.md` before processing videos, PDFs, article URLs, scanned documents, or subtitles.

Hard rules:

- Preserve source provenance: page, timestamp, URL, or segment id.
- Prefer subtitles/PDF text/user text before audio transcription.
- If a video has no accessible subtitles and transcription is not available, stop and ask for a transcript.
- Mark extension research separately from source-derived knowledge.

## Quality Gates

Read `references/quality_gates.md` before final delivery.

Required files for a normal run:

- `segments.jsonl`
- `material_report.json`
- `deep_research.json`
- `review_choices.md`
- `research_prompt.md`
- `topic_research.md` and `source_links.json` when the input was a bare topic
- `exam_brief.json`
- `exam.json`
- `exam.html`
- `grading_prompt.md`
- `kaoda_agent_report.md` after learner completes and exports the review
- `grade.json` after scoring
- `agent_open_review.md` when `grade.json.open_review.status` is `pending_agent_review`
- `mistake_bank.jsonl` after recording mistakes
- `dashboard/index.html`, `dashboard/exams.html`, `dashboard/mistakes.html`, and `dashboard/notes.html` after refreshing the learner dashboard
- `dashboard/notes_agent_pack.md` when the learner wants an Agent to rewrite notes in a more natural personal voice

## Do Not

- Do not generate a summary booklet as the final product.
- Do not run `build-exam` before mandatory research and lightweight mode/style selection are recorded in `exam_brief.json`.
- Do not run `plan-exam` before writing and validating `deep_research.json`.
- Do not ask the old five-question intake bundle before research.
- Do not claim external extension research was done in source-only mode.
- Do not create only recall questions.
- Do not expose internal labels or style prompts in visible question text.
- Do not create a wall of long open-answer questions. `复盘模式` and `正常模式` should be objective-first and directly scorable in the browser; short/oral prompts belong to `拷打模式` and `深度拷打`.
- Do not score open answers by keyword matching alone.
- Do not record `grade.json` with `open_review.status` still set to `pending_agent_review`.
- Do not generate questions from a bare topic before writing topic research notes and sources.
- Do not reuse old questions for review or weekly exams.
- Do not hide missing source evidence behind confident wording.
- Do not mix source facts and extension research without labels.
