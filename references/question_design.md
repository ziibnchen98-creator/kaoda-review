# Question Design

## Review Purpose

The review checklist diagnoses fake understanding. It should make weak comprehension visible without feeling like a formal exam.

The key question is:

> Can the learner survive follow-up questioning when the scenario changes?

## Ability Types

| Ability | What It Exposes | Good Prompt Shape |
| --- | --- | --- |
| 复述检查 | Can name and define the concept | "Explain X without copying the material." |
| 为什么追问 | Mechanism understanding | "Why does X work? What must be true?" |
| 边界识别 | Knows when not to apply it | "When would X fail or mislead?" |
| 错误理解识别 | Detects fake understanding in others | "Which statements are wrong or unsupported?" |
| 迁移应用 | Can use it in a new case | "Apply X to this different situation." |
| 反例判断 | Can reason from counterexamples | "Which case breaks the rule?" |
| 落地追问 | Can make a decision/action | "What would you do next, and how verify?" |

## Mode-Based Mix

The mode controls friction, scoring method, and whether open answers appear.

- `复盘模式 · 5分钟`: about 15 objective checkpoints. Use roughly 60% single-choice, 25% true/false, and 15% multiple-choice. No fill-in, short answer, or oral prompts.
- `正常模式 · 10分钟`: about 20 checkpoints. Use roughly 50% single-choice, 20% multiple-choice, 20% true/false, and 10% fill-in. No short answer or oral prompts by default.
- `拷打模式 · 30分钟`: about 30 checkpoints. Keep objective questions dominant, add a small short/oral slice, and use agent review for those open answers.
- `深度拷打 · 45分钟`: use a higher short/oral ratio for interview, expression training, or deep follow-up. Agent review is required.
- For long or complex material, 30, 40, or 50 checkpoints are acceptable when needed for coverage, but do not add open answers to `复盘模式` or `正常模式` unless the user explicitly changes the mode.
- Oral prompts must always keep a text input fallback.
- Include at least one `错误理解识别`, one `边界识别`, and one `迁移应用` item.
- The final mix must reflect `exam_brief.review_mode` and `exam_brief.question_style`.

## Style Variants

Questions should not all sound like a teacher asking students to recite the lesson. Rotate style families internally, but do not print the style family or cue sentence in the visible prompt. Style should only shape scenario choice or option wording.

- 正经复盘
- 趣味拷打
- 毒舌拷打
- 面试追问
- 老板追问
- 朋友吐槽
- 反例猎人
- 概念诈骗识别
- 迁移现场
- 弹幕判断

Each style still needs a clear answer and evidence. Fun is useful only when it exposes fake understanding.

## Visible Prompt Contract

Visible prompts must be clean enough that a learner immediately knows what to answer.

Do not expose internal scaffolding in `prompt`:

- source layer labels such as `原文校准`, `变体追问`, or `延伸研究`
- style labels such as `正经复盘`, `毒舌拷打`, or `弹幕判断`
- question-type labels such as `单选`, `判断`, or `填空` when used as prefixes
- style cue sentences

Do not use these visible prompt patterns:

- `原文校准｜正经复盘｜单选`
- `线索：...`
- `最稳`
- `哪种理解最稳？`
- `哪些明显是在装懂？`
- `别急着...`
- `这题不哄人...`
- `一眼假`
- `伪理解`

Prefer direct, plain patterns:

- `关于「X」，哪一项说法更符合材料？`
- `关于「X」，哪些说法有问题？`
- `判断对错：...`
- `材料里和这条描述对应的关键词或短语是什么？描述：... 答案：____。`
- `在「场景」中，如何使用「X」？`

The UI should render sections in this order: single-choice, multiple-choice, true/false, fill-in, then short/oral. Keep internal metadata in JSON for grading and archive use, not in the visible question text.

## Before Writing Questions

Read `exam_brief.json` and check:

- `review_selection.status` is `confirmed`.
- `review_mode` is present.
- `question_style` is present.
- `research.status` is `completed`.
- `research.mandatory` is `true`.
- `deepened_knowledge_map` exists.

If any item is missing, stop and run `plan-exam` instead of writing questions.

## Source vs Extension

Source-derived questions must cite `source.segment_id`.

Variant questions may use `source_layer: "variant"` when they change the scenario, wording, or social frame while still testing source-derived knowledge.

Extension questions must set:

```json
"extension": true
```

They must not pretend to be from the original material.

## Bad Question Patterns

Do not use:

- "What did the author say about X?" as the main pattern.
- Definition-only questions for every concept.
- Trivia from examples.
- Generic "what is the best answer?" prompts without a source or scenario.
- Generic distractors that would fit any material, such as "memorize keywords" repeated for every question.
- Open questions in `复盘模式` or default `正常模式`.
- Open questions without a scoring rubric.
- Long written prompts when a fill-in, choice, or short-answer checkpoint can expose the same weakness.
- Teacher-style repetition where every prompt starts with "What is X" or "Why is X important".
- Internal labels, style cues, or source layer names in visible prompts.

## Material-Specific Distractors

Objective questions should use the material's own evidence and the deepened knowledge map.

For each important concept, derive:

- Mechanism: why the claim works.
- Boundary: when the claim fails or misleads.
- Misconception: what a learner would say when pretending to understand.
- Transfer: a new scenario where the learner must decide how to apply it.

Good distractors should look plausible to someone who watched the material passively. They should expose a specific mistake, such as overgeneralizing the source case, confusing a boundary condition, or treating a term as a magic keyword.

## Good Question Pattern

```json
{
  "type": "multiple_choice",
  "ability": "错误理解识别",
  "prompt": "关于 X，哪些说法有问题？",
  "answer": ["B", "D"]
}
```

```json
{
  "type": "true_false",
  "ability": "边界识别",
  "prompt": "判断对错：只要能复述 X 这个词，就说明掌握了 X。",
  "answer": ["B"]
}
```

```json
{
  "type": "open",
  "answer_mode": "oral",
  "voice_enabled": true,
  "ability": "迁移应用",
  "prompt": "用 60-90 秒口述：把 X 用到一个不同场景。说明机制、边界、失败信号和验证方式。",
  "rubric": {"scale": "0-4"}
}
```
