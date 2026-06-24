# Agent Instructions

This repository contains the `kaoda-review` Agent Skill.

Use it when a learner wants to turn videos, PDFs, articles, subtitles, notes, or a bare learning topic into a “拷打式复盘” understanding diagnostic with mandatory research, HTML review checklists, mode-based objective/open mixes, true/false items, rubric grading for short/oral answers, downloadable agent scoring packages, archived attempts, mistake memory, variants, and weekly synthesis.

Run commands from the skill root:

```bash
python scripts/kaoda.py ingest <input>
python scripts/kaoda.py research-topic "token"
python scripts/kaoda.py ingest-topic <run_id>
# write/verify data/runs/<run_id>/deep_research.json before planning
python scripts/kaoda.py plan-exam <run_id> --review-mode "正常模式" --question-style "混合风格"
python scripts/kaoda.py build-exam <run_id>
python scripts/kaoda.py grade-report <kaoda_agent_report.md> --learner-id <id>
python scripts/kaoda.py record <grade.json>
python scripts/kaoda.py review <id>
python scripts/kaoda.py weekly <id> --since 7d
```

Do not reduce this skill to summarization or normal quiz generation. Its job is to expose fake understanding, weak transfer, misconception, and boundary-blindness through low-stakes review checkpoints.

Before `plan-exam`, always analyze the material and complete core research/deepening into `deep_research.json`; the command must fail when that file is missing or thin. Do not ask whether research is allowed; only use `--source-only` when the learner explicitly says to stay inside the source. After research, ask or confirm review mode/time, question style, and mistake-knowledge policy only when active history exists. If the learner only gives a topic, complete `research-topic` and `ingest-topic` before planning. `build-exam` must not run before `exam_brief.json` exists. `record` must not run while `grade.json.open_review.status` is `pending_agent_review`.
