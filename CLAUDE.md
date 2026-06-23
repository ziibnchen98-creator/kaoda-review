# Claude-Compatible Notes

`kaoda-review` is runtime-neutral. Treat `SKILL.md` as the canonical workflow and use `scripts/kaoda.py` for deterministic file generation.

When scoring open answers, read `grading_prompt.md`, `exam.json`, and `attempt.json`, then update `grade.json` with evidence-grounded rubric judgments.

If the learner gives only a topic, run `research-topic`, research the topic, write `topic_research.md` and `source_links.json`, then run `ingest-topic` before `plan-exam`.

Before building an exam, analyze the material and complete mandatory core research first. Then ask or confirm only review mode/time, question style, and mistake-knowledge policy when active history exists. Run `plan-exam`; do not bypass the `exam_brief.json` gate.

Default recommendation is `正常模式 · 10分钟`: objective-first and fully scorable in the browser. `拷打模式` and `深度拷打` may include short/oral prompts that need agent review. After grading, run `record` so the full attempt is archived.
