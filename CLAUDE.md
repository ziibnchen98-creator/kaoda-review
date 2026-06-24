# Claude-Compatible Notes

`kaoda-review` is runtime-neutral. Treat `SKILL.md` as the canonical workflow and use `scripts/kaoda.py` for deterministic file generation.

Run `python scripts/kaoda.py doctor` after installation, for beginners, or when video/PDF/OCR extraction fails. Explain the result simply. If `ingest` returns `status: needs_text`, help the learner paste real source text into `manual_input.txt` or `manual_transcript.txt`, then run `python scripts/kaoda.py ingest-manual <run_id>`.

When scoring browser exports, run `grade-report <kaoda_agent_report.md>` first. If open answers are present, read `agent_open_review.md`, `grading_prompt.md`, `exam.json`, and `attempt.json`, then update `grade.json` with evidence-grounded rubric judgments, set each open result `score_status` to `completed` or remove it, and set `open_review.status` to `completed`.

If the learner gives only a topic, run `research-topic`, research the topic, write `topic_research.md` and `source_links.json`, then run `ingest-topic` before `plan-exam`.

Before building an exam, analyze the material and complete mandatory core research into `deep_research.json` first. Then ask or confirm only review mode/time, question style, and mistake-knowledge policy when active history exists. Run `plan-exam`; do not bypass the `deep_research.json` or `exam_brief.json` gates.

Default recommendation is `正常模式 · 10分钟`: objective-first and fully scorable in the browser. `拷打模式` and `深度拷打` may include short/oral prompts that need agent review. After final grading, run `record` so the full attempt and source/material/deep-research files are archived.
