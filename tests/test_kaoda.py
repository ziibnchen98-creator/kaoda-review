import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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

    def write_deep_research(self, run_id, mode="extended"):
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / run_id
        report = json.loads((run_dir / "material_report.json").read_text(encoding="utf-8"))
        segments = [json.loads(line) for line in (run_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        sources = [{"title": "Reliable source", "url": "https://example.com/source", "why_used": "测试延伸研究来源"}] if mode == "extended" else []
        payload = kaoda.build_deep_research_from_report(report, segments, sources=sources)
        if mode == "source_only":
            payload["research"]["mode"] = "source_only"
            payload["research"]["items"] = [item for item in payload["research"]["items"] if item.get("origin") != "extension"]
            for item in payload["research"]["items"]:
                item["origin"] = "source_inferred"
        (run_dir / "deep_research.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def agent_report_markdown(self, exam, attempt):
        return "\n".join(
            [
                "# kaoda-review Agent 报告包",
                "",
                "## attempt.json",
                "",
                "```json",
                json.dumps(attempt, ensure_ascii=False, indent=2),
                "```",
                "",
                "## exam.json",
                "",
                "```json",
                json.dumps(exam, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )

    def write_minimal_pdf(self, path, text):
        stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        chunks = [b"%PDF-1.4\n"]
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(sum(len(chunk) for chunk in chunks))
            chunks.append(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
        xref_offset = sum(len(chunk) for chunk in chunks)
        chunks.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
        for offset in offsets[1:]:
            chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
        chunks.append(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        path.write_bytes(b"".join(chunks))

    def test_full_local_flow_records_mistakes_and_generates_weekly(self):
        fixture = ROOT / "tests" / "fixtures" / "sample_text.txt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "demo"]), 0)
        self.write_deep_research("demo")
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
        self.assertTrue((archive_dir / "source.json").exists())
        self.assertTrue((archive_dir / "material_report.json").exists())
        self.assertTrue((archive_dir / "deep_research.json").exists())

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
        self.assertIn("exam_brief", weekly_exam)
        self.assertIn("review_design", weekly_exam)
        self.assertIn("question_sections", weekly_exam)
        self.assertEqual(kaoda.main(["validate", str(weekly_paths[0])]), 0)
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
        self.assertEqual(kaoda.main(["plan-exam", "needs-brief", "--source-only"]), 2)
        self.write_deep_research("needs-brief", mode="source_only")
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

    def test_deep_research_validation_rejects_bad_contracts(self):
        fixture = ROOT / "tests" / "fixtures" / "sample_text.txt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "research-gate"]), 0)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "research-gate"

        (run_dir / "deep_research.json").write_text(
            json.dumps({"research": {"status": "completed", "mode": "extended", "items": []}}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.assertEqual(kaoda.main(["plan-exam", "research-gate"]), 2)

        payload = self.write_deep_research("research-gate", mode="extended")
        payload["research"]["mode"] = "source_only"
        (run_dir / "deep_research.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(kaoda.main(["plan-exam", "research-gate", "--source-only"]), 2)

        self.write_deep_research("research-gate", mode="extended")
        self.assertEqual(kaoda.main(["plan-exam", "research-gate"]), 0)

    def test_grade_report_roundtrip_and_open_review_guard(self):
        fixture = ROOT / "tests" / "fixtures" / "sample_text.txt"
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "report-demo"]), 0)
        self.write_deep_research("report-demo")
        self.assertEqual(kaoda.main(["plan-exam", "report-demo", "--review-mode", "正常模式"]), 0)
        self.assertEqual(kaoda.main(["build-exam", "report-demo"]), 0)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "report-demo"
        exam = json.loads((run_dir / "exam.json").read_text(encoding="utf-8"))
        answers = {q["id"]: q["answer"][0] if q["type"] == "fill_blank" else q["answer"] for q in exam["questions"]}
        attempt = {
            "version": "1.0",
            "learner_id": "reporter",
            "exam_id": exam["exam_id"],
            "run_id": "report-demo",
            "exam_path": "exam.json",
            "answers": answers,
        }
        report_path = run_dir / "kaoda_agent_report.md"
        report_path.write_text(self.agent_report_markdown(exam, attempt), encoding="utf-8")
        self.assertEqual(kaoda.main(["grade-report", str(report_path), "--learner-id", "reporter"]), 0)
        grade = json.loads((run_dir / "grade.json").read_text(encoding="utf-8"))
        self.assertEqual(grade["open_review"]["status"], "not_required")
        self.assertEqual(kaoda.main(["record", str(run_dir / "grade.json")]), 0)

        self.assertEqual(kaoda.main(["plan-exam", "report-demo", "--review-mode", "拷打模式"]), 0)
        self.assertEqual(kaoda.main(["build-exam", "report-demo"]), 0)
        exam = json.loads((run_dir / "exam.json").read_text(encoding="utf-8"))
        answers = {}
        for question in exam["questions"]:
            if question["type"] == "fill_blank":
                answers[question["id"]] = question["answer"][0]
            elif question["type"] == "open":
                answers[question["id"]] = "我会先说明机制，再检查边界、风险、反例和验证步骤。"
            else:
                answers[question["id"]] = question["answer"]
        attempt = {
            "version": "1.0",
            "learner_id": "reporter",
            "exam_id": exam["exam_id"],
            "run_id": "report-demo",
            "exam_path": "exam.json",
            "answers": answers,
        }
        report_path.write_text(self.agent_report_markdown(exam, attempt), encoding="utf-8")
        self.assertEqual(kaoda.main(["grade-report", str(report_path), "--learner-id", "reporter"]), 0)
        grade = json.loads((run_dir / "grade.json").read_text(encoding="utf-8"))
        self.assertEqual(grade["open_review"]["status"], "pending_agent_review")
        self.assertTrue((run_dir / "agent_open_review.md").exists())
        self.assertEqual(kaoda.main(["record", str(run_dir / "grade.json")]), 2)
        grade["open_review"]["status"] = "completed"
        (run_dir / "grade.json").write_text(json.dumps(grade, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertEqual(kaoda.main(["record", str(run_dir / "grade.json")]), 0)

    def test_article_url_ingest_extracts_metadata(self):
        site_dir = Path(self.tmp.name) / "site"
        site_dir.mkdir()
        (site_dir / "index.html").write_text(
            """
            <html><head>
            <title>Token 教程</title>
            <meta name="author" content="Kaoda Author">
            <meta property="article:published_time" content="2026-06-20">
            </head><body>
            <nav>广告和导航</nav>
            <article>
            <h1>Token 教程</h1>
            <p>Token 是模型处理文字的基本单位，机制上由 tokenizer 把文本切成片段。</p>
            <p>边界是它不等同于完整词语，中文、符号和 emoji 都可能改变切分。</p>
            <p>常见误解是把 token 当成普通英文单词，然后错误估算上下文窗口。</p>
            </article>
            </body></html>
            """,
            encoding="utf-8",
        )
        handler = partial(SimpleHTTPRequestHandler, directory=str(site_dir))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
            self.assertEqual(kaoda.main(["ingest", url, "--run-id", "article-demo"]), 0)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "article-demo"
        source = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))
        self.assertEqual(source["input_type"], "article_url")
        self.assertEqual(source["author"], "Kaoda Author")
        self.assertEqual(source["published_time"], "2026-06-20")
        rows = [json.loads(line) for line in (run_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(rows)
        self.assertIn("url", rows[0]["locator"])

    def test_video_subtitle_ingest_uses_ytdlp_stub(self):
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "yt-dlp"
        stub.write_text(
            """#!/usr/bin/env python3
import pathlib, sys
out = sys.argv[sys.argv.index("-o") + 1]
path = pathlib.Path(out.replace("%(id)s", "mock-video").replace("%(ext)s", "vtt"))
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("WEBVTT\\n\\n00:00:01.000 --> 00:00:04.000\\nToken 是模型处理文字的基本单位。\\n\\n00:00:05.000 --> 00:00:08.000\\n边界是 token 不等同于完整词语。\\n", encoding="utf-8")
""",
            encoding="utf-8",
        )
        os.chmod(stub, 0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
        try:
            self.assertEqual(kaoda.main(["ingest", "https://www.youtube.com/watch?v=demo", "--run-id", "video-demo"]), 0)
        finally:
            os.environ["PATH"] = old_path
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "video-demo"
        rows = [json.loads(line) for line in (run_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertIn("timestamp", rows[0]["locator"])

    def test_pdf_ingest_preserves_page_locator_when_pdftotext_exists(self):
        if not kaoda.command_exists("pdftotext"):
            self.skipTest("pdftotext is not installed")
        pdf_path = Path(self.tmp.name) / "token.pdf"
        self.write_minimal_pdf(pdf_path, "Token is model text unit. Boundary is not same as word.")
        self.assertEqual(kaoda.main(["ingest", str(pdf_path), "--run-id", "pdf-demo"]), 0)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "pdf-demo"
        rows = [json.loads(line) for line in (run_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(rows)
        self.assertEqual(rows[0]["locator"].get("page"), 1)

    def test_long_material_scales_checkpoint_count(self):
        fixture = Path(self.tmp.name) / "long.txt"
        fixture.write_text(
            "\n\n".join(
                f"Token 机制说明 {i}：tokenizer 会切分文本，边界是不能把 token 当完整词语，误解会导致上下文估算失败，迁移时要检查场景。"
                for i in range(180)
            ),
            encoding="utf-8",
        )
        self.assertEqual(kaoda.main(["ingest", str(fixture), "--run-id", "long-demo"]), 0)
        self.write_deep_research("long-demo")
        self.assertEqual(kaoda.main(["plan-exam", "long-demo", "--review-mode", "正常模式"]), 0)
        run_dir = Path(os.environ["KAODA_DATA_DIR"]) / "runs" / "long-demo"
        brief = json.loads((run_dir / "exam_brief.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(brief["checkpoint_count"], 30)

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
        self.write_deep_research("mode-demo")
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
        self.write_deep_research("mistake-choice")
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
        self.assertTrue((run_dir / "deep_research.json").exists())
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
