# Research And Light Selection Gate

This gate prevents the skill from degenerating into a summary, an ordinary quiz generator, or a premature preference form.

## Mandatory Order

1. Ingest source material. If the user only gives a title or topic, run `research-topic`, do research, write `topic_research.md` and `source_links.json`, then run `ingest-topic`.
2. Read `material_report.json`.
3. Complete source analysis and mandatory core research/deepening, then write `deep_research.json`.
4. Ask the learner only the lightweight post-research choices.
5. Run `plan-exam` to write `review_choices.md`, `research_prompt.md`, and `exam_brief.json`.
6. Only then run `build-exam`.

## Mandatory Research

Do not ask the learner whether research is allowed. Research is part of the skill contract.

For every material or topic, deepen the core concepts. Mechanism, boundary, misconception, counterexample, and transfer are the minimum. The actual research direction must follow the material and can also include:

- background context or history
- upstream/downstream concepts
- practical applications
- controversies or competing interpretations
- risks, failure cases, and misuse patterns
- alternative methods or tools
- metrics, evaluation signals, or decision criteria
- domain-specific context needed to understand the material

If the learner explicitly says "只按原文", "source-only", or equivalent, keep `research.mode` as `source_only`: do source-internal research and inference only, do not introduce outside sources. This still counts as research; it is not a skip.

`deep_research.json` must include:

```json
{
  "version": "1.0",
  "research": {
    "status": "completed",
    "mandatory": true,
    "mode": "extended",
    "items": [
      {
        "origin": "source",
        "mechanism": "...",
        "boundary": "...",
        "misconception": "...",
        "counterexample": "...",
        "transfer_scenario": "...",
        "source_refs": [
          {"segment_id": "seg-0001", "locator": {"page": 1}, "excerpt": "..."}
        ]
      }
    ]
  }
}
```

Use `origin: "source"` for source-derived knowledge, `origin: "source_inferred"` for source-only inference, and `origin: "extension"` for external extension research. Never present extension knowledge as if it came from the original material.

`plan-exam` reads `deep_research.json` and copies the validated research object into `exam_brief.json.research`. It must fail when the file is missing, items are empty, required fields are thin, or source refs are absent. In `source_only` mode, no item may use `origin: "extension"`. In `extended` mode, include at least one `origin: "extension"` item with an external source URL; if external research was unavailable, set the mode to `source_only` and say why.

## Lightweight Post-Research Choices

After research, ask or confirm only these choices.

Review mode:

- `复盘模式 · 5分钟`: pure objective questions; single-choice, true/false, and multiple-choice; browser can score everything.
- `正常模式 · 10分钟`: objective-first; single-choice, multiple-choice, true/false, and a small fill-in slice; browser can score everything by default.
- `拷打模式 · 30分钟`: objective-first with a small number of short/oral prompts; agent review is needed for open answers.
- `深度拷打 · 45分钟`: higher short/oral ratio for interview, expression training, or deep follow-up; agent review is needed.

Question style:

- `正经复盘`
- `趣味拷打`
- `毒舌拷打`
- `面试官追问`
- `老板追问`
- `朋友吐槽`
- `反例猎人`
- `概念诈骗识别`
- `弹幕判断`
- `混合风格`

Mistake-knowledge policy, only when active mistake history exists:

- `只复盘当前材料`
- `加入历史错题`
- `重点拷最近错题`
- `当前材料为主，错题为辅`

Default recommendation: `正常模式 · 10分钟`, `混合风格`, and ask before adding historical mistakes. Do not silently mix mistake-bank knowledge.

## Topic-Only Requests

When the user says something like "我想了解 token" and provides no material:

1. Run `python scripts/kaoda.py research-topic "token" --run-id <id>`.
2. Use available research tools to gather reliable sources.
3. Write `topic_research.md` and `source_links.json` in the run directory.
4. Run `python scripts/kaoda.py ingest-topic <id>`.
5. Confirm or refine the generated `deep_research.json` from the resulting notes and source links.
6. Ask the lightweight choices, then continue with `plan-exam` and `build-exam`.

Do not generate questions from the bare topic string. The research note is the source material.

## plan-exam Contract

After mandatory research is written to `deep_research.json` and lightweight selection is known, run:

```bash
python scripts/kaoda.py plan-exam <run_id> \
  --review-mode "正常模式" \
  --question-style "混合风格" \
  --learner-id "<id>"
```

Use `--source-only` only when the learner explicitly asked to stay inside the original material. Use `--mistake-knowledge-policy` only after confirming the learner's choice when active mistake history exists.

`build-exam` must fail if `exam_brief.json` is missing or incomplete.

Mode defaults:

| Mode | Time | Default shape |
| --- | ---: | --- |
| `复盘模式` | 5 min | 15 objective checkpoints, no open answers |
| `正常模式` | 10 min | 20 checkpoints, objective/fill-in, no open answers |
| `拷打模式` | 30 min | 30 checkpoints, small short/oral slice |
| `深度拷打` | 45 min | 20 checkpoints, high short/oral ratio |

## Failure Modes

| Failure | Required Response |
| --- | --- |
| User gives only a vague topic, no material | Run `research-topic`, complete research notes, then `ingest-topic`; do not invent from the bare topic. |
| User gives material but no mode/style | Research first, then recommend `正常模式 · 10分钟` and `混合风格`; ask for confirmation only if needed. |
| External browsing is unavailable | Use source-internal research; mark `research.mode` as `source_only` if no external extension was actually used. |
| Material is too thin | Ask for transcript, notes, or PDF text. |
| User wants source-only review | Set `research.mode` to `source_only`; do not create extension facts, but still build a research structure. |
