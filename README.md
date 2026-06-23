# kaoda-review

“拷打式复盘” is an open Agent Skill for converting passive learning material into interactive understanding review checklists.

It is not a summarizer and not a normal quiz generator. It uses low-stakes checkpoints to ask whether the learner can explain mechanisms, transfer concepts, identify wrong interpretations, state boundaries, and apply ideas in real scenarios.

Default recommendation: `正常模式 · 10分钟`, about 20 checkpoints, objective-first, and fully scorable in the browser. Heavier modes add short/oral prompts for agent-reviewed expression training.

## Quick Start

```bash
cd kaoda-review
python scripts/kaoda.py ingest tests/fixtures/sample_text.txt --run-id demo
python scripts/kaoda.py plan-exam demo \
  --review-mode "正常模式" \
  --question-style "混合风格"
python scripts/kaoda.py build-exam demo
open data/runs/demo/exam.html
```

Topic-only workflow:

```bash
python scripts/kaoda.py research-topic "token" --run-id token-demo
# Agent researches, then writes data/runs/token-demo/topic_research.md and source_links.json
python scripts/kaoda.py ingest-topic token-demo
python scripts/kaoda.py plan-exam token-demo --review-mode "正常模式" --question-style "混合风格"
python scripts/kaoda.py build-exam token-demo
```

After completing a review in the browser, click `提交试卷` to enter the learning report page. Click `导出报告给 Agent` to download `kaoda_agent_report.md`; it contains the report, answers, `attempt.json`, `exam.json`, and the instructions an Agent needs for second-pass grading and mistake recording.

Agent-side commands still use the deterministic CLI contracts:

```bash
python scripts/kaoda.py grade data/runs/demo/attempt.json --learner-id demo-user
python scripts/kaoda.py record data/runs/demo/grade.json
python scripts/kaoda.py dashboard demo-user
python scripts/kaoda.py review demo-user
python scripts/kaoda.py weekly demo-user --since 7d
```

`record` also archives the full exam, attempt, grade, HTML exam, and wrong questions under `data/learners/<id>/archive/`. `dashboard` regenerates a static multi-page learner hub at `data/learners/<id>/dashboard/index.html`.

## What It Produces

- `segments.jsonl`: source-preserving learning material segments
- `material_report.json`: knowledge-map draft and fake-understanding risks
- `review_choices.md`: lightweight choices shown after mandatory research
- `research_prompt.md`: focused research/deepening task
- `exam_brief.json`: confirmed review mode, question style, mistake-knowledge policy, mandatory research, and generation contract
- `exam.json`: structured review-checklist data
- `exam.html`: static interactive review checklist
- `grading_prompt.md`: instructions for agent open-answer grading
- `kaoda_agent_report.md`: browser export containing the learning report, answers, exam, attempt, and Agent scoring/recording instructions
- `grade.json`: score, analysis, and mistake tags
- `mistake_bank.jsonl`: append-only local memory for variants and weekly reviews
- `archive/`: complete history of completed reviews and wrong-question sets
- `dashboard/index.html`: learner homepage with score totals, accuracy, recent exams, learned topics, and weak points
- `dashboard/exams.html`: archived exam collection with links to archived files
- `dashboard/mistakes.html`: wrong-question board grouped by knowledge point and mistake tag
- `dashboard/notes.html`: plain-language notes drafted from wrong-question clusters
- `dashboard/notes_agent_pack.md`: Agent package for rewriting those notes in a natural personal-review voice

## Requirements

The core CLI uses Python standard library. Optional source extraction tools:

- `yt-dlp` for video subtitles
- `pdftotext` for PDF text extraction
- `pdftoppm` and `tesseract` for scanned PDF OCR

## Runtime Neutrality

This skill is designed for skills-aware agents across runtimes. The deterministic layer is filesystem-based and the model-dependent layer is represented through structured prompts and JSON contracts.

## Important Gate

`build-exam` intentionally fails if `exam_brief.json` is missing. This forces the agent to analyze the material, complete mandatory research/deepening, and record the lightweight mode/style selection before generating the review.
