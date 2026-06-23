import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "kaoda.py"
BANNED_VISIBLE_PROMPT_PATTERNS = [
    "原文校准｜",
    "变体追问｜",
    "延伸研究｜",
    "线索：",
    "最稳",
    "哪种理解最稳",
    "明显是在装懂",
    "别急着",
    "这题不哄人",
    "一眼假",
    "伪理解",
]


spec = importlib.util.spec_from_file_location("kaoda", MODULE_PATH)
kaoda = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["kaoda"] = kaoda
spec.loader.exec_module(kaoda)


class KaodaFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data_dir = os.environ.get("KAODA_DATA_DIR")
        os.environ["KAODA_DATA_DIR"] = str(Path(self.tmp.name) / "data")

    def tearDown(self):
        if self.old_data_dir is None:
            os.environ.pop("KAODA_DATA_DIR", None)
        else:
            os.environ["KAODA_DATA_DIR"] = self.old_data_dir
        self.tmp.cleanup()

    def test_full_local_flow_records_mistakes_and_generates_weekly(self):
        fixture = ROOT / "tests" / "fixtures" / "sample_text.txt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "demo"]), 0)
        self.assertEqual(
            kaoda.main(
                [
                    "plan-exam",
                    "demo",
                    "--review-mode",
                    "正常模式",
                    "--question-style",
                    "面试官追问",
                ]
            ),
            0,
        )
        self.assertEqual(kaoda.main(["build-exam", "demo"]), 0)

        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "demo"
        segments = [json.loads(line) for line in (run_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(segments)
        self.assertIn("locator", segments[0])

        exam = json.loads((run_dir / "exam.json").read_text(encoding="utf-8"))
        self.assertEqual(exam["mode"], "面试官追问")
        self.assertEqual(exam["review_mode"], "正常模式")
        self.assertEqual(exam["duration_minutes"], 10)
        self.assertEqual(exam["exam_brief"]["research"]["status"], "completed")
        self.assertTrue(exam["exam_brief"]["research"]["mandatory"])
        self.assertNotIn("intake", exam["exam_brief"])
        self.assertEqual(exam["exam_brief"]["review_selection"]["status"], "confirmed")
        self.assertTrue(exam["knowledge_map"]["source_topics"][0].get("diagnostic_focus"))
        self.assertTrue(exam["knowledge_map"]["source_topics"][0].get("misconception_trap"))
        self.assertEqual(len(exam["questions"]), 20)
        type_counts = {}
        for question in exam["questions"]:
            type_counts[question["type"]] = type_counts.get(question["type"], 0) + 1
        self.assertEqual(type_counts.get("single_choice", 0), 10)
        self.assertEqual(type_counts.get("multiple_choice", 0), 4)
        self.assertEqual(type_counts.get("true_false", 0), 4)
        self.assertEqual(type_counts.get("fill_blank", 0), 2)
        self.assertEqual(type_counts.get("open", 0), 0)
        self.assertEqual(
            [section["label"] for section in exam["question_sections"]],
            ["单选题", "多选题", "判断题", "填空题"],
        )
        self.assertEqual(
            [question["type"] for question in exam["questions"]],
            ["single_choice"] * 10 + ["multiple_choice"] * 4 + ["true_false"] * 4 + ["fill_blank"] * 2,
        )
        self.assertEqual({q.get("style_label") for q in exam["questions"]}, {"面试追问"})
        self.assertIn("variant", {q.get("source_layer") for q in exam["questions"]})
        single_answers = [question["answer"][0] for question in exam["questions"] if question["type"] == "single_choice"]
        self.assertGreater(len(set(single_answers)), 1)
        self.assertNotEqual(single_answers[:4], ["A", "A", "A", "A"])
        multiple_answers = [tuple(question["answer"]) for question in exam["questions"] if question["type"] == "multiple_choice"]
        self.assertGreater(len(set(multiple_answers)), 1)
        for question in exam["questions"]:
            self.assertIn("knowledge_point", question)
            self.assertIn("diagnostic_focus", question["knowledge_point"])
            self.assertIn("source", question)
            self.assertIn("style_label", question)
            self.assertIn("answer", question)
            for pattern in BANNED_VISIBLE_PROMPT_PATTERNS:
                self.assertNotIn(pattern, question["prompt"])

        html = (run_dir / "exam.html").read_text(encoding="utf-8")
        self.assertIn("学习报告", html)
        self.assertIn("提交试卷", html)
        self.assertIn("确认交卷后会生成学习报告，是否提交？", html)
        self.assertIn("导出报告给 Agent", html)
        self.assertIn("kaoda_agent_report.md", html)
        self.assertIn("## attempt.json", html)
        self.assertIn("## exam.json", html)
        self.assertIn("python scripts/kaoda.py record grade.json", html)
        self.assertNotIn("导出 attempt.json", html)
        self.assertNotIn("导出 agent 评分包", html)
        self.assertNotIn("导出错题 Markdown", html)
        self.assertNotIn("导出学习报告", html)
        self.assertNotIn("重新挑战", html)
        self.assertIn("question-section", html)
        self.assertNotIn("q-info", html)

        answers = {}
        for question in exam["questions"]:
            if question["type"] == "single_choice":
                answers[question["id"]] = ["B"]
            elif question["type"] == "multiple_choice":
                answers[question["id"]] = ["A"]
            elif question["type"] == "true_false":
                answers[question["id"]] = ["A"]
            elif question["type"] == "fill_blank":
                answers[question["id"]] = question["answer"][0]
        attempt = {
            "version": "1.0",
            "learner_id": "alice",
            "exam_id": exam["exam_id"],
            "run_id": "demo",
            "exam_path": str(run_dir / "exam.json"),
            "answers": answers,
        }
        attempt_path = run_dir / "attempt.json"
        attempt_path.write_text(json.dumps(attempt, ensure_ascii=False), encoding="utf-8")

        self.assertEqual(kaoda.main(["grade", str(attempt_path), "--learner-id", "alice"]), 0)
        grade = json.loads((run_dir / "grade.json").read_text(encoding="utf-8"))
        self.assertIn("wrong_reason_profile", grade)
        self.assertTrue(any(row.get("mistake_tag") for row in grade["question_results"]))
        self.assertTrue(any(row.get("learn_from") for row in grade["question_results"] if row.get("score") < row.get("max_score")))

        self.assertEqual(kaoda.main(["record", str(run_dir / "grade.json")]), 0)
        bank = Path(os.environ["KAODA_DATA_DIR"]) / "learners" / "alice" / "mistake_bank.jsonl"
        self.assertTrue(bank.exists())
        self.assertGreater(len(bank.read_text(encoding="utf-8").splitlines()), 0)
        archive_root = Path(os.environ["KAODA_DATA_DIR"]) / "learners" / "alice" / "archive"
        archives = list(archive_root.glob("*/archive_manifest.json"))
        self.assertTrue(archives)
        archive_dir = archives[0].parent
        self.assertTrue((archive_dir / "exam.json").exists())
        self.assertTrue((archive_dir / "exam.html").exists())
        self.assertTrue((archive_dir / "attempt.json").exists())
        self.assertTrue((archive_dir / "grade.json").exists())

        self.assertEqual(kaoda.main(["review", "alice", "--limit", "5"]), 0)
        self.assertEqual(kaoda.main(["weekly", "alice", "--since", "7d"]), 0)
        self.assertEqual(kaoda.main(["dashboard", "alice"]), 0)
        dashboard_dir = Path(os.environ["KAODA_DATA_DIR"]) / "learners" / "alice" / "dashboard"
        for name in ["index.html", "exams.html", "mistakes.html", "notes.html", "notes_agent_pack.md"]:
            self.assertTrue((dashboard_dir / name).exists(), name)
        dashboard = (dashboard_dir / "index.html").read_text(encoding="utf-8")
        exams_page = (dashboard_dir / "exams.html").read_text(encoding="utf-8")
        mistakes_page = (dashboard_dir / "mistakes.html").read_text(encoding="utf-8")
        notes_page = (dashboard_dir / "notes.html").read_text(encoding="utf-8")
        agent_pack = (dashboard_dir / "notes_agent_pack.md").read_text(encoding="utf-8")
        correct_count = sum(
            1 for row in grade["question_results"] if row.get("score", 0) >= row.get("max_score", 1)
        )
        wrong_count = len(grade["question_results"]) - correct_count
        self.assertIn("拷打式复盘总看板", dashboard)
        self.assertIn(f">{len(grade['question_results'])}<", dashboard)
        self.assertIn(f">{correct_count}<", dashboard)
        self.assertIn(f">{wrong_count}<", dashboard)
        self.assertIn("考卷集合", exams_page)
        self.assertIn("archive/", exams_page)
        self.assertIn("exam.html", exams_page)
        self.assertIn("错题集", mistakes_page)
        self.assertIn("active", mistakes_page)
        self.assertIn("错题笔记", notes_page)
        self.assertIn("我这里容易在", notes_page)
        self.assertIn("Agent 精修说明", agent_pack)
        self.assertIn("请把这些草稿改写成像我自己写的复盘笔记", agent_pack)
        weekly_root = Path(os.environ["KAODA_DATA_DIR"]) / "learners" / "alice" / "weekly"
        weekly_paths = list(weekly_root.glob("*/weekly_exam.json"))
        self.assertTrue(weekly_paths)
        weekly_exam = json.loads(weekly_paths[0].read_text(encoding="utf-8"))
        weekly_single_answers = [
            question["answer"][0] for question in weekly_exam["questions"] if question["type"] == "single_choice"
        ]
        if len(weekly_single_answers) > 1:
            self.assertGreater(len(set(weekly_single_answers)), 1)
        for question in weekly_exam["questions"]:
            for pattern in BANNED_VISIBLE_PROMPT_PATTERNS:
                self.assertNotIn(pattern, question["prompt"])

    def test_build_exam_requires_exam_brief(self):
        fixture = ROOT / "tests" / "fixtures" / "sample_text.txt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "needs-brief"]), 0)
        self.assertEqual(kaoda.main(["build-exam", "needs-brief"]), 2)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "needs-brief"
        self.assertTrue((run_dir / "intake_questions.md").exists() is False)
        self.assertEqual(kaoda.main(["plan-exam", "needs-brief", "--source-only"]), 0)
        self.assertFalse((run_dir / "intake_questions.md").exists())
        self.assertTrue((run_dir / "review_choices.md").exists())
        self.assertTrue((run_dir / "research_prompt.md").exists())
        self.assertEqual(kaoda.main(["build-exam", "needs-brief"]), 0)
        exam = json.loads((run_dir / "exam.json").read_text(encoding="utf-8"))
        self.assertEqual(exam["exam_brief"]["research"]["status"], "completed")
        self.assertEqual(exam["exam_brief"]["research"]["mode"], "source_only")
        origins = {item.get("origin") for item in exam["exam_brief"]["research"]["items"]}
        self.assertNotIn("extension", origins)

    def test_subtitle_ingest_preserves_timestamp(self):
        fixture = ROOT / "tests" / "fixtures" / "sample.srt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "srt-demo"]), 0)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "srt-demo"
        rows = [json.loads(line) for line in (run_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertIn("timestamp", rows[0]["locator"])

    def test_material_report_prefers_informative_evidence(self):
        segments = [
            {
                "segment_id": "seg-1",
                "source_id": "demo",
                "text": "各位同学大家好，今天这堂课是一堂课。",
                "locator": {"chunk": 1},
            },
            {
                "segment_id": "seg-2",
                "source_id": "demo",
                "text": "Token 是模型处理文字的基本单位，边界是它不等同于完整词语。",
                "locator": {"chunk": 2},
            },
            {
                "segment_id": "seg-3",
                "source_id": "demo",
                "text": "如果只把 token 当作英文字，遇到中文或符号就会理解错。",
                "locator": {"chunk": 3},
            },
        ]
        report = kaoda.build_material_report("demo", {"input": "inline", "input_type": "inline_text"}, segments)
        token_topic = next(topic for topic in report["knowledge_map"]["source_topics"] if topic["name"].lower() == "token")
        self.assertNotIn("seg-1", token_topic["evidence_segment_ids"])
        self.assertTrue(token_topic["diagnostic_focus"])
        self.assertIn("Token", token_topic["misconception_trap"])

    def test_research_misconception_reaches_question_options(self):
        segments = [
            {
                "segment_id": "seg-1",
                "source_id": "demo",
                "text": "大家好，欢迎来到课程。",
                "locator": {"chunk": 1},
            },
            {
                "segment_id": "seg-2",
                "source_id": "demo",
                "text": "Token 是模型处理文字的基本单位，边界是它不等同于完整词语。",
                "locator": {"chunk": 2},
            },
        ]
        source = {"input": "inline", "input_type": "inline_text"}
        report = kaoda.build_material_report("demo", source, segments)
        token_topic = next(topic for topic in report["knowledge_map"]["source_topics"] if topic["name"].lower() == "token")
        brief = {
            "exam_style": "有趣拷打模式",
            "question_profile": ["错误理解识别", "迁移应用", "边界识别"],
            "intake": {"status": "confirmed"},
            "research": {
                "status": "completed",
                "items": [
                    {
                        "topic_id": token_topic["id"],
                        "topic": token_topic["name"],
                        "misconception": "把 token 当成普通英文单词，忽略中文、符号和切分规则。",
                        "boundary": "它不是完整词语，也不等同于一个字符。",
                        "mechanism": "模型按 token 处理输入，tokenizer 决定切分方式。",
                        "transfer_scenario": "估算上下文窗口和提示长度。",
                        "counterexample": "中文、emoji 或标点会破坏英文单词式理解。",
                    }
                ],
            },
        }
        exam = kaoda.make_exam_from_segments("demo", source, segments, report, brief=brief)
        misconception_question = next(question for question in exam["questions"] if question["type"] == "multiple_choice")
        self.assertEqual(misconception_question["source"]["segment_id"], "seg-2")
        self.assertTrue(any("普通英文单词" in option["text"] for option in misconception_question["options"]))

    def test_modes_control_open_question_ratio(self):
        fixture = ROOT / "tests" / "fixtures" / "sample_text.txt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "mode-demo"]), 0)
        self.assertEqual(kaoda.main(["plan-exam", "mode-demo", "--review-mode", "拷打模式"]), 0)
        self.assertEqual(kaoda.main(["build-exam", "mode-demo"]), 0)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "mode-demo"
        exam = json.loads((run_dir / "exam.json").read_text(encoding="utf-8"))
        type_counts = {}
        for question in exam["questions"]:
            type_counts[question["type"]] = type_counts.get(question["type"], 0) + 1
            for pattern in BANNED_VISIBLE_PROMPT_PATTERNS:
                self.assertNotIn(pattern, question["prompt"])
        self.assertEqual(exam["review_mode"], "拷打模式")
        self.assertEqual(len(exam["questions"]), 30)
        self.assertGreater(type_counts.get("open", 0), 0)
        self.assertTrue(any(q.get("voice_enabled") for q in exam["questions"] if q["type"] == "open"))
        first_open = next(index for index, question in enumerate(exam["questions"]) if question["type"] == "open")
        self.assertTrue(all(question["type"] != "open" for question in exam["questions"][:first_open]))

        self.assertEqual(kaoda.main(["plan-exam", "mode-demo", "--review-mode", "深度拷打"]), 0)
        self.assertEqual(kaoda.main(["build-exam", "mode-demo"]), 0)
        exam = json.loads((run_dir / "exam.json").read_text(encoding="utf-8"))
        open_count = sum(1 for question in exam["questions"] if question["type"] == "open")
        self.assertEqual(exam["review_mode"], "深度拷打")
        self.assertGreaterEqual(open_count, len(exam["questions"]) // 2)

    def test_mistake_knowledge_choice_only_when_bank_exists(self):
        fixture = ROOT / "tests" / "fixtures" / "sample_text.txt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "mistake-choice"]), 0)
        self.assertEqual(
            kaoda.main(
                [
                    "plan-exam",
                    "mistake-choice",
                    "--learner-id",
                    "bob",
                    "--mistake-knowledge-policy",
                    "加入历史错题",
                ]
            ),
            0,
        )
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "mistake-choice"
        choices = (run_dir / "review_choices.md").read_text(encoding="utf-8")
        brief = json.loads((run_dir / "exam_brief.json").read_text(encoding="utf-8"))
        self.assertNotIn("检测到该 learner 有历史错题", choices)
        self.assertFalse(brief["mistake_knowledge"]["available"])
        self.assertEqual(brief["mistake_knowledge"]["policy"], "只复盘当前材料")

        bank = Path(os.environ["KAODA_DATA_DIR"]) / "learners" / "bob" / "mistake_bank.jsonl"
        bank.parent.mkdir(parents=True, exist_ok=True)
        bank.write_text(
            json.dumps(
                {
                    "created_at": "2026-06-23T00:00:00Z",
                    "review_status": "active",
                    "mistake_tag": "boundary_blindness",
                    "knowledge_point": {"id": "kp-old", "name": "旧错题知识"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(
            kaoda.main(
                [
                    "plan-exam",
                    "mistake-choice",
                    "--learner-id",
                    "bob",
                    "--mistake-knowledge-policy",
                    "重点拷最近错题",
                ]
            ),
            0,
        )
        choices = (run_dir / "review_choices.md").read_text(encoding="utf-8")
        brief = json.loads((run_dir / "exam_brief.json").read_text(encoding="utf-8"))
        self.assertIn("检测到该 learner 有历史错题", choices)
        self.assertTrue(brief["mistake_knowledge"]["available"])
        self.assertEqual(brief["mistake_knowledge"]["policy"], "重点拷最近错题")

    def test_topic_only_workflow_requires_research_notes(self):
        self.assertEqual(kaoda.main(["research-topic", "token", "--run-id", "token-demo"]), 0)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "token-demo"
        self.assertTrue((run_dir / "topic_research_prompt.md").exists())
        self.assertEqual(kaoda.main(["ingest-topic", "token-demo"]), 2)
        (run_dir / "topic_research.md").write_text(
            "\n".join(
                [
                    "# token 研究",
                    "Token 是模型处理文本的基本单位，由 tokenizer 把字符序列切成片段。",
                    "机制上，模型看到的是 token 序列而不是人类自然语言里的完整词语。",
                    "边界是 token 不等同于英文单词，也不等同于一个中文字符。",
                    "常见误解是把 token 当成普通单词，忽略中文、标点、emoji 和不同 tokenizer 的切分差异。",
                    "迁移应用包括估算上下文窗口、控制提示长度、理解计费和压缩输入。",
                    "反例是同一句中文在不同 tokenizer 下可能切成不同数量的 token。",
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "source_links.json").write_text(
            json.dumps({"sources": [{"title": "Tokenizer docs", "url": "https://example.com", "why_used": "示例"}]}),
            encoding="utf-8",
        )
        self.assertEqual(kaoda.main(["ingest-topic", "token-demo"]), 0)
        self.assertTrue((run_dir / "segments.jsonl").exists())
        source = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))
        self.assertEqual(source["input_type"], "topic_research")
        report = json.loads((run_dir / "material_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["topic_research"]["topic"], "token")

    def test_dashboard_empty_learner_renders_without_history(self):
        self.assertEqual(kaoda.main(["dashboard", "new-learner"]), 0)
        dashboard_dir = Path(os.environ["KAODA_DATA_DIR"]) / "learners" / "new-learner" / "dashboard"
        index = (dashboard_dir / "index.html").read_text(encoding="utf-8")
        exams = (dashboard_dir / "exams.html").read_text(encoding="utf-8")
        mistakes = (dashboard_dir / "mistakes.html").read_text(encoding="utf-8")
        notes = (dashboard_dir / "notes.html").read_text(encoding="utf-8")
        self.assertIn("还没有完成记录", index)
        self.assertIn("暂无归档考卷", exams)
        self.assertIn("暂无错题", mistakes)
        self.assertIn("暂无错题笔记", notes)


if __name__ == "__main__":
    unittest.main()
