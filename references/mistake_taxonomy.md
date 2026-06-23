# Mistake Taxonomy

Use these tags in `grade.json` and `mistake_bank.jsonl`.

| Tag | Meaning | Review Angle |
| --- | --- | --- |
| `concept_confusion` | Misunderstands or swaps concepts | Ask for plain-language definition and contrast. |
| `mechanism_missing` | Cannot explain why it works | Ask "why" twice and require causal chain. |
| `boundary_blindness` | Treats method as universal | Ask when it fails or should not be used. |
| `false_transfer` | Applies source case blindly to new scenario | Change domain, user, constraint, or objective. |
| `counterexample_blindness` | Cannot see cases that break the idea | Present near-miss and contrary examples. |
| `application_gap` | Understands idea but cannot operationalize | Require concrete next action and validation. |
| `evidence_missing` | Claims without source or reasoning evidence | Require citation or observable proof. |

## Mistake Entry Contract

```json
{
  "entry_id": "mistake-...",
  "created_at": "2026-06-22T00:00:00Z",
  "learner_id": "default",
  "run_id": "run-id",
  "exam_id": "exam-id",
  "question_id": "q05",
  "knowledge_point": {"id": "kp-01", "name": "概念"},
  "ability": "迁移应用",
  "mistake_tag": "false_transfer",
  "original_prompt_hash": "hash",
  "original_scenario": "scenario",
  "source": {"segment_id": "seg-1"},
  "review_status": "active"
}
```

Store the reason the learner failed, not only the original question.
