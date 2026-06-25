#!/usr/bin/env python3
"""Kaoda Review CLI.

Local-first pipeline for turning passive learning material into an
interactive understanding diagnostic exam.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


VERSION = "0.1.0"
PACKAGE_SHARE_NAME = "kaoda-review"


def has_skill_resources(root: Path) -> bool:
    return (root / "SKILL.md").exists() and (root / "assets" / "exam-template" / "index.html").exists()


def resolve_root(
    module_file: Path | str | None = None,
    env: dict[str, str] | None = None,
    prefix: Path | str | None = None,
) -> Path:
    env = env if env is not None else os.environ
    module_path = Path(module_file or __file__).resolve()
    prefix_path = Path(prefix or sys.prefix)
    candidates: list[Path] = []
    if env.get("KAODA_SKILL_ROOT"):
        candidates.append(Path(env["KAODA_SKILL_ROOT"]).expanduser())
    candidates.append(module_path.parents[1])
    candidates.append(prefix_path / "share" / PACKAGE_SHARE_NAME)
    for candidate in candidates:
        candidate = candidate.resolve()
        if has_skill_resources(candidate):
            return candidate
    return module_path.parents[1].resolve()


def default_data_dir_for(root: Path) -> Path:
    if (root / "scripts" / "kaoda.py").exists():
        return root / "data"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / PACKAGE_SHARE_NAME


ROOT = resolve_root()
DEFAULT_DATA_DIR = default_data_dir_for(ROOT)
TEMPLATE_PATH = ROOT / "assets" / "exam-template" / "index.html"

ABILITY_TYPES = [
    "复述检查",
    "为什么追问",
    "边界识别",
    "错误理解识别",
    "迁移应用",
    "反例判断",
    "落地追问",
]

MISTAKE_TAGS = [
    "concept_confusion",
    "mechanism_missing",
    "boundary_blindness",
    "false_transfer",
    "counterexample_blindness",
    "application_gap",
    "evidence_missing",
]

MISTAKE_TAG_LABELS = {
    "concept_confusion": "概念混淆",
    "mechanism_missing": "机制缺失",
    "boundary_blindness": "边界盲区",
    "false_transfer": "迁移误用",
    "counterexample_blindness": "反例盲区",
    "application_gap": "落地断层",
    "evidence_missing": "证据不足",
    "unknown": "未分类错因",
}

SCENARIO_POOL = [
    "把这个知识用于一个真实工作项目",
    "向同事解释并说服对方采纳",
    "发现方案失败后定位原因",
    "在面试中被追问边界条件",
    "老板要求你把概念转成可落地动作",
    "用同一原则判断一个相反案例",
    "把学到的方法迁移到另一个工具",
]

DEFAULT_QUESTION_PROFILE = [
    "复述检查",
    "为什么追问",
    "边界识别",
    "错误理解识别",
    "迁移应用",
    "反例判断",
    "落地追问",
]

DEFAULT_REVIEW_CHECKPOINTS = 20
MIN_REVIEW_CHECKPOINTS = 15
MAX_REVIEW_CHECKPOINTS = 50

REVIEW_MODES = {
    "复盘模式": {
        "label": "复盘模式 · 5分钟",
        "duration_minutes": 5,
        "checkpoint_count": 15,
        "description": "纯客观题，快速回顾，网页内直接出分。",
    },
    "正常模式": {
        "label": "正常模式 · 10分钟",
        "duration_minutes": 10,
        "checkpoint_count": 20,
        "description": "客观题为主，默认不含简答，适合日常复盘。",
    },
    "拷打模式": {
        "label": "拷打模式 · 30分钟",
        "duration_minutes": 30,
        "checkpoint_count": 30,
        "description": "客观题为主，加入少量简答/口述追问。",
    },
    "深度拷打": {
        "label": "深度拷打 · 45分钟",
        "duration_minutes": 45,
        "checkpoint_count": 20,
        "description": "简答/口述占比较高，用于面试、表达训练和深度追问。",
    },
}

QUESTION_STYLE_FRAMES = [
    {
        "id": "serious_review",
        "label": "正经复盘",
        "cue": "核对条件、证据和边界。",
    },
    {
        "id": "fun_drill",
        "label": "趣味拷打",
        "cue": "表达轻松，问题要清楚。",
    },
    {
        "id": "sharp_roast",
        "label": "毒舌拷打",
        "cue": "直接指出薄弱理解。",
    },
    {
        "id": "concept_scam",
        "label": "概念诈骗识别",
        "cue": "别被名词骗了，先看它到底解决什么问题。",
    },
    {
        "id": "friend_roast",
        "label": "朋友吐槽",
        "cue": "朋友听完你的解释后开始挑刺：你是不是只是在背词？",
    },
    {
        "id": "boss_followup",
        "label": "老板追问",
        "cue": "老板不关心你会不会背，他要你说明怎么落地。",
    },
    {
        "id": "counterexample_hunt",
        "label": "反例猎人",
        "cue": "先找会翻车的情况，再判断你是不是真的懂。",
    },
    {
        "id": "transfer_scene",
        "label": "迁移现场",
        "cue": "换一个场景还能用，才算没有把案例当答案。",
    },
    {
        "id": "danmu_judgement",
        "label": "弹幕判断",
        "cue": "弹幕里有人说得很自信，但自信不等于理解。",
    },
    {
        "id": "one_glance_fake",
        "label": "可疑说法识别",
        "cue": "识别听起来顺但条件不足的说法。",
    },
    {
        "id": "interviewer_drill",
        "label": "面试追问",
        "cue": "面试官继续追：条件变了，你的答案还成立吗？",
    },
]

QUESTION_STYLE_OPTIONS = [
    "正经复盘",
    "趣味拷打",
    "毒舌拷打",
    "面试官追问",
    "老板追问",
    "朋友吐槽",
    "反例猎人",
    "概念诈骗识别",
    "弹幕判断",
    "混合风格",
]

QUESTION_STYLE_ALIASES = {
    "正经考试模式": "正经复盘",
    "有趣拷打模式": "趣味拷打",
    "毒舌考官模式": "毒舌拷打",
    "面试官模式": "面试官追问",
    "老板追问模式": "老板追问",
    "朋友吐槽模式": "朋友吐槽",
    "融合模式": "混合风格",
}

STYLE_FAMILY_BY_OPTION = {
    "正经复盘": ["serious_review"],
    "趣味拷打": ["fun_drill", "concept_scam", "danmu_judgement", "one_glance_fake"],
    "毒舌拷打": ["sharp_roast", "one_glance_fake", "concept_scam"],
    "面试官追问": ["interviewer_drill"],
    "老板追问": ["boss_followup"],
    "朋友吐槽": ["friend_roast"],
    "反例猎人": ["counterexample_hunt"],
    "概念诈骗识别": ["concept_scam"],
    "弹幕判断": ["danmu_judgement"],
    "混合风格": [],
}

MISTAKE_KNOWLEDGE_POLICIES = [
    "只复盘当前材料",
    "加入历史错题",
    "重点拷最近错题",
    "当前材料为主，错题为辅",
]

QUESTION_SECTION_ORDER = ["single_choice", "multiple_choice", "true_false", "fill_blank", "open"]
QUESTION_TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "true_false": "判断题",
    "fill_blank": "填空题",
    "open": "简答/口述题",
}

BAD_VISIBLE_PROMPT_PATTERNS = [
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

BAD_VISIBLE_CONDITION_PATTERNS = [
    "根据材料",
    "符合材料",
    "材料里",
    "材料对",
    "材料中的",
    "材料里的",
]

INFORMATION_CUES = [
    "为什么",
    "因为",
    "所以",
    "机制",
    "原理",
    "条件",
    "边界",
    "不成立",
    "不适用",
    "误解",
    "错误",
    "风险",
    "失败",
    "反例",
    "迁移",
    "应用",
    "落地",
    "真正",
    "只会",
    "至少",
    "why",
    "because",
    "mechanism",
    "boundary",
    "condition",
    "risk",
    "failure",
    "counterexample",
    "transfer",
]

LOW_VALUE_SEGMENT_PATTERNS = [
    r"^\s*(大家好|各位同學|各位同学|hello|hi)\b",
    r"^\s*(今天[这這]堂课|欢迎|subscribe|like and subscribe)",
    r"^\s*(点赞|投币|收藏|关注|一键三连)",
]

CHINESE_TOPIC_CUES = [
    "理解",
    "机制",
    "原理",
    "条件",
    "边界",
    "误解",
    "风险",
    "失败",
    "反例",
    "迁移",
    "应用",
    "落地",
    "错因",
]

GENERIC_TOPIC_STOPWORDS = {
    "例如",
    "应该",
    "不能",
    "不要",
    "可以",
    "需要",
    "用户",
    "项目",
    "系统",
    "内容",
    "材料",
    "问题",
    "模块",
    "阶段",
    "格式",
    "建议",
    "当前",
    "之后",
    "其中",
    "包括",
    "以下",
    "标准",
    "链接",
    "我的答案",
    "正确答案",
    "根据材料",
    "根据材料选择",
    "核心问题总结",
    "主要问题包括",
    "产品逻辑重新划分",
    "这个项目需要明确区分四个东西",
    "它只需要告诉用户",
    "类比真实考试场景",
    "错题集的重点是让用户一眼看懂",
    "错题集的结构建议如下",
    "每一道错题包含",
    "题目",
    "知识解读",
    "大白话解释",
    "建议改成",
    "每道题必须绑定",
    "特别注意",
    "错误示例",
    "正确做法",
    "错题",
    "考试",
    "复盘",
    "engineering",
}

STRUCTURAL_TOPIC_RULES = [
    (r"考试结果页|成绩单|成绩反馈", "考试结果页"),
    (r"错题集", "错题集"),
    (r"错题卡片结构|每一道错题包含", "错题卡片结构"),
    (r"错题笔记", "错题笔记合并"),
    (r"学习报告", "学习报告"),
    (r"Agent\s*讲解|Agent\s*复盘", "Agent 讲解复盘"),
    (r"考试知识库", "考试知识库"),
    (r"出题链路|出题流程|材料、研究、题目、答案", "出题链路"),
    (r"每道题必须绑定|材料依据|评分标准|常见错误答案", "题目依据绑定"),
    (r"根据材料|题目语言|题目条件|提供材料片段", "题目条件一致性"),
    (r"考卷命名|考卷名称|命名规则", "考卷命名规则"),
    (r"视觉风格|设计风格", "视觉风格统一"),
    (r"语言风格|AI 味|大白话", "语言风格"),
    (r"看板|学习闭环|下一步建议", "学习闭环看板"),
    (r"Loop\s*Engineering|循环优化|目标\s*→\s*计划", "Loop Engineering 优化机制"),
]

AUDIO_FILE_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_FILE_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".txt", ".md", ".markdown"}
ARTICLE_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "button"}
ARTICLE_JUNK_ATTR_PATTERN = re.compile(
    r"\b(comment|comments|advert|advertisement|ad-|ads|sidebar|cookie|modal|subscribe|share|related|recommend)\b",
    re.I,
)


class KaodaError(RuntimeError):
    """Actionable CLI error."""


@dataclass
class Segment:
    segment_id: str
    source_id: str
    text: str
    locator: dict[str, Any]
    kind: str = "source"

    def as_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "source_id": self.source_id,
            "kind": self.kind,
            "locator": self.locator,
            "text": self.text,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def data_dir() -> Path:
    return Path(os.environ.get("KAODA_DATA_DIR", DEFAULT_DATA_DIR)).resolve()


def stable_slug(value: str, length: int = 10) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def make_run_id(source: str) -> str:
    stamp = utc_now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{stable_slug(source, 8)}"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_cmd(args: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def is_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_video_url(value: str) -> bool:
    host = urllib.parse.urlparse(value).netloc.lower()
    return any(
        token in host
        for token in [
            "youtube.com",
            "youtu.be",
            "bilibili.com",
            "b23.tv",
            "vimeo.com",
            "coursera.org",
        ]
    )


def detect_input(value: str) -> str:
    if is_url(value):
        return "video_url" if is_video_url(value) else "article_url"
    path = Path(value).expanduser()
    if path.exists():
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix in {".srt", ".vtt"}:
            return "subtitle"
        if suffix in {".txt", ".md", ".markdown"}:
            return "text_file"
        if suffix in AUDIO_FILE_SUFFIXES:
            return "audio_file"
        if suffix in VIDEO_FILE_SUFFIXES:
            return "video_file"
        raise KaodaError(
            f"Unsupported file type: {suffix}. Use PDF, SRT, VTT, TXT, MD, or common audio/video files."
        )
    return "inline_text"


def normalize_text(text: str) -> str:
    text = text.replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_learning_text(text: str) -> str:
    text = normalize_text(text)
    filler_patterns = [
        r"(?im)^\s*(点赞|投币|收藏|关注|一键三连|subscribe|like and subscribe).*$",
        r"(?im)^\s*(大家好|hello everyone|hi everyone)[，,!\s]*$",
    ]
    for pattern in filler_patterns:
        text = re.sub(pattern, "", text)
    lines = []
    seen_recent: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        normalized = re.sub(r"\W+", "", line.lower())
        if normalized and normalized in seen_recent[-3:]:
            continue
        seen_recent.append(normalized)
        lines.append(line)
    return normalize_text("\n".join(lines))


def split_paragraphs(text: str, max_chars: int = 900) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|(?<=[。！？.!?])\s+", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= max_chars:
            current = f"{current}\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            if len(para) <= max_chars:
                current = para
            else:
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i : i + max_chars])
                current = ""
    if current:
        chunks.append(current)
    return chunks or ([text[:max_chars]] if text else [])


def make_segments_from_text(
    text: str,
    source_id: str,
    locator_base: dict[str, Any] | None = None,
    kind: str = "source",
) -> list[Segment]:
    cleaned = clean_learning_text(text)
    chunks = split_paragraphs(cleaned)
    segments: list[Segment] = []
    for index, chunk in enumerate(chunks, 1):
        locator = dict(locator_base or {})
        locator["chunk"] = index
        segments.append(
            Segment(
                segment_id=f"{source_id}-seg-{index:04d}",
                source_id=source_id,
                kind=kind,
                locator=locator,
                text=chunk,
            )
        )
    return segments


def parse_timestamp(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
    except ValueError:
        return 0.0
    return 0.0


def parse_subtitle(path: Path, source_id: str) -> list[Segment]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    segments: list[Segment] = []
    index = 0
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing_line = next((line for line in lines if "-->" in line), "")
        if not timing_line:
            continue
        content_lines = [
            re.sub(r"<[^>]+>", "", line)
            for line in lines
            if "-->" not in line and not re.fullmatch(r"\d+", line)
        ]
        content = clean_learning_text(" ".join(content_lines))
        if not content:
            continue
        index += 1
        start, _, end = timing_line.partition("-->")
        locator = {
            "timestamp_start": parse_timestamp(start.strip().split(" ")[0]),
            "timestamp_end": parse_timestamp(end.strip().split(" ")[0]),
            "timestamp": timing_line,
        }
        segments.append(
            Segment(
                segment_id=f"{source_id}-seg-{index:04d}",
                source_id=source_id,
                locator=locator,
                text=content,
            )
        )
    if not segments:
        raise KaodaError(f"No subtitle segments found in {path}")
    return segments


def find_sidecar_transcript(path: Path) -> Path | None:
    direct = [path.with_suffix(suffix) for suffix in TRANSCRIPT_SUFFIXES]
    fuzzy = [
        candidate
        for candidate in sorted(path.parent.glob(f"{path.stem}.*"))
        if candidate.suffix.lower() in TRANSCRIPT_SUFFIXES
    ]
    for candidate in direct + fuzzy:
        if candidate.exists() and candidate.is_file() and candidate.resolve() != path.resolve():
            return candidate.resolve()
    return None


def extract_media_file_transcript(path: Path, run_dir: Path) -> tuple[list[Segment], dict[str, Any]]:
    source_id = f"media-{stable_slug(str(path.resolve()), 8)}"
    sidecar = find_sidecar_transcript(path)
    metadata: dict[str, Any] = {
        "method": "media sidecar transcript",
        "path": str(path),
        "sidecar_transcript": str(sidecar) if sidecar else None,
    }
    if not sidecar:
        raise KaodaError(
            "Audio/video file needs a same-name SRT/VTT/TXT/MD transcript, or a local transcription step before ingest."
        )
    if sidecar.suffix.lower() in {".srt", ".vtt"}:
        segments = parse_subtitle(sidecar, source_id)
    else:
        text = sidecar.read_text(encoding="utf-8", errors="replace")
        segments = make_segments_from_text(
            text,
            source_id,
            locator_base={"media_path": str(path), "transcript_path": str(sidecar)},
        )
    if not segments:
        raise KaodaError(f"No usable transcript text found next to media file: {path}")
    return segments, metadata


def extract_video_subtitles(url: str, run_dir: Path) -> tuple[list[Segment], dict[str, Any]]:
    if not command_exists("yt-dlp"):
        raise KaodaError("yt-dlp is required for video URLs. Install yt-dlp or provide an SRT/VTT/TXT file.")

    raw_dir = ensure_dir(run_dir / "raw")
    output_template = str(raw_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-sub",
        "--write-auto-sub",
        "--sub-langs",
        "zh-Hans,zh-CN,zh,en.*",
        "--convert-subs",
        "vtt",
        "-o",
        output_template,
        url,
    ]
    result = run_cmd(cmd, timeout=180)
    metadata = {
        "method": "yt-dlp subtitles",
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "stderr_tail": result.stderr[-2000:],
    }
    subtitle_files = sorted(raw_dir.glob("*.vtt")) + sorted(raw_dir.glob("*.srt"))
    if not subtitle_files:
        raise KaodaError(
            "No subtitles were extracted. Provide an SRT/VTT/TXT file, or retry with a playable video and valid cookies."
        )
    source_id = f"video-{stable_slug(url, 8)}"
    segments = parse_subtitle(subtitle_files[0], source_id)
    return segments, metadata


def extract_pdf(path: Path, run_dir: Path) -> tuple[list[Segment], dict[str, Any]]:
    source_id = f"pdf-{stable_slug(str(path.resolve()), 8)}"
    metadata: dict[str, Any] = {"method": "pdf text extraction", "path": str(path), "attempts": []}
    text = ""
    if command_exists("pdftotext"):
        result = run_cmd(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"], timeout=120)
        metadata["attempts"].append("pdftotext")
        metadata["pdftotext_returncode"] = result.returncode
        metadata["pdftotext_stderr_tail"] = result.stderr[-1000:]
        if result.returncode == 0:
            text = result.stdout
            metadata["method"] = "pdftotext"
    if len(text.strip()) < 50:
        stdlib_text = extract_pdf_text_stdlib(path)
        metadata["attempts"].append("stdlib_pdf_text")
        metadata["stdlib_text_chars"] = len(stdlib_text.strip())
        if len(stdlib_text.strip()) >= 30:
            text = stdlib_text
            metadata["method"] = "stdlib_pdf_text"
    if len(text.strip()) < 50:
        metadata["method"] = "ocr"
        metadata["attempts"].append("ocr")
        text = ocr_pdf(path, run_dir)
    pages = text.split("\f") if "\f" in text else [text]
    segments: list[Segment] = []
    for page_number, page_text in enumerate(pages, 1):
        for segment in make_segments_from_text(
            page_text,
            source_id=f"{source_id}-p{page_number}",
            locator_base={"page": page_number},
        ):
            segments.append(segment)
    if not segments:
        raise KaodaError(f"No text could be extracted from PDF: {path}")
    return segments, metadata


def decode_pdf_literal(raw: bytes) -> str:
    out = bytearray()
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != 0x5C:
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(raw):
            break
        escaped = raw[index]
        index += 1
        if escaped in b"nrtbf":
            out.append({ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}[escaped])
        elif escaped in b"()\\":
            out.append(escaped)
        elif 48 <= escaped <= 55:
            octal = bytes([escaped])
            for _ in range(2):
                if index < len(raw) and 48 <= raw[index] <= 55:
                    octal += bytes([raw[index]])
                    index += 1
            out.append(int(octal, 8) & 0xFF)
        elif escaped in {10, 13}:
            if escaped == 13 and index < len(raw) and raw[index] == 10:
                index += 1
        else:
            out.append(escaped)
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return out.decode("latin-1", errors="replace")


def extract_pdf_text_stdlib(path: Path) -> str:
    raw = path.read_bytes()
    pieces: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        stream = match.group(1).strip(b"\r\n")
        header = raw[max(0, match.start() - 600) : match.start()]
        if b"/FlateDecode" in header:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        for literal in re.finditer(rb"\((?:\\.|[^\\()])*\)", stream):
            value = decode_pdf_literal(literal.group(0)[1:-1]).strip()
            if value:
                pieces.append(value)
    return clean_learning_text(" ".join(pieces))


def ocr_pdf(path: Path, run_dir: Path) -> str:
    if not (command_exists("pdftoppm") and command_exists("tesseract")):
        raise KaodaError(
            "PDF appears scanned and OCR tools are missing. Install pdftoppm+tesseract or provide extracted text."
        )
    image_prefix = run_dir / "raw" / "page"
    ensure_dir(image_prefix.parent)
    result = run_cmd(["pdftoppm", "-png", "-r", "180", str(path), str(image_prefix)], timeout=180)
    if result.returncode != 0:
        raise KaodaError(f"pdftoppm failed: {result.stderr[-1000:]}")
    texts: list[str] = []
    for image in sorted(image_prefix.parent.glob("page-*.png")):
        out_base = image.with_suffix("")
        ocr = run_cmd(["tesseract", str(image), str(out_base), "-l", "chi_sim+eng"], timeout=180)
        if ocr.returncode == 0:
            txt = out_base.with_suffix(".txt")
            if txt.exists():
                texts.append(txt.read_text(encoding="utf-8", errors="replace"))
    return "\f".join(texts)


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_stack: list[str] = []
        self.in_title = False
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        attr_text = " ".join(
            attrs_dict.get(name, "") for name in ["id", "class", "role", "aria-label", "data-testid"]
        )
        if self.skip_stack:
            self.skip_stack.append(tag)
            return
        if tag in ARTICLE_SKIP_TAGS or ARTICLE_JUNK_ATTR_PATTERN.search(attr_text):
            self.skip_stack.append(tag)
            return
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content", "")
            if name in {"author", "article:author", "og:title", "article:published_time", "date"}:
                self.meta[name] = content

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_stack and self.skip_stack[-1] == tag:
            self.skip_stack.pop()
            return
        if self.skip_stack:
            return
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3"}:
            self.body_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            return
        value = data.strip()
        if not value:
            return
        if self.in_title:
            self.title_parts.append(value)
        self.body_parts.append(value)


def extract_article(url: str) -> tuple[list[Segment], dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "kaoda-review/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    encoding = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    document = raw.decode(encoding, errors="replace")
    parser = ArticleParser()
    parser.feed(document)
    body = clean_learning_text("\n".join(parser.body_parts))
    title = clean_learning_text(" ".join(parser.title_parts)) or parser.meta.get("og:title") or url
    if len(body) < 80:
        raise KaodaError("Article text is too thin after cleanup. Paste the article正文 or provide a readable copy.")
    source_id = f"article-{stable_slug(url, 8)}"
    segments = make_segments_from_text(body, source_id, locator_base={"url": url})
    metadata = {
        "method": "urllib+htmlparser",
        "url": url,
        "title": title,
        "author": parser.meta.get("author") or parser.meta.get("article:author"),
        "published_time": parser.meta.get("article:published_time") or parser.meta.get("date"),
    }
    return segments, metadata


def manual_input_kind(input_type: str) -> str:
    if input_type in {"video_url", "audio_file", "video_file"}:
        return "transcript"
    if input_type == "article_url":
        return "article_text"
    return "source_text"


def write_text_needed_workspace(run_dir: Path, source: dict[str, Any], reason: str) -> dict[str, Any]:
    kind = manual_input_kind(str(source.get("input_type", "")))
    filename = "manual_transcript.txt" if kind == "transcript" else "manual_input.txt"
    manual_path = run_dir / filename
    prompt_path = run_dir / "manual_text_request.md"
    source_status = {
        "version": "1.0",
        "run_id": source["run_id"],
        "status": "needs_text",
        "reason": reason,
        "manual_input_kind": kind,
        "manual_input_path": str(manual_path),
        "next_command": f"python scripts/kaoda.py ingest-manual {source['run_id']}",
    }
    source.update(
        {
            "status": "needs_text",
            "extraction_error": reason,
            "manual_input_kind": kind,
            "manual_input_path": str(manual_path),
        }
    )
    if not manual_path.exists():
        if kind == "transcript":
            label = "请把视频/音频的字幕、转写稿或课程文字稿粘贴到这里。"
        elif kind == "article_text":
            label = "请把文章标题、作者/日期（如有）和正文粘贴到这里。"
        else:
            label = "请把资料中可用于学习复盘的正文粘贴到这里。"
        manual_path.write_text(
            "\n".join(
                [
                    label,
                    "保留页码、时间戳或小标题更好；没有也可以直接粘贴正文。",
                    "",
                    "KAODA_REPLACE_THIS_TEXT",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    prompt_path.write_text(
        "\n".join(
            [
                "# 需要补充可读文本",
                "",
                f"- run_id: {source['run_id']}",
                f"- input_type: {source.get('input_type')}",
                f"- input: {source.get('input')}",
                f"- reason: {reason}",
                "",
                "下一步：",
                f"1. 把可读正文/字幕粘贴到 `{manual_path.name}`。",
                f"2. 运行 `python scripts/kaoda.py ingest-manual {source['run_id']}`。",
                "3. 继续 deep research -> plan-exam -> build-exam。",
                "",
                "不要根据标题、URL 或文件名直接编题。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_json(run_dir / "source.json", source)
    write_json(run_dir / "source_status.json", source_status)
    print_path(
        run_dir / "source_status.json",
        {
            "run_id": source["run_id"],
            "status": "needs_text",
            "manual_input": str(manual_path),
            "next": source_status["next_command"],
        },
    )
    return {"run_id": source["run_id"], "run_dir": str(run_dir), "status": "needs_text"}


def ingest(args: argparse.Namespace) -> dict[str, Any]:
    input_value = args.input
    input_type = detect_input(input_value)
    run_id = args.run_id or make_run_id(input_value)
    run_dir = ensure_dir(data_dir() / "runs" / run_id)
    source: dict[str, Any] = {
        "run_id": run_id,
        "input": input_value,
        "input_type": input_type,
        "created_at": iso_now(),
    }

    try:
        if input_type == "video_url":
            segments, metadata = extract_video_subtitles(input_value, run_dir)
        elif input_type == "article_url":
            segments, metadata = extract_article(input_value)
        elif input_type == "pdf":
            segments, metadata = extract_pdf(Path(input_value).expanduser().resolve(), run_dir)
        elif input_type in {"audio_file", "video_file"}:
            segments, metadata = extract_media_file_transcript(Path(input_value).expanduser().resolve(), run_dir)
        elif input_type == "subtitle":
            path = Path(input_value).expanduser().resolve()
            segments = parse_subtitle(path, f"subtitle-{stable_slug(str(path), 8)}")
            metadata = {"method": "subtitle parser", "path": str(path)}
        elif input_type == "text_file":
            path = Path(input_value).expanduser().resolve()
            text = path.read_text(encoding="utf-8", errors="replace")
            segments = make_segments_from_text(text, f"text-{stable_slug(str(path), 8)}", {"path": str(path)})
            metadata = {"method": "text file", "path": str(path)}
        else:
            segments = make_segments_from_text(input_value, f"inline-{stable_slug(input_value, 8)}", {"input": "inline"})
            metadata = {"method": "inline text"}
    except KaodaError as exc:
        if input_type in {"video_url", "article_url", "pdf", "audio_file", "video_file"}:
            return write_text_needed_workspace(run_dir, source, str(exc))
        raise

    source.update(metadata)
    write_json(run_dir / "source.json", source)
    rows = [segment.as_dict() for segment in segments]
    write_jsonl(run_dir / "segments.jsonl", rows)
    report = build_material_report(run_id, source, rows)
    write_json(run_dir / "material_report.json", report)
    print_path(run_dir / "segments.jsonl", {"run_id": run_id, "segments": len(rows)})
    return {"run_id": run_id, "run_dir": str(run_dir)}


def ingest_manual(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id
    run_dir = ensure_dir(data_dir() / "runs" / run_id)
    source_path = run_dir / "source.json"
    if not source_path.exists():
        raise KaodaError(f"source.json missing for {run_id}. Run ingest first.")
    source = read_json(source_path)
    manual_path = Path(args.text_file).expanduser().resolve() if args.text_file else None
    if manual_path is None:
        stored = source.get("manual_input_path")
        candidates = [
            Path(stored).expanduser() if stored else None,
            run_dir / "manual_transcript.txt",
            run_dir / "manual_input.txt",
        ]
        manual_path = next((candidate for candidate in candidates if candidate and candidate.exists()), None)
    if manual_path is None or not manual_path.exists():
        raise KaodaError(f"Manual text file missing for {run_id}. Fill manual_input.txt or manual_transcript.txt first.")
    text = manual_path.read_text(encoding="utf-8", errors="replace")
    if "KAODA_REPLACE_THIS_TEXT" in text or len(clean_learning_text(text)) < 40:
        raise KaodaError("Manual text is still empty or too thin. Paste the real transcript/article/source text first.")
    original_type = str(source.get("input_type", "manual"))
    source_id = f"manual-{stable_slug(run_id + str(manual_path), 8)}"
    locator_base = {
        "manual_input": str(manual_path),
        "original_input": source.get("input"),
        "original_input_type": original_type,
    }
    if original_type == "article_url" and is_url(str(source.get("input", ""))):
        locator_base["url"] = source.get("input")
    segments = make_segments_from_text(text, source_id, locator_base=locator_base)
    rows = [segment.as_dict() for segment in segments]
    source.update(
        {
            "status": "ready",
            "method": "manual text fallback",
            "manual_text_path": str(manual_path),
            "manual_ingested_at": iso_now(),
        }
    )
    write_json(source_path, source)
    write_jsonl(run_dir / "segments.jsonl", rows)
    report = build_material_report(run_id, source, rows)
    write_json(run_dir / "material_report.json", report)
    status_path = run_dir / "source_status.json"
    if status_path.exists():
        status = read_json(status_path)
        status["status"] = "ready"
        status["segments"] = len(rows)
        status["manual_text_path"] = str(manual_path)
        write_json(status_path, status)
    print_path(run_dir / "segments.jsonl", {"run_id": run_id, "segments": len(rows), "source": "manual_text"})
    return {"run_id": run_id, "run_dir": str(run_dir), "segments": len(rows)}


def write_topic_research_prompt(run_dir: Path, topic: str) -> None:
    content = f"""# 主题研究任务：{topic}

用户只给了一个想了解的主题，没有给视频、PDF 或文章。agent 不能直接出题，必须先完成小型研究。

## 研究要求

1. 查找 3-5 个可靠来源，优先官方文档、教材、论文、权威解释或高质量技术文章。
2. 写清楚这个主题的机制、边界、常见误解、反例和迁移场景。
3. 区分事实、推论和例子；不要把未经核验的说法写成确定结论。
4. 把研究笔记写到同目录 `topic_research.md`。
5. 把来源写到同目录 `source_links.json`，格式为：

```json
{{
  "sources": [
    {{"title": "Source title", "url": "https://example.com", "why_used": "一句话说明"}}
  ]
}}
```

## topic_research.md 建议结构

- 主题一句话定义
- 核心机制
- 关键边界
- 常见误解
- 反例/失败案例
- 迁移应用场景
- 需要继续确认的问题

完成后运行：

```bash
python scripts/kaoda.py ingest-topic {run_dir.name}
```
"""
    (run_dir / "topic_research_prompt.md").write_text(content, encoding="utf-8")


def research_topic(args: argparse.Namespace) -> dict[str, Any]:
    topic = clean_learning_text(args.topic)
    if not topic:
        raise KaodaError("Topic cannot be empty.")
    run_id = args.run_id or f"topic-{stable_slug(topic, 8)}"
    run_dir = ensure_dir(data_dir() / "runs" / run_id)
    request = {
        "version": "1.0",
        "run_id": run_id,
        "topic": topic,
        "created_at": iso_now(),
        "status": "needs_agent_research",
        "next_required_file": "topic_research.md",
        "notes": "agent must research before ingest-topic; do not generate questions from the bare topic.",
    }
    write_json(run_dir / "topic_request.json", request)
    write_json(run_dir / "source_links.json", {"sources": []})
    write_topic_research_prompt(run_dir, topic)
    print_path(run_dir / "topic_research_prompt.md", {"run_id": run_id, "topic": topic})
    return request


def ingest_topic(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id
    run_dir = ensure_dir(data_dir() / "runs" / run_id)
    request_path = run_dir / "topic_request.json"
    request = read_json(request_path) if request_path.exists() else {}
    topic = args.topic or request.get("topic") or run_id
    notes_path = Path(args.notes).expanduser().resolve() if args.notes else run_dir / "topic_research.md"
    if not notes_path.exists():
        raise KaodaError(
            f"topic_research.md missing for {run_id}. Run research-topic first, complete the research note, then run ingest-topic."
        )
    text = notes_path.read_text(encoding="utf-8", errors="replace")
    if "TODO" in text[:400] or len(clean_learning_text(text)) < 120:
        raise KaodaError("topic_research.md is too thin or still contains TODO. Complete focused research before ingest-topic.")
    sources_path = Path(args.sources).expanduser().resolve() if args.sources else run_dir / "source_links.json"
    sources: list[dict[str, Any]] = []
    if sources_path.exists():
        source_payload = read_json(sources_path)
        if isinstance(source_payload, dict):
            sources = source_payload.get("sources", [])
        elif isinstance(source_payload, list):
            sources = source_payload
    source_id = f"topic-{stable_slug(topic, 8)}"
    source: dict[str, Any] = {
        "run_id": run_id,
        "input": topic,
        "input_type": "topic_research",
        "created_at": iso_now(),
        "method": "agent-curated topic research",
        "title": f"主题研究：{topic}",
        "research_notes_path": str(notes_path),
        "sources": sources,
    }
    segments = make_segments_from_text(
        text,
        source_id,
        locator_base={"topic": topic, "research_note": str(notes_path)},
        kind="topic_research",
    )
    rows = [segment.as_dict() for segment in segments]
    write_json(run_dir / "source.json", source)
    write_jsonl(run_dir / "segments.jsonl", rows)
    report = build_material_report(run_id, source, rows)
    report["topic_research"] = {"topic": topic, "sources": sources, "notes_path": str(notes_path)}
    write_json(run_dir / "material_report.json", report)
    if not (run_dir / "deep_research.json").exists():
        write_json(
            run_dir / "deep_research.json",
            build_deep_research_from_report(report, rows, sources=sources),
        )
    print_path(run_dir / "segments.jsonl", {"run_id": run_id, "topic": topic, "segments": len(rows)})
    return {"run_id": run_id, "run_dir": str(run_dir)}


def normalize_keyword_token(token: str, max_chars: int = 14) -> str:
    if re.fullmatch(r"[\u4e00-\u9fff]+", token):
        if "错误的理解" in token:
            return "错误理解识别"
        if "不是" in token and len(token.split("不是", 1)[0]) >= 2:
            token = token.split("不是", 1)[0]
        if "转化成" in token and len(token.split("转化成", 1)[1]) >= 2:
            token = token.split("转化成", 1)[1]
        if "转化为" in token and len(token.split("转化为", 1)[1]) >= 2:
            token = token.split("转化为", 1)[1]
    if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > max_chars:
        cue_pos = [(token.find(cue), cue) for cue in CHINESE_TOPIC_CUES if cue in token]
        if cue_pos:
            pos, cue = min(cue_pos, key=lambda item: item[0])
            start = max(0, pos - 4)
            end = min(len(token), pos + len(cue) + 6)
            return token[start:end]
        return token[:max_chars]
    return token


def is_weak_keyword(token: str) -> bool:
    weak_prefixes = ["如果", "但是", "所以", "因为", "却", "并"]
    weak_fragments = ["大家好", "欢迎来到", "来到课程", "点赞", "投币", "收藏", "关注", "subscribe"]
    return any(token.startswith(prefix) for prefix in weak_prefixes) or any(fragment in token for fragment in weak_fragments)


def is_bad_topic_name(token: str) -> bool:
    cleaned = normalize_keyword_token(token).strip(" ：:，,。；;、")
    lowered = cleaned.lower()
    if not cleaned or lowered in GENERIC_TOPIC_STOPWORDS:
        return True
    if len(cleaned) < 2:
        return True
    if cleaned.startswith(
        (
            "主要问题",
            "这个项目",
            "它只需要",
            "它的目标",
            "类比",
            "如果用户回答错了",
            "如果没有材料",
            "如果有材料",
            "阅读以下材料",
            "边界是",
            "它不是",
            "是",
        )
    ):
        return True
    if cleaned.endswith(("如下", "包括", "看懂", "应该包含")):
        return True
    if re.fullmatch(r"[A-Za-z]+", cleaned) and lowered not in {"agent", "workflow", "rag", "token"}:
        return True
    if cleaned.endswith(("是什么", "为什么", "怎么做")):
        return True
    return False


def normalize_heading_topic(line: str) -> str:
    topic = line.strip()
    topic = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", topic)
    topic = re.sub(r"^\d+[.、．]\s*", "", topic)
    topic = re.split(r"[：:]", topic, maxsplit=1)[0].strip()
    topic = re.sub(r"^(为本项目设计|本项目|当前)", "", topic).strip()
    topic = topic.strip("“”\"'：:，,。；;、")
    if "Loop Engineering" in topic and "机制" in topic:
        return "Loop Engineering 优化机制"
    if len(topic) > 18:
        for cue in ["优化", "规则", "机制", "阶段", "模块", "流程", "链路", "风格", "报告", "看板"]:
            pos = topic.find(cue)
            if pos >= 0:
                topic = topic[: pos + len(cue)]
                break
    return topic


def structural_topic_candidates(text: str, limit: int = 18) -> list[str]:
    rule_candidates: list[str] = []
    heading_candidates: list[str] = []

    def add(bucket: list[str], value: str) -> None:
        value = normalize_keyword_token(normalize_heading_topic(value), max_chars=18)
        if value and not is_bad_topic_name(value) and value not in bucket:
            bucket.append(value)

    for raw_line in clean_learning_text(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for pattern, topic in STRUCTURAL_TOPIC_RULES:
            if re.search(pattern, line, re.I):
                add(rule_candidates, topic)
        looks_like_heading = bool(re.match(r"^([一二三四五六七八九十]+[、.．]|\d+[.、．])", line))
        has_heading_colon = "：" in line or ":" in line
        if looks_like_heading or (has_heading_colon and len(line) <= 36):
            add(heading_candidates, line)

    candidates: list[str] = []
    seen: set[str] = set()
    for value in rule_candidates + heading_candidates:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(value)
        if len(candidates) >= limit:
            break
    return candidates


def keyword_candidates(text: str, limit: int = 24) -> list[str]:
    cleaned = re.sub(r"https?://\S+", "", text)
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", cleaned)
    tokens = [normalize_keyword_token(token) for token in raw_tokens]
    stop = {
        "这个",
        "一个",
        "我们",
        "他们",
        "因为",
        "所以",
        "如果",
        "但是",
        "就是",
        "可以",
        "需要",
        "时候",
        "进行",
        "第一",
        "第二",
        "第三",
        "第四",
        "首先",
        "其次",
        "最后",
        "大家好",
        "欢迎",
        "课程",
        "同学",
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
    }
    counts = Counter(
        token
        for token in tokens
        if token.lower() not in stop and not is_weak_keyword(token) and not is_bad_topic_name(token)
    )
    keywords: list[str] = []
    seen: set[str] = set()
    for word, _ in counts.most_common(limit * 2):
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(word)
        if len(keywords) >= limit:
            break
    return keywords


def segment_information_score(segment: dict[str, Any]) -> float:
    text = clean_learning_text(segment.get("text", ""))
    if not text:
        return -10.0
    lowered = text.lower()
    score = min(len(text), 420) / 80
    score += sum(2.2 for cue in INFORMATION_CUES if cue.lower() in lowered)
    if any(re.search(pattern, lowered, re.I) for pattern in LOW_VALUE_SEGMENT_PATTERNS):
        score -= 8
    if len(text) < 12:
        score -= 3
    return score


def informative_segments(segments: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    ranked = sorted(
        enumerate(segments),
        key=lambda item: (segment_information_score(item[1]), -item[0]),
        reverse=True,
    )
    rows = [row for _, row in ranked]
    return rows[:limit] if limit is not None else rows


def topic_match_terms(topic: str) -> list[str]:
    mapped = {
        "错题笔记合并": ["错题笔记", "错题解析"],
        "Agent 讲解复盘": ["Agent 讲解", "Agent 复盘", "导入 Agent"],
        "出题链路": ["出题链路", "出题流程", "考试知识库", "材料、研究、题目、答案"],
        "题目依据绑定": ["每道题必须绑定", "材料依据", "标准答案", "常见错误答案"],
        "题目条件一致性": ["题目条件", "题目语言", "根据材料", "提供材料片段"],
        "考卷命名规则": ["考卷命名", "考卷名称", "命名规则"],
        "视觉风格统一": ["视觉风格", "设计风格", "风格统一"],
        "语言风格": ["语言风格", "AI 味", "大白话"],
        "学习闭环看板": ["看板", "学习闭环", "下一步建议"],
        "Loop Engineering 优化机制": ["Loop Engineering", "循环优化", "目标 → 计划"],
    }
    terms = mapped.get(topic, [])
    return [topic, *terms]


def text_contains_topic(text: str, topic: str) -> bool:
    lowered = text.lower()
    return any(term and term.lower() in lowered for term in topic_match_terms(topic))


def select_evidence_segments(
    topic: str,
    segments: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    matching = [row for row in segments if text_contains_topic(row.get("text", ""), topic)]
    pool = matching or informative_segments(segments)
    ranked = sorted(pool, key=segment_information_score, reverse=True)
    return ranked[:limit] or segments[:limit]


def diagnostic_focus(text: str, topic: str = "", max_chars: int = 72) -> str:
    clauses = [part.strip() for part in re.split(r"[。！？!?；;\n]+", clean_learning_text(text)) if part.strip()]
    if not clauses:
        return compact_excerpt(text, max_chars)
    if topic:
        match = next((clause for clause in clauses if text_contains_topic(clause, topic)), "")
        if match:
            return compact_excerpt(match, max_chars)
    best = max(clauses, key=lambda clause: segment_information_score({"text": clause}))
    return compact_excerpt(best, max_chars)


def make_source_topic(index: int, keyword: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = select_evidence_segments(keyword, segments)
    focus = diagnostic_focus(evidence[0].get("text", ""), keyword) if evidence else keyword
    return {
        "id": f"kp-{index:02d}",
        "name": keyword,
        "origin": "source",
        "evidence_segment_ids": [row["segment_id"] for row in evidence],
        "evidence_excerpt": compact_excerpt(evidence[0].get("text", "")) if evidence else "",
        "diagnostic_focus": focus,
        "mechanism_probe": f"为什么材料中的「{focus}」成立？",
        "boundary_probe": f"「{keyword}」在哪些条件下会失效或误导？",
        "misconception_trap": f"把「{keyword}」只当作关键词背下来，却说不出机制、边界和反例。",
        "transfer_probe": f"把「{keyword}」换到一个新任务时，先确认条件再落地。",
    }


def rank_keywords_by_evidence(keywords: list[str], segments: list[dict[str, Any]]) -> list[str]:
    def rank(keyword: str) -> tuple[float, int]:
        matching = [row for row in segments if text_contains_topic(row.get("text", ""), keyword)]
        best_score = max((segment_information_score(row) for row in matching), default=-99.0)
        mentions = sum(row.get("text", "").lower().count(keyword.lower()) for row in matching)
        return (best_score, mentions)

    return sorted(keywords, key=rank, reverse=True)


def merge_topic_candidates(primary: list[str], fallback: list[str], limit: int = 24) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for keyword in primary + fallback:
        normalized = normalize_keyword_token(keyword, max_chars=18).strip()
        key = normalized.lower()
        if is_bad_topic_name(normalized) or key in seen:
            continue
        if any(
            min(len(normalized), len(existing)) >= 4
            and abs(len(normalized) - len(existing)) <= 4
            and (normalized.startswith(existing) or existing.startswith(normalized))
            for existing in merged
        ):
            continue
        seen.add(key)
        merged.append(normalized)
        if len(merged) >= limit:
            break
    return merged


def build_material_report(run_id: str, source: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    all_text = "\n".join(row["text"] for row in segments)
    structural_keywords = structural_topic_candidates(all_text)
    ranked_keywords = rank_keywords_by_evidence(keyword_candidates(all_text), segments)
    keywords = merge_topic_candidates(structural_keywords, ranked_keywords)
    source_topics: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for keyword in keywords:
        topic = make_source_topic(len(source_topics) + 1, keyword, segments)
        name_key = topic["name"].lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        source_topics.append(topic)
        if len(source_topics) >= 16:
            break
    extension_topics = [
        {
            "id": f"ext-{index:02d}",
            "name": f"{keyword} 的边界与迁移场景",
            "origin": "extension_research_needed",
            "source_focus": source_topics[index - 1].get("diagnostic_focus", keyword) if index <= len(source_topics) else keyword,
            "research_instruction": "由 agent 只围绕核心概念做 3-5 个可靠来源的延伸研究，必须标注为延伸。",
        }
        for index, keyword in enumerate(keywords[:3], 1)
    ]
    return {
        "run_id": run_id,
        "source": source,
        "created_at": iso_now(),
        "summary": "自动提取的材料理解草案。agent 应在生成正式题目前补充或修正知识点。",
        "stats": {
            "segment_count": len(segments),
            "source_chars": len(all_text),
            "keyword_count": len(keywords),
            "source_topic_count": len(source_topics),
        },
        "keywords": keywords,
        "knowledge_map": {
            "source_topics": source_topics,
            "extension_topics": extension_topics,
        },
        "easy_to_fake_understanding": [
            "能复述名词但解释不出机制",
            "套用原案例可以，换业务场景不会",
            "忽略边界条件，把方法当成万能答案",
        ],
    }


def source_refs_for_topic(topic: dict[str, Any], segments_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for segment_id in topic.get("evidence_segment_ids", [])[:3]:
        segment = segments_by_id.get(segment_id)
        if not segment:
            continue
        ref: dict[str, Any] = {"segment_id": segment_id}
        locator = segment.get("locator") or {}
        if locator:
            ref["locator"] = locator
        excerpt = compact_excerpt(segment.get("text", ""), 140)
        if excerpt:
            ref["excerpt"] = excerpt
        refs.append(ref)
    if not refs and topic.get("evidence_excerpt"):
        refs.append({"excerpt": topic["evidence_excerpt"]})
    return refs


def build_deep_research_from_report(
    report: dict[str, Any],
    segments: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    segments_by_id = {row.get("segment_id"): row for row in segments if row.get("segment_id")}
    source_topics = report.get("knowledge_map", {}).get("source_topics", [])[:5]
    source_links = sources or report.get("topic_research", {}).get("sources", []) or []
    mode = "extended" if source_links else "source_only"
    items: list[dict[str, Any]] = []
    for topic in source_topics:
        name = topic.get("name") or "核心概念"
        items.append(
            {
                "topic_id": topic.get("id"),
                "topic": name,
                "origin": "source",
                "mechanism": topic.get("mechanism_probe") or f"说明「{name}」为什么成立。",
                "boundary": topic.get("boundary_probe") or f"说明「{name}」何时不适用。",
                "misconception": topic.get("misconception_trap") or f"把「{name}」当作名词背诵而不解释条件。",
                "counterexample": f"找一个会限制或推翻「{name}」的失败案例。",
                "transfer_scenario": topic.get("transfer_probe") or f"把「{name}」迁移到一个新任务中。",
                "source_refs": source_refs_for_topic(topic, segments_by_id),
            }
        )
    if mode == "extended":
        first_ref = source_refs_for_topic(source_topics[0], segments_by_id) if source_topics else []
        for index, source_link in enumerate(source_links[:3], 1):
            title = source_link.get("title") or f"延伸来源 {index}"
            url = source_link.get("url") or source_link.get("href") or ""
            name = f"{title} 的延伸边界"
            refs = [{"title": title, "url": url, "why_used": source_link.get("why_used", "")}]
            if first_ref:
                refs.append(first_ref[0])
            items.append(
                {
                    "topic_id": f"ext-{index:02d}",
                    "topic": name,
                    "origin": "extension",
                    "mechanism": f"结合外部来源说明「{title}」补充了什么机制或背景。",
                    "boundary": "说明这条延伸信息不能替代原材料，只能用于补边界和迁移。",
                    "misconception": "把外部资料当成原文结论，或者把单一来源当成通用规律。",
                    "counterexample": "当外部来源和原材料场景不同，直接套用会失真。",
                    "transfer_scenario": "用外部来源补充真实应用、风险或上下游知识，再回到材料核对。",
                    "source_refs": refs,
                }
            )
    return {
        "version": "1.0",
        "created_at": iso_now(),
        "research": {
            "status": "completed",
            "mandatory": True,
            "mode": mode,
            "items": items,
            "notes": "由已完成的主题研究笔记和来源清单整理；plan-exam 会再次校验字段和来源。",
        },
    }


RESEARCH_ITEM_REQUIRED_FIELDS = [
    "mechanism",
    "boundary",
    "misconception",
    "counterexample",
    "transfer_scenario",
]


def research_text_is_substantive(value: Any) -> bool:
    return isinstance(value, str) and len(clean_learning_text(value)) >= 6


def source_ref_has_source(ref: dict[str, Any], origin: str) -> bool:
    if not isinstance(ref, dict):
        return False
    if origin == "extension":
        return bool(ref.get("url") or ref.get("href") or ref.get("source_url"))
    if ref.get("segment_id") or ref.get("page") or ref.get("timestamp") or ref.get("url"):
        return True
    locator = ref.get("locator") if isinstance(ref.get("locator"), dict) else {}
    return bool(locator.get("page") or locator.get("timestamp") or locator.get("url") or locator.get("research_note"))


def normalize_deep_research_payload(payload: dict[str, Any]) -> dict[str, Any]:
    research = payload.get("research") if isinstance(payload.get("research"), dict) else payload
    if not isinstance(research, dict):
        raise KaodaError("deep_research.json must contain a research object.")
    normalized = dict(research)
    normalized["mandatory"] = True
    normalized["items"] = list(normalized.get("items") or [])
    return normalized


def validate_deep_research(research: dict[str, Any], source_only_requested: bool = False) -> dict[str, Any]:
    issues: list[str] = []
    if research.get("status") != "completed":
        issues.append("research.status must be completed")
    mode = research.get("mode")
    if mode not in {"extended", "source_only"}:
        issues.append("research.mode must be extended or source_only")
    if source_only_requested and mode != "source_only":
        issues.append("--source-only requires research.mode source_only")
    items = research.get("items") or []
    if not items:
        issues.append("research.items cannot be empty")
    origin_counts: Counter[str] = Counter()
    for index, item in enumerate(items, 1):
        origin = item.get("origin")
        origin_counts[origin] += 1
        if origin not in {"source", "source_inferred", "extension"}:
            issues.append(f"items[{index}].origin must be source, source_inferred, or extension")
        if mode == "source_only" and origin == "extension":
            issues.append(f"items[{index}] cannot use origin extension in source_only mode")
        for field in RESEARCH_ITEM_REQUIRED_FIELDS:
            if not research_text_is_substantive(item.get(field)):
                issues.append(f"items[{index}].{field} is missing or too thin")
        source_refs = item.get("source_refs")
        if not isinstance(source_refs, list) or not source_refs:
            issues.append(f"items[{index}].source_refs must be a non-empty list")
        elif not any(source_ref_has_source(ref, origin or "") for ref in source_refs):
            issues.append(f"items[{index}].source_refs lacks usable source evidence")
    if mode == "extended" and origin_counts.get("extension", 0) < 1:
        issues.append("extended research requires at least one origin=extension item; use mode source_only if external research was unavailable")
    if issues:
        raise KaodaError("deep_research.json is incomplete: " + "; ".join(issues))
    return research


def load_deep_research(run_dir: Path, source_only_requested: bool = False) -> dict[str, Any]:
    path = run_dir / "deep_research.json"
    if not path.exists():
        raise KaodaError(
            "deep_research.json missing. Complete mandatory source analysis and core research before plan-exam."
        )
    payload = read_json(path)
    research = normalize_deep_research_payload(payload)
    research = validate_deep_research(research, source_only_requested=source_only_requested)
    research["deep_research_path"] = str(path)
    return research


def split_csv(value: str | None, defaults: list[str]) -> list[str]:
    if not value:
        return list(defaults)
    items = [item.strip() for item in re.split(r"[,，]", value) if item.strip()]
    return items or list(defaults)


def clamp_checkpoint_count(value: int) -> int:
    return max(MIN_REVIEW_CHECKPOINTS, min(int(value), MAX_REVIEW_CHECKPOINTS))


def recommend_checkpoint_count(
    report: dict[str, Any],
    segments: list[dict[str, Any]],
    requested: int | None = None,
) -> int:
    if requested:
        return clamp_checkpoint_count(requested)
    stats = report.get("stats", {})
    source_chars = int(stats.get("source_chars") or sum(len(row.get("text", "")) for row in segments))
    segment_count = int(stats.get("segment_count") or len(segments))
    keyword_count = int(stats.get("keyword_count") or len(report.get("keywords", [])))
    if source_chars >= 50000 or segment_count >= 80:
        return 50
    if source_chars >= 25000 or segment_count >= 45:
        return 40
    if source_chars >= 9000 or segment_count >= 18 or (source_chars >= 4000 and keyword_count >= 22):
        return 30
    return DEFAULT_REVIEW_CHECKPOINTS


def normalize_review_mode(value: str | None) -> str:
    if not value:
        return "正常模式"
    normalized = value.split("·", 1)[0].strip()
    return normalized if normalized in REVIEW_MODES else "正常模式"


def normalize_question_style(value: str | None) -> str:
    if not value:
        return "混合风格"
    normalized = QUESTION_STYLE_ALIASES.get(value, value)
    return normalized if normalized in QUESTION_STYLE_OPTIONS else "混合风格"


def style_ids_for_option(question_style: str) -> list[str]:
    ids = STYLE_FAMILY_BY_OPTION.get(question_style, [])
    if ids:
        return ids
    return [style["id"] for style in QUESTION_STYLE_FRAMES]


def has_mistake_bank(learner_id: str | None) -> bool:
    if not learner_id:
        return False
    bank_path = data_dir() / "learners" / learner_id / "mistake_bank.jsonl"
    return any(row.get("review_status", "active") == "active" for row in read_jsonl(bank_path))


def summarize_mistake_bank(learner_id: str | None, limit: int = 8) -> list[dict[str, Any]]:
    if not learner_id:
        return []
    bank_path = data_dir() / "learners" / learner_id / "mistake_bank.jsonl"
    active = [row for row in read_jsonl(bank_path) if row.get("review_status", "active") == "active"]
    active.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return active[:limit]


def write_review_choices(run_dir: Path, report: dict[str, Any], learner_id: str | None = None) -> None:
    keywords = "、".join(report.get("keywords", [])[:6]) or "材料核心概念"
    mistake_section = ""
    if has_mistake_bank(learner_id):
        mistake_section = """
## 错题知识

检测到该 learner 有历史错题。研究完成后再问用户是否混入错题知识：

- 只复盘当前材料
- 加入历史错题
- 重点拷最近错题
- 当前材料为主，错题为辅
"""
    content = f"""# 研究完成后的复盘选择

agent 已经完成内容分析和核心研究后，只需要让用户做轻量选择；不要再询问研究许可。

## 复盘模式

- 复盘模式 · 5分钟
- 正常模式 · 10分钟
- 拷打模式 · 30分钟
- 深度拷打 · 45分钟

## 题目风格

- 正经复盘
- 趣味拷打
- 毒舌拷打
- 面试官追问
- 老板追问
- 朋友吐槽
- 反例猎人
- 概念诈骗识别
- 弹幕判断
- 混合风格
{mistake_section}
本次材料自动识别的候选核心概念：{keywords}
"""
    (run_dir / "review_choices.md").write_text(content, encoding="utf-8")


def write_research_prompt(run_dir: Path, report: dict[str, Any]) -> None:
    source_topics = report.get("knowledge_map", {}).get("source_topics", [])[:5]
    topic_lines = "\n".join(
        f"- {topic.get('id')}: {topic.get('name')}｜拷问点：{topic.get('diagnostic_focus', '')}"
        for topic in source_topics
    )
    content = f"""# 核心研究与知识地图深化任务

在询问用户复盘模式之前，agent 必须完成这个任务。核心研究不是可选项，不要询问研究许可。

## 输入

- `segments.jsonl`
- `material_report.json`

## 核心概念候选

{topic_lines}

## 输出要求

把调研和深化结果写入同目录 `deep_research.json`，然后再运行 `plan-exam`。格式：

```json
{{
  "version": "1.0",
  "research": {{
    "status": "completed",
    "mandatory": true,
    "mode": "extended",
    "items": [
      {{
        "topic_id": "kp-01",
        "topic": "核心概念",
        "origin": "source",
        "mechanism": "为什么成立",
        "boundary": "什么时候不成立",
        "misconception": "常见错误理解",
        "counterexample": "反例或失败信号",
        "transfer_scenario": "换场景如何用",
        "source_refs": [
          {{"segment_id": "seg-xxxx", "locator": {{"page": 1}}, "excerpt": "原文证据"}}
        ]
      }}
    ]
  }}
}}
```

- `research.status` 必须是 `completed`。
- `research.mode` 必须是 `extended` 或 `source_only`。
- `research.items` 建议 3-8 个。
- 每个 item 必须有 `mechanism`、`boundary`、`misconception`、`counterexample`、`transfer_scenario`、`source_refs`。
- 每个 item 必须标注 `origin`: `source`, `extension`, 或 `source_inferred`。
- 延伸研究必须至少有一个带 URL 的 `source_refs`。
- 原文内研究必须说明推理来自哪个原文片段、页码、时间戳或文章 URL。
- 不允许把延伸内容伪装成原文内容。

## 研究目标

机制、边界、常见误解、反例、迁移只是保底项。agent 还要根据内容主动发散，补充必要的背景、上下游知识、现实应用、争议、失败案例、替代观点、工具链、指标、风险、历史脉络或领域常识。

如果用户明确要求“只按原文”，设置 `research.mode` 为 `source_only`，只做原文内研究，不引入外部来源；但研究步骤仍然必须完成。

研究完成并写入 `deep_research.json` 后，再让用户根据 `review_choices.md` 选择复盘模式、题目风格和是否加入错题知识。
"""
    (run_dir / "research_prompt.md").write_text(content, encoding="utf-8")


def plan_exam(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, source, segments, report = load_run(args.run_id)
    write_review_choices(run_dir, report, args.learner_id)
    write_research_prompt(run_dir, report)
    deep_research = load_deep_research(run_dir, source_only_requested=args.source_only)
    question_profile = split_csv(args.question_types, DEFAULT_QUESTION_PROFILE)
    review_mode = normalize_review_mode(args.review_mode)
    mode_config = REVIEW_MODES[review_mode]
    question_style = normalize_question_style(args.question_style or args.style)
    duration_minutes = args.duration_minutes or int(mode_config["duration_minutes"])
    if args.checkpoint_count:
        checkpoint_count = recommend_checkpoint_count(report, segments, args.checkpoint_count)
    elif review_mode == "复盘模式":
        checkpoint_count = int(mode_config["checkpoint_count"])
    else:
        checkpoint_count = max(recommend_checkpoint_count(report, segments), int(mode_config["checkpoint_count"]))
    mistake_policy = args.mistake_knowledge_policy
    mistakes = summarize_mistake_bank(args.learner_id)
    if not mistakes:
        mistake_policy = "只复盘当前材料"
    research_mode = deep_research["mode"]
    research_items = deep_research["items"]
    brief = {
        "version": "1.0",
        "run_id": args.run_id,
        "created_at": iso_now(),
        "learner_goal": args.learner_goal,
        "review_mode": review_mode,
        "review_mode_label": mode_config["label"],
        "duration_minutes": duration_minutes,
        "question_style": question_style,
        "exam_style": question_style,
        "difficulty": args.difficulty,
        "question_profile": question_profile,
        "checkpoint_count": checkpoint_count,
        "question_mix_target": question_mix_target(review_mode),
        "review_selection": {
            "status": "confirmed",
            "selected_after_research": True,
            "review_mode": review_mode,
            "duration_minutes": duration_minutes,
            "question_style": question_style,
            "notes": args.selection_notes,
        },
        "research": {
            "status": "completed",
            "mode": research_mode,
            "mandatory": True,
            "items": research_items,
            "notes": deep_research.get("notes") or args.research_notes,
            "source_only": research_mode == "source_only",
            "deep_research_path": deep_research.get("deep_research_path"),
            "scope": "核心研究强制完成；机制、边界、误解、反例、迁移只是保底，实际研究方向按内容发散。",
        },
        "mistake_knowledge": {
            "learner_id": args.learner_id,
            "available": bool(mistakes),
            "policy": mistake_policy,
            "items": mistakes if mistake_policy != "只复盘当前材料" else [],
        },
        "deepened_knowledge_map": {
            "source_topics": report.get("knowledge_map", {}).get("source_topics", []),
            "extension_topics": report.get("knowledge_map", {}).get("extension_topics", []),
            "fake_understanding_risks": report.get("easy_to_fake_understanding", []),
        },
        "generation_contract": {
            "must_research_before_selection": True,
            "must_select_mode_after_research": True,
            "must_research_before_build": True,
            "must_include_question_types": question_profile,
            "must_not_generate_summary_only": True,
            "loop_engineering": {
                "goal": "先明确本轮要发现的理解问题，而不是只复述材料。",
                "plan": "每道题绑定知识点、材料依据、题型、答案和错因方向。",
                "do": "按计划生成复盘单、标准答案、解析、成绩单和 Agent 报告包。",
                "check": "检查题目是否有依据、题干条件是否一致、成绩单是否简洁、错题包是否可复盘。",
                "act": "发现脱节、AI 味、标题泛化或错题说明混乱时，回到对应环节修正。",
            },
        },
    }
    write_json(run_dir / "exam_brief.json", brief)
    print_path(
        run_dir / "exam_brief.json",
        {
            "run_id": args.run_id,
            "research_status": "completed",
            "research_mode": research_mode,
            "review_mode": review_mode,
            "question_style": question_style,
            "checkpoint_count": checkpoint_count,
        },
    )
    return brief


def load_exam_brief(run_dir: Path, allow_draft: bool = False) -> dict[str, Any]:
    brief_path = run_dir / "exam_brief.json"
    if not brief_path.exists():
        if allow_draft:
            return {
                "review_mode": "正常模式",
                "review_mode_label": REVIEW_MODES["正常模式"]["label"],
                "duration_minutes": 10,
                "question_style": "混合风格",
                "exam_style": "混合风格",
                "question_profile": DEFAULT_QUESTION_PROFILE,
                "research": {"status": "draft", "mode": "extended", "items": []},
                "review_selection": {"status": "draft"},
                "generation_contract": {"draft": True},
            }
        raise KaodaError(
            "exam_brief.json missing. Run `python scripts/kaoda.py plan-exam <run_id>` after core research and lightweight mode/style selection."
        )
    brief = read_json(brief_path)
    missing = []
    if not brief.get("review_mode"):
        missing.append("review_mode")
    if not brief.get("question_style"):
        missing.append("question_style")
    if brief.get("research", {}).get("status") not in {"completed", "draft"}:
        missing.append("research.status completed")
    if brief.get("research", {}).get("mode") not in {"extended", "source_only", "draft"}:
        missing.append("research.mode extended|source_only")
    if missing:
        raise KaodaError(f"exam_brief.json is incomplete: {', '.join(missing)}")
    return brief


def load_run(run_id: str) -> tuple[Path, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    run_dir = data_dir() / "runs" / run_id
    if not run_dir.exists():
        raise KaodaError(f"Run not found: {run_id}")
    source = read_json(run_dir / "source.json")
    segments = read_jsonl(run_dir / "segments.jsonl")
    report = read_json(run_dir / "material_report.json")
    return run_dir, source, segments, report


def compact_excerpt(text: str, max_chars: int = 180) -> str:
    text = clean_learning_text(text)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def make_rubric(max_score: int = 4) -> dict[str, Any]:
    return {
        "scale": "0-4",
        "max_score": max_score,
        "levels": [
            {"level": 0, "meaning": "答非所问或核心概念错误"},
            {"level": 1, "meaning": "只复述材料，缺少解释"},
            {"level": 2, "meaning": "能解释原文，但缺少边界或条件"},
            {"level": 3, "meaning": "能迁移到新场景，并说明关键取舍"},
            {"level": 4, "meaning": "能识别反例、风险、限制和错误理解"},
        ],
        "required_output": ["level", "evidence", "deduction_reason", "mistake_tag", "improvement"],
    }


def build_exam(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, source, segments, report = load_run(args.run_id)
    brief = load_exam_brief(run_dir, allow_draft=args.draft)
    mode = args.mode or brief.get("question_style") or "混合风格"
    exam = make_exam_from_segments(args.run_id, source, segments, report, mode=mode, exam_kind="daily", brief=brief)
    write_exam_outputs(run_dir, exam)
    print_path(run_dir / "exam.html", {"exam_id": exam["exam_id"], "questions": len(exam["questions"])})
    return exam


def make_exam_from_segments(
    run_id: str,
    source: dict[str, Any],
    segments: list[dict[str, Any]],
    report: dict[str, Any],
    mode: str = "有趣拷打模式",
    exam_kind: str = "daily",
    brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    exam_id = f"{exam_kind}-{run_id}-{stable_slug(mode, 4)}"
    source_topics = enrich_topics_with_brief(report.get("knowledge_map", {}).get("source_topics", []), brief)
    source_topics = apply_mistake_knowledge_policy(source_topics, brief)
    title = build_exam_title(source, source_topics, review_mode=normalize_review_mode((brief or {}).get("review_mode")), exam_kind=exam_kind)
    questions: list[dict[str, Any]] = []
    usable_segments = informative_segments(segments, limit=max(7, min(len(segments), 14)))
    if not usable_segments:
        raise KaodaError("No segments available to build an exam.")
    segment_by_id = {row["segment_id"]: row for row in segments}
    profile = list((brief or {}).get("question_profile") or DEFAULT_QUESTION_PROFILE)
    for required in ["边界识别", "迁移应用", "错误理解识别"]:
        if required not in profile:
            profile.append(required)
    review_mode = normalize_review_mode((brief or {}).get("review_mode"))
    question_style = normalize_question_style((brief or {}).get("question_style") or mode)
    checkpoint_count = int((brief or {}).get("checkpoint_count") or REVIEW_MODES[review_mode]["checkpoint_count"])
    allow_extension = has_extension_research(brief)
    blueprint = make_review_blueprint(
        profile,
        checkpoint_count,
        allow_extension=allow_extension,
        review_mode=review_mode,
        question_style=question_style,
    )
    for index, item in enumerate(blueprint, 1):
        kp = source_topics[(index - 1) % len(source_topics)] if source_topics else {"id": "kp-00", "name": "核心概念"}
        segment = pick_topic_segment(kp, usable_segments[(index - 1) % len(usable_segments)], segment_by_id)
        extension = item.get("source_layer") == "extension"
        questions.append(
            make_question(
                index,
                item["ability"],
                segment,
                kp,
                mode,
                extension=extension,
                question_type=item["question_type"],
                answer_mode=item.get("answer_mode", ""),
                style_family=item.get("style_family", ""),
                source_layer=item.get("source_layer", "source"),
            )
        )

    return {
        "version": "1.0",
        "exam_id": exam_id,
        "exam_kind": exam_kind,
        "run_id": run_id,
        "title": title,
        "mode": mode,
        "review_mode": review_mode,
        "duration_minutes": (brief or {}).get("duration_minutes") or REVIEW_MODES[review_mode]["duration_minutes"],
        "question_style": question_style,
        "created_at": iso_now(),
        "material_source": {
            "input": source.get("input"),
            "input_type": source.get("input_type"),
            "title": source.get("title"),
            "author": source.get("author"),
            "published_time": source.get("published_time"),
        },
        "knowledge_map": report.get("knowledge_map", {}),
        "exam_brief": brief or {},
        "review_design": {
            "positioning": "low-stakes review checklist, not a formal exam",
            "review_mode": review_mode,
            "question_style": question_style,
            "checkpoint_count": len(questions),
            "mix": summarize_question_mix(questions),
            "target_mix": question_mix_target(review_mode),
            "requires_agent_review": any(question.get("type") == "open" for question in questions),
            "score_page_role": "成绩单只展示分数、题型表现、薄弱点和下一步，不展开长篇错题解析。",
            "agent_report_role": "导出的报告包负责承载错题集、学习档案和 Agent 复盘材料。",
        },
        "scoring": {
            "objective": "front-end exact/normalized match for fill_blank, single_choice, multiple_choice, true_false",
            "open": "agent rubric scoring with evidence before score",
        },
        "question_sections": build_question_sections(questions),
        "questions": questions,
        "quality_notes": [
            "原文题必须带 source.segment_id。",
            "延伸题必须 extension=true。",
            "题面不得暴露来源层、风格名、题型名或风格提示语。",
            "只有拷打/深度拷打模式默认包含开放题，开放题必须使用 rubric 分档评分。",
        ],
    }


def has_extension_research(brief: dict[str, Any] | None) -> bool:
    if not brief or brief.get("research", {}).get("status") != "completed":
        return False
    return any(item.get("origin") == "extension" for item in brief.get("research", {}).get("items", []))


def question_mix_target(review_mode: str) -> dict[str, float]:
    mode = normalize_review_mode(review_mode)
    if mode == "复盘模式":
        return {"single_choice": 0.6, "true_false": 0.25, "multiple_choice": 0.15, "fill_blank": 0.0, "open": 0.0}
    if mode == "正常模式":
        return {"single_choice": 0.5, "true_false": 0.2, "multiple_choice": 0.2, "fill_blank": 0.1, "open": 0.0}
    if mode == "拷打模式":
        return {"single_choice": 0.5, "true_false": 0.13, "multiple_choice": 0.13, "fill_blank": 0.1, "open": 0.14}
    return {"single_choice": 0.2, "true_false": 0.1, "multiple_choice": 0.1, "fill_blank": 0.0, "open": 0.6}


def count_from_ratio(count: int, ratio: float, minimum: int = 0) -> int:
    if ratio <= 0:
        return 0
    return max(minimum, round(count * ratio))


def allocate_question_type_counts(count: int, review_mode: str = "正常模式") -> dict[str, int]:
    count = clamp_checkpoint_count(count)
    target = question_mix_target(review_mode)
    open_count = count_from_ratio(count, target["open"])
    fill_count = count_from_ratio(count, target["fill_blank"])
    multiple_count = count_from_ratio(count, target["multiple_choice"], 1 if target["multiple_choice"] else 0)
    true_false_count = count_from_ratio(count, target["true_false"], 1 if target["true_false"] else 0)
    single_count = count - open_count - fill_count - multiple_count - true_false_count
    if single_count < 1:
        open_count = max(0, open_count + single_count - 1)
        single_count = 1
    return {
        "single_choice": single_count,
        "multiple_choice": multiple_count,
        "true_false": true_false_count,
        "fill_blank": fill_count,
        "open": open_count,
    }


def make_question_type_pattern(count: int, review_mode: str = "正常模式") -> list[str]:
    counts = allocate_question_type_counts(count, review_mode)
    pattern: list[str] = []
    for question_type in ["single_choice", "multiple_choice", "true_false", "fill_blank"]:
        pattern.extend([question_type] * counts[question_type])
    mode = normalize_review_mode(review_mode)
    if mode == "深度拷打":
        open_modes = ["open_oral" if index % 3 == 2 else "open_short" for index in range(counts["open"])]
    elif counts["open"]:
        open_modes = ["open_short"] * max(0, counts["open"] - 1) + ["open_oral"]
    else:
        open_modes = []
    pattern.extend(open_modes)
    return pattern[:count]


def source_layer_for_index(index: int, allow_extension: bool) -> str:
    cycle = ["source", "variant", "source", "source", "variant", "extension", "source", "variant", "source", "extension"]
    layer = cycle[(index - 1) % len(cycle)]
    if layer == "extension" and not allow_extension:
        return "variant"
    return layer


def make_review_blueprint(
    profile: list[str],
    checkpoint_count: int,
    allow_extension: bool = False,
    review_mode: str = "正常模式",
    question_style: str = "混合风格",
) -> list[dict[str, str]]:
    count = clamp_checkpoint_count(checkpoint_count)
    type_pattern = make_question_type_pattern(count, review_mode)
    style_ids = style_ids_for_option(question_style)
    blueprint: list[dict[str, str]] = []
    for index, question_type in enumerate(type_pattern[:count]):
        ability = profile[index % len(profile)] if profile else DEFAULT_QUESTION_PROFILE[index % len(DEFAULT_QUESTION_PROFILE)]
        style = style_frame(style_ids[index % len(style_ids)])
        item = {
            "question_type": question_type,
            "ability": ability,
            "style_family": style["id"],
            "source_layer": source_layer_for_index(index + 1, allow_extension),
        }
        if question_type == "open_short":
            item["question_type"] = "open"
            item["answer_mode"] = "short"
        elif question_type == "open_oral":
            item["question_type"] = "open"
            item["answer_mode"] = "oral"
        blueprint.append(item)
    return blueprint


def summarize_question_mix(questions: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for question in questions:
        key = question.get("type", "unknown")
        if key == "open" and question.get("answer_mode"):
            key = f"open_{question.get('answer_mode')}"
        counts[key] += 1
    return dict(counts)


def build_question_sections(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for question_type in QUESTION_SECTION_ORDER:
        ids = [question["id"] for question in questions if question.get("type") == question_type]
        if ids:
            sections.append({"type": question_type, "label": QUESTION_TYPE_LABELS[question_type], "question_ids": ids})
    return sections


def visible_question_texts(question: dict[str, Any]) -> list[tuple[str, str]]:
    texts = [
        ("prompt", str(question.get("prompt") or "")),
        ("answer_hint", str(question.get("answer_hint") or "")),
        ("explanation", str(question.get("explanation") or "")),
        ("reference_answer", str(question.get("reference_answer") or "")),
    ]
    for option in question.get("options") or []:
        texts.append((f"option {option.get('id', '?')}", str(option.get("text") or "")))
    return [(label, text) for label, text in texts if text]


def build_exam_title(
    source: dict[str, Any],
    source_topics: list[dict[str, Any]],
    review_mode: str = "正常模式",
    exam_kind: str = "daily",
) -> str:
    topic = infer_title_topic(source, source_topics)
    if exam_kind == "weekly":
        return "《本周学习内容综合测验》"
    if exam_kind == "variant_review":
        return f"《{topic}：薄弱点变种复习卷》"
    if source.get("input_type") == "topic_research":
        return f"《{topic}：核心概念理解测试》"
    if review_mode in {"拷打模式", "深度拷打"}:
        return f"《{topic}：从基础到应用测验》"
    return f"《{topic}：核心概念理解测试》"


def infer_title_topic(source: dict[str, Any], source_topics: list[dict[str, Any]]) -> str:
    candidates = [
        source.get("title"),
        source.get("topic"),
        source.get("input") if source.get("input_type") != "article_url" else "",
    ]
    for candidate in candidates:
        cleaned = clean_title_topic(candidate)
        if cleaned:
            return cleaned
    topic_names = [clean_title_topic(topic.get("name")) for topic in source_topics if isinstance(topic, dict)]
    topic_names = [name for name in topic_names if name]
    if topic_names:
        return " 与 ".join(topic_names[:2])[:24]
    return "本次学习内容"


def clean_title_topic(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.match(r"https?://", text):
        return ""
    text = urllib.parse.unquote(text)
    text = re.sub(r"[?].*$", "", text)
    text = re.split(r"[/\\]", text)[-1]
    text = re.sub(r"[.](txt|md|markdown|pdf|srt|vtt|mp3|mp4|mov|m4a|wav)$", "", text, flags=re.I)
    text = re.sub(r"^(主题研究|拷打式复盘单|拷打复盘|复盘单)[:：\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -_｜|")
    if not text or text.lower() in {
        "untitled",
        "index",
        "pasted-text",
        "pasted text",
        "manual_input",
        "manual-transcript",
        "manual_transcript",
    }:
        return ""
    return text[:28]


def enrich_topics_with_brief(source_topics: list[dict[str, Any]], brief: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not brief:
        return [dict(topic) for topic in source_topics]
    research_items = brief.get("research", {}).get("items", [])
    by_id = {item.get("topic_id"): item for item in research_items if item.get("topic_id")}
    by_name = {item.get("topic"): item for item in research_items if item.get("topic")}
    enriched = []
    for topic in source_topics:
        item = by_id.get(topic.get("id")) or by_name.get(topic.get("name")) or {}
        merged = dict(topic)
        for key in ["mechanism", "boundary", "misconception", "transfer_scenario", "counterexample"]:
            if item.get(key):
                merged[key] = item[key]
        enriched.append(merged)
    return enriched


def mistake_as_topic(index: int, mistake: dict[str, Any]) -> dict[str, Any]:
    kp = mistake.get("knowledge_point") or {}
    name = kp.get("name") or "历史错题知识"
    tag = mistake.get("mistake_tag") or "unknown"
    return {
        "id": f"mistake-kp-{index:02d}",
        "name": name,
        "origin": "mistake_bank",
        "diagnostic_focus": f"历史错因 `{tag}`：需要换场景重新检查「{name}」。",
        "mechanism": f"重新说明「{name}」为什么成立，不要复用旧答案。",
        "boundary": "这次必须补出旧答案缺失的边界、失败信号或条件。",
        "misconception": f"旧错因是 {tag}，容易再次用熟悉说法糊弄过去。",
        "transfer_scenario": "把旧错题知识混入当前材料场景，检查是否还会犯同类错。",
        "evidence_segment_ids": [],
    }


def apply_mistake_knowledge_policy(
    source_topics: list[dict[str, Any]],
    brief: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not brief:
        return source_topics
    mistake_payload = brief.get("mistake_knowledge") or {}
    policy = mistake_payload.get("policy") or "只复盘当前材料"
    mistakes = mistake_payload.get("items") or []
    if policy == "只复盘当前材料" or not mistakes:
        return source_topics
    mistake_topics = [mistake_as_topic(index, mistake) for index, mistake in enumerate(mistakes[:8], 1)]
    if policy == "重点拷最近错题":
        return mistake_topics + source_topics
    if policy == "当前材料为主，错题为辅":
        merged: list[dict[str, Any]] = []
        for index, topic in enumerate(source_topics, 1):
            merged.append(topic)
            if index % 3 == 0 and mistake_topics:
                merged.append(mistake_topics.pop(0))
        return merged + mistake_topics
    return source_topics + mistake_topics


def pick_topic_segment(
    knowledge_point: dict[str, Any],
    fallback: dict[str, Any],
    segment_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    for segment_id in knowledge_point.get("evidence_segment_ids", []):
        if segment_id in segment_by_id:
            return segment_by_id[segment_id]
    return fallback


def style_frame(style_family: str) -> dict[str, str]:
    return next((style for style in QUESTION_STYLE_FRAMES if style["id"] == style_family), QUESTION_STYLE_FRAMES[0])


def mask_topic_name(text: str, topic_name: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return "材料围绕这个概念说明了它的作用、条件和边界。"
    if topic_name:
        cleaned = re.sub(re.escape(topic_name), "这个概念", cleaned, flags=re.IGNORECASE)
    return cleaned


def visible_condition_safe_text(text: str) -> str:
    cleaned = str(text or "")
    replacements = [
        ("根据材料选择", "依据可见条件选择"),
        ("根据材料", "依据可见条件"),
        ("符合材料", "符合题目条件"),
        ("材料中的", "可见内容中的"),
        ("材料里的", "可见内容里的"),
        ("材料里", "可见内容里"),
        ("材料对", "内容对"),
        ("是否真的提供了材料", "是否真的给出对应内容"),
        ("提供了材料", "给出对应内容"),
    ]
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)
    return cleaned


def plain_focus(text: str, topic_name: str) -> str:
    cleaned = mask_topic_name(text, topic_name)
    return visible_condition_safe_text(cleaned.rstrip("。；;，,")[:120])


def trim_sentence(text: str, limit: int = 110) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip("，。；;、 ") + "…"


def fill_blank_description(focus: str, topic_name: str) -> str:
    masked = plain_focus(focus, topic_name)
    rough = re.sub(r"(这个概念|这个做法|这件事|第[一二三四五六七八九十]+[，,、]?)", "", masked).strip(" ，,。；;、")
    if len(rough) < 8:
        return visible_condition_safe_text(trim_sentence(focus, 140))
    return masked


def single_choice_prompt(topic_name: str, index: int) -> str:
    patterns = [
        f"关于「{topic_name}」，哪一项说法更准确？",
        f"理解「{topic_name}」时，哪一项最不能省略？",
        f"把「{topic_name}」用到新场景前，应该先确认什么？",
        f"哪一项更接近本次复盘对「{topic_name}」的要求？",
    ]
    return patterns[(index - 1) % len(patterns)]


def multiple_choice_prompt(topic_name: str, index: int) -> str:
    patterns = [
        f"关于「{topic_name}」，哪些说法有问题？",
        f"学习「{topic_name}」时，下面哪些理解不成立？",
        f"把「{topic_name}」用到实际场景时，哪些做法有风险？",
    ]
    return patterns[(index - 1) % len(patterns)]


def distribute_choice_options(
    options: list[dict[str, str]],
    answer: list[str],
    index: int,
    correct_slots: list[list[str]] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    option_by_old_id = {option["id"]: option["text"] for option in options}
    correct_old_ids = list(answer)
    wrong_old_ids = [option["id"] for option in options if option["id"] not in correct_old_ids]
    new_ids = [chr(ord("A") + i) for i in range(len(options))]
    if correct_slots:
        target_correct = correct_slots[(index - 1) % len(correct_slots)]
    else:
        target_correct = [[slot] for slot in new_ids][(index - 1) % len(new_ids)]
    target_correct = [slot for slot in target_correct if slot in new_ids][: len(correct_old_ids)]
    if len(target_correct) < len(correct_old_ids):
        target_correct.extend([slot for slot in new_ids if slot not in target_correct][: len(correct_old_ids) - len(target_correct)])
    old_by_new: dict[str, str] = {}
    for slot, old_id in zip(target_correct, correct_old_ids):
        old_by_new[slot] = old_id
    for slot in new_ids:
        if slot not in old_by_new and wrong_old_ids:
            old_by_new[slot] = wrong_old_ids.pop(0)
    distributed = [{"id": slot, "text": option_by_old_id[old_by_new[slot]]} for slot in new_ids]
    return distributed, sorted(target_correct)


def make_question(
    index: int,
    ability: str,
    segment: dict[str, Any],
    knowledge_point: dict[str, Any],
    mode: str,
    extension: bool,
    question_type: str | None = None,
    answer_mode: str = "",
    style_family: str = "",
    source_layer: str = "source",
) -> dict[str, Any]:
    excerpt = compact_excerpt(segment["text"])
    kp_name = knowledge_point.get("name", "核心概念")
    frame = style_frame(style_family)
    frame_label = frame["label"]
    focus = knowledge_point.get("diagnostic_focus") or diagnostic_focus(segment.get("text", ""), kp_name)
    focus_plain = plain_focus(focus, kp_name)
    mechanism = knowledge_point.get("mechanism") or knowledge_point.get("mechanism_probe") or f"解释「{kp_name}」为什么成立。"
    boundary = knowledge_point.get("boundary") or knowledge_point.get("boundary_probe") or f"说明「{kp_name}」何时不适用。"
    misconception = (
        knowledge_point.get("misconception")
        or knowledge_point.get("misconception_trap")
        or f"只会复述「{kp_name}」这个词，却说不出机制和边界。"
    )
    transfer = knowledge_point.get("transfer_scenario") or knowledge_point.get("transfer_probe") or "换一个真实任务重新应用。"
    boundary_visible = visible_condition_safe_text(trim_sentence(boundary))
    misconception_visible = visible_condition_safe_text(trim_sentence(misconception, 140))
    base = {
        "id": f"q{index:02d}",
        "ability": ability,
        "knowledge_point": {
            "id": knowledge_point.get("id", "kp-00"),
            "name": kp_name,
            "diagnostic_focus": focus,
        },
        "difficulty": "medium" if index < 10 else "hard",
        "extension": extension,
        "source_layer": source_layer,
        "style_family": frame["id"],
        "style_label": frame_label,
        "source": {
            "segment_id": segment["segment_id"],
            "locator": segment.get("locator", {}),
            "excerpt": excerpt,
        },
        "mistake_tags": MISTAKE_TAGS,
    }
    resolved_type = question_type
    if not resolved_type:
        if ability == "错误理解识别":
            resolved_type = "multiple_choice"
        elif ability in {"为什么追问", "迁移应用", "落地追问"}:
            resolved_type = "open"
        else:
            resolved_type = "single_choice"
    if resolved_type == "fill_blank":
        description = fill_blank_description(focus, kp_name)
        return {
            **base,
            "type": "fill_blank",
            "prompt": f"这条描述对应的关键词或短语是什么？\n描述：{description}\n答案：____。",
            "answer": [kp_name],
            "accepted_answers": [kp_name, focus],
            "answer_hint": "填本次复盘的核心概念，不需要写长句。",
            "explanation": f"这题检查你能不能把描述和核心概念对应起来：{kp_name}。",
        }
    if resolved_type == "single_choice":
        options, answer = distribute_choice_options(
            [
                {"id": "A", "text": f"先说明「{focus_plain}」，再判断适用条件和边界。"},
                {"id": "B", "text": f"只要见过「{kp_name}」这个词，就说明已经掌握了。"},
                {"id": "C", "text": f"把这个做法直接搬到所有新场景，不检查条件：{boundary_visible}"},
                {"id": "D", "text": "遇到反例或失败信号时先忽略，避免影响原结论。"},
            ],
            ["A"],
            index,
        )
        return {
            **base,
            "type": "single_choice",
            "prompt": single_choice_prompt(kp_name, index),
            "options": options,
            "answer": answer,
            "explanation": "正确理解需要同时看来源依据、适用条件和边界；只背名称或直接套用都会漏掉关键条件。",
        }
    if resolved_type == "multiple_choice":
        options, answer = distribute_choice_options(
            [
                {"id": "A", "text": f"能用关键描述说明它为什么成立：{focus_plain}。"},
                {"id": "B", "text": misconception_visible},
                {"id": "C", "text": f"如果应用失败，先检查这些条件：{boundary_visible}"},
                {"id": "D", "text": f"只要记住「{kp_name}」和一句原话，就不用解释机制。"},
            ],
            ["B", "D"],
            index,
            correct_slots=[["A", "C"], ["B", "D"], ["A", "D"], ["B", "C"]],
        )
        return {
            **base,
            "type": "multiple_choice",
            "prompt": multiple_choice_prompt(kp_name, index),
            "options": options,
            "answer": answer,
            "explanation": "错误选项的问题在于把概念当口号，或者跳过条件检查。",
        }
    if resolved_type == "true_false":
        correct_is_true = index % 2 == 0
        statement = (
            f"理解「{kp_name}」时，至少要能说出机制、边界和失败信号。"
            if correct_is_true
            else f"只要能复述「{kp_name}」这个词，就已经足够说明自己掌握了。"
        )
        return {
            **base,
            "type": "true_false",
            "prompt": f"判断对错：{statement}",
            "options": [
                {"id": "A", "text": "对"},
                {"id": "B", "text": "错"},
            ],
            "answer": ["A"] if correct_is_true else ["B"],
            "explanation": "判断这类说法时，先看它有没有说明机制、适用条件和失败情况。",
        }
    scenario = SCENARIO_POOL[index % len(SCENARIO_POOL)]
    requirement = (
        "请用 60-90 秒说清楚：怎么做、什么时候会失效、怎么验证。"
        if answer_mode == "oral"
        else "请用 1-3 句话回答：怎么做、什么时候会失效、怎么验证。"
    )
    return {
        **base,
        "type": "open",
        "answer_mode": answer_mode or "short",
        "voice_enabled": answer_mode == "oral",
        "prompt": f"在「{scenario}」中，如何使用「{kp_name}」？\n{requirement}",
        "rubric": make_rubric(),
        "reference_answer": f"优秀答案应围绕「{focus}」说明机制、适用条件、边界、反例或风险，并能落到新场景：{transfer}",
        "explanation": f"回答时要结合来源里的关键点：{trim_sentence(mechanism)} 同时说明边界：{trim_sentence(boundary)}",
    }


def write_exam_outputs(directory: Path, exam: dict[str, Any], html_name: str = "exam.html") -> None:
    write_json(directory / "exam.json", exam)
    render_exam_html(exam, directory / html_name)
    write_grading_prompt(exam, directory / "grading_prompt.md")


def render_exam_html(exam: dict[str, Any], output_path: Path) -> None:
    if not TEMPLATE_PATH.exists():
        raise KaodaError(f"HTML template missing: {TEMPLATE_PATH}")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = json.dumps(exam, ensure_ascii=False).replace("</", "<\\/")
    rendered = template.replace("__EXAM_JSON__", payload)
    ensure_dir(output_path.parent)
    output_path.write_text(rendered, encoding="utf-8")


def write_grading_prompt(exam: dict[str, Any], path: Path) -> None:
    prompt = f"""# Agent 评分任务

你是“拷打式复盘”的考官。读取同目录的 `attempt.json`，结合 `exam.json` 输出 `grade.json`。

评分硬规则：
- 客观题按 `answer` 评分；填空题允许归一化关键词匹配。
- 先找用户答案证据，再给分。
- 不要因为答案长就给高分。
- 不要把复述材料当作真正理解。
- 每道开放题必须输出 level、evidence、deduction_reason、mistake_tag、improvement。
- 开放题复核完成后，必须把对应 result 的 `score_status` 改为 `completed` 或移除该字段；不能保留 `pending_agent_review`。
- 每道错题必须输出 learn_from，说明回到哪个知识点、片段或来源复习。
- 输出总分、客观题得分、开放题得分、百分比和优先复习建议。
- 如果存在开放题，复核完成后把 `grade.json.open_review.status` 改为 `completed`；未完成复核时不要运行 record。
- mistake_tag 只能从这些值里选择：{", ".join(MISTAKE_TAGS)}。

之后运行 `python scripts/kaoda.py record grade.json`，会归档 exam、attempt、grade、source/material/deep_research 和错题。

考试：{exam.get("title")}
开放题数量：{sum(1 for q in exam.get("questions", []) if q.get("type") == "open")}
"""
    path.write_text(prompt, encoding="utf-8")


def grade(args: argparse.Namespace) -> dict[str, Any]:
    attempt_path = Path(args.attempt).expanduser().resolve()
    attempt = read_json(attempt_path)
    exam_path = Path(attempt.get("exam_path") or attempt_path.parent / "exam.json").expanduser().resolve()
    if not exam_path.exists():
        raise KaodaError("exam.json not found. Put attempt.json next to exam.json or include exam_path.")
    exam = read_json(exam_path)
    learner_id = args.learner_id or attempt.get("learner_id") or "default"
    grade_payload = grade_attempt(exam, attempt, learner_id)
    grade_payload["artifacts"] = {
        "attempt_path": str(attempt_path),
        "exam_path": str(exam_path),
    }
    output_path = attempt_path.parent / "grade.json"
    write_json(output_path, grade_payload)
    print_path(output_path, {"score": grade_payload["score"]["total"], "needs_agent_review": grade_payload["needs_agent_review"]})
    return grade_payload


def extract_markdown_json_block(markdown: str, heading: str) -> Any:
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(heading)}\s*\n+```json\s*\n(.*?)\n```"
    )
    match = pattern.search(markdown)
    if not match:
        raise KaodaError(f"Cannot find JSON block under heading: {heading}")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise KaodaError(f"Invalid JSON block under heading {heading}: {exc}") from exc


def write_agent_open_review(exam: dict[str, Any], attempt: dict[str, Any], path: Path) -> None:
    answers = answer_map(attempt)
    lines = [
        "# Agent 开放题复核任务",
        "",
        "请读取同目录 `grade.json`，只复核简答/口述题。完成后把 `open_review.status` 改为 `completed`，并补齐每道开放题的证据、扣分原因、rubric level、错因标签和改进建议。",
        "每道开放题 result 还必须把 `score_status` 改为 `completed` 或移除；不要保留本地预检的 `pending_agent_review`。",
        "",
        "复核时不要按字数给分；先找答案证据，再按 rubric 给分。",
        "",
    ]
    for question in exam.get("questions", []):
        if question.get("type") != "open":
            continue
        lines.extend(
            [
                f"## {question.get('id')} · {question.get('knowledge_point', {}).get('name', '')}",
                "",
                f"题目：{question.get('prompt', '')}",
                "",
                f"用户答案：{answers.get(question.get('id'), '')}",
                "",
                "Rubric:",
                "```json",
                json.dumps(question.get("rubric", {}), ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def grade_report(args: argparse.Namespace) -> dict[str, Any]:
    report_path = Path(args.report).expanduser().resolve()
    markdown = report_path.read_text(encoding="utf-8")
    attempt = extract_markdown_json_block(markdown, "attempt.json")
    exam = extract_markdown_json_block(markdown, "exam.json")
    out_dir = ensure_dir(Path(args.out_dir).expanduser().resolve() if args.out_dir else report_path.parent)
    attempt["exam_path"] = "exam.json"
    learner_id = args.learner_id or attempt.get("learner_id") or "default"
    write_json(out_dir / "attempt.json", attempt)
    write_json(out_dir / "exam.json", exam)
    write_grading_prompt(exam, out_dir / "grading_prompt.md")
    grade_payload = grade_attempt(exam, attempt, learner_id)
    grade_payload["artifacts"] = {
        "agent_report_path": str(report_path),
        "attempt_path": str(out_dir / "attempt.json"),
        "exam_path": str(out_dir / "exam.json"),
    }
    if grade_payload["open_review"]["status"] == "pending_agent_review":
        open_review_path = out_dir / "agent_open_review.md"
        write_agent_open_review(exam, attempt, open_review_path)
        grade_payload["open_review"]["agent_open_review_path"] = str(open_review_path)
    output_path = out_dir / "grade.json"
    write_json(output_path, grade_payload)
    print_path(
        output_path,
        {
            "score": grade_payload["score"]["total"],
            "open_review": grade_payload["open_review"]["status"],
            "next": "review open answers before record" if grade_payload["open_review"]["status"] == "pending_agent_review" else "python scripts/kaoda.py record grade.json",
        },
    )
    return grade_payload


def answer_map(attempt: dict[str, Any]) -> dict[str, Any]:
    answers = attempt.get("answers", {})
    if isinstance(answers, list):
        return {row.get("question_id") or row.get("id"): row.get("answer") for row in answers}
    return answers


def normalize_objective_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def fill_blank_correct(user_answer: Any, accepted: list[Any]) -> bool:
    normalized_user = normalize_objective_text(user_answer)
    if not normalized_user:
        return False
    for expected in accepted:
        normalized_expected = normalize_objective_text(expected)
        if normalized_expected and (normalized_user == normalized_expected or normalized_expected in normalized_user):
            return True
    return False


def grade_attempt(exam: dict[str, Any], attempt: dict[str, Any], learner_id: str) -> dict[str, Any]:
    answers = answer_map(attempt)
    question_results = []
    objective_total = 0
    objective_score = 0
    open_total = 0
    for question in exam.get("questions", []):
        qid = question["id"]
        user_answer = answers.get(qid, [] if question["type"] != "open" else "")
        if question["type"] in {"fill_blank", "single_choice", "multiple_choice", "true_false"}:
            max_score = 1
            objective_total += max_score
            if question["type"] == "fill_blank":
                correct = fill_blank_correct(user_answer, question.get("accepted_answers") or question.get("answer") or [])
            else:
                correct = sorted(user_answer if isinstance(user_answer, list) else [user_answer]) == sorted(question["answer"])
            score = 1 if correct else 0
            objective_score += score
            question_results.append(
                {
                    "question_id": qid,
                    "type": question["type"],
                    "score": score,
                    "max_score": max_score,
                    "correct": correct,
                    "user_answer": user_answer,
                    "correct_answer": question.get("accepted_answers") or question.get("answer") or [],
                    "evidence": ["填空题按归一化关键词匹配。" if question["type"] == "fill_blank" else "客观题按选项精确匹配。"],
                    "deduction_reason": "" if correct else objective_deduction_reason(question),
                    "mistake_tag": "" if correct else pick_mistake_tag(question),
                    "improvement": "" if correct else next_time_hint(question.get("knowledge_point", {}), question),
                    "learn_from": learning_target(question),
                }
            )
        else:
            max_score = int(question.get("rubric", {}).get("max_score", 4))
            open_total += max_score
            level, evidence, reason = heuristic_open_level(str(user_answer), question)
            question_results.append(
                {
                    "question_id": qid,
                    "type": "open",
                    "score": 0,
                    "max_score": max_score,
                    "score_status": "pending_agent_review",
                    "rubric_level": None,
                    "user_answer": user_answer,
                    "correct_answer": question.get("reference_answer") or question.get("answer") or "",
                    "evidence": evidence,
                    "deduction_reason": "开放题未做最终评分；本地只做预检提示，必须由 Agent 按 rubric 复核。",
                    "mistake_tag": "",
                    "improvement": "补充机制、边界、反例和真实应用步骤；不要只复述材料原话。",
                    "learn_from": learning_target(question),
                    "needs_agent_review": True,
                    "pregrade_hint": {
                        "suggested_rubric_level": level,
                        "suggested_mistake_tag": pick_mistake_tag(question, user_answer=str(user_answer), level=level),
                        "reason": reason,
                    },
                }
            )
    needs_agent_review = open_total > 0
    open_review = {
        "status": "pending_agent_review" if needs_agent_review else "not_required",
        "open_question_count": sum(1 for question in exam.get("questions", []) if question.get("type") == "open"),
        "policy": "objective questions are final; open answers are not scored locally and require agent rubric review before record"
        if needs_agent_review
        else "no open answers in this exam",
    }
    return {
        "version": "1.0",
        "graded_at": iso_now(),
        "learner_id": learner_id,
        "exam_id": exam.get("exam_id"),
        "run_id": exam.get("run_id"),
        "scoring_mode": "local objective scoring"
        if not needs_agent_review
        else "local objective scoring + open-answer precheck only; agent rubric review required",
        "needs_agent_review": needs_agent_review,
        "open_review": open_review,
        "score": {
            "objective": objective_score,
            "objective_total": objective_total,
            "objective_percent": round((objective_score / objective_total * 100) if objective_total else 0, 1),
            "open": None if needs_agent_review else 0,
            "open_total": open_total,
            "open_pending_total": open_total if needs_agent_review else 0,
            "total": objective_score,
            "max_total": objective_total,
            "percent": round((objective_score / objective_total * 100) if objective_total else 0, 1),
            "final_total": None if needs_agent_review else objective_score,
            "final_max_total": None if needs_agent_review else objective_total,
            "final_percent": None if needs_agent_review else round((objective_score / objective_total * 100) if objective_total else 0, 1),
        },
        "question_results": question_results,
        "wrong_reason_profile": summarize_wrong_reasons(question_results),
        "review_advice": make_review_advice(question_results),
    }


def learning_target(question: dict[str, Any]) -> dict[str, Any]:
    kp = question.get("knowledge_point", {})
    source = question.get("source", {})
    return {
        "knowledge_point": kp.get("name", "核心概念"),
        "source_segment_id": source.get("segment_id"),
        "source_excerpt": source.get("excerpt", ""),
        "suggested_action": "回到这个片段，补一遍机制、边界、误解和迁移场景。",
    }


def heuristic_open_level(answer: str, question: dict[str, Any]) -> tuple[int, list[str], str]:
    text = answer.strip()
    if not text:
        return 0, ["用户未作答。"], "没有可评分内容。"
    score = 1
    evidence = [f"答案长度 {len(text)} 字符。"]
    indicators = {
        "mechanism": ["因为", "机制", "原理", "导致", "why", "how"],
        "boundary": ["边界", "条件", "不适用", "除非", "限制", "风险"],
        "transfer": ["场景", "应用", "迁移", "落地", "步骤", "业务"],
        "counter": ["反例", "误解", "错误", "翻车", "失败", "例外"],
    }
    hits = 0
    for name, words in indicators.items():
        if any(word.lower() in text.lower() for word in words):
            hits += 1
            evidence.append(f"包含{name}相关表达。")
    if len(text) > 80:
        score += 1
    if hits >= 2:
        score += 1
    if hits >= 4:
        score += 1
    score = min(score, 4)
    if score <= 1:
        reason = "答案更像复述或表态，缺少机制、边界与迁移。"
    elif score == 2:
        reason = "能解释一部分，但边界或反例不足。"
    elif score == 3:
        reason = "具备迁移意识，但还可以更明确地识别风险和错误理解。"
    else:
        reason = "本地启发式判断较完整，仍建议 agent 按 rubric 复核。"
    return score, evidence, reason


def pick_mistake_tag(question: dict[str, Any], user_answer: str = "", level: int = 0) -> str:
    ability = question.get("ability")
    if ability == "为什么追问":
        return "mechanism_missing"
    if ability == "边界识别":
        return "boundary_blindness"
    if ability == "迁移应用":
        return "false_transfer"
    if ability == "反例判断":
        return "counterexample_blindness"
    if level <= 1:
        return "concept_confusion"
    if "证据" not in user_answer:
        return "evidence_missing"
    return "application_gap"


def objective_deduction_reason(question: dict[str, Any]) -> str:
    kp_name = question.get("knowledge_point", {}).get("name") or "这个知识点"
    ability = question.get("ability")
    qtype = question.get("type")
    if qtype == "fill_blank":
        return f"这题考的是能否把描述对回「{kp_name}」这个核心概念；答错说明概念定位还不稳。"
    if qtype == "multiple_choice":
        return f"这题要求识别关于「{kp_name}」的错误理解；漏选或误选通常说明机制、边界和误解风险还混在一起。"
    if qtype == "true_false":
        return f"这题要求判断「{kp_name}」相关说法是否成立；答错多半是没有先检查条件和失败信号。"
    if ability == "边界识别":
        return f"这题的关键不是背「{kp_name}」的定义，而是看它在什么条件下成立、什么时候会失效。"
    if ability == "迁移应用":
        return f"这题检查能不能把「{kp_name}」换到新场景；答错说明直接套用多于条件判断。"
    if ability == "错误理解识别":
        return f"这题要抓住关于「{kp_name}」的常见误解；答错说明容易被听起来顺的说法带跑。"
    return f"这题要求抓住「{kp_name}」的机制、条件和边界；当前答案没有命中最关键的判断点。"


def summarize_wrong_reasons(results: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in results:
        if row.get("score_status") == "pending_agent_review":
            continue
        if row.get("score", 0) < row.get("max_score", 1):
            tag = row.get("mistake_tag") or "unknown"
            counter[tag] += 1
    return dict(counter.most_common())


def make_review_advice(results: list[dict[str, Any]]) -> list[str]:
    profile = summarize_wrong_reasons(results)
    advice = []
    for tag, _ in Counter(profile).most_common(3):
        if tag == "mechanism_missing":
            advice.append("优先练习“为什么成立”：每个结论都补机制链条。")
        elif tag == "boundary_blindness":
            advice.append("优先补边界：写出方法不适用的条件。")
        elif tag == "false_transfer":
            advice.append("优先做迁移题：换业务场景，不许照搬原案例。")
        elif tag == "counterexample_blindness":
            advice.append("优先找反例：用失败案例验证自己是不是真懂。")
        elif tag:
            advice.append(f"复习错因 {tag}：重答时必须补证据和应用步骤。")
    return advice or ["本次没有明显错因，下一步提高题目难度并增加真实场景追问。"]


def record(args: argparse.Namespace) -> dict[str, Any]:
    grade_path = Path(args.grade).expanduser().resolve()
    grade_payload = read_json(grade_path)
    open_status = (grade_payload.get("open_review") or {}).get("status")
    if open_status == "pending_agent_review" or (grade_payload.get("needs_agent_review") and open_status != "completed"):
        raise KaodaError(
            "grade.json contains open answers pending Agent review. Complete rubric review and set open_review.status to completed before record."
        )
    if open_status and open_status not in {"not_required", "completed"}:
        raise KaodaError(f"Unsupported open_review.status for record: {open_status}")
    if open_status == "completed":
        pending_open = [
            result.get("question_id")
            for result in grade_payload.get("question_results", [])
            if result.get("type") == "open" and result.get("score_status") == "pending_agent_review"
        ]
        if pending_open:
            raise KaodaError(
                "open_review.status is completed, but open question results are still pending Agent review: "
                + ", ".join(str(item) for item in pending_open)
            )
    ensure_grade_score_totals_match_results(grade_payload)
    exam_path = grade_path.parent / "exam.json"
    exam = read_json(exam_path) if exam_path.exists() else {"questions": []}
    q_by_id = {q["id"]: q for q in exam.get("questions", [])}
    learner_id = args.learner_id or grade_payload.get("learner_id") or "default"
    entries: list[dict[str, Any]] = []
    for result in grade_payload.get("question_results", []):
        if result.get("score", 0) >= result.get("max_score", 1):
            continue
        question = q_by_id.get(result.get("question_id"), {})
        entries.append(make_mistake_entry(learner_id, grade_payload, result, question))
    bank_path = data_dir() / "learners" / learner_id / "mistake_bank.jsonl"
    append_jsonl(bank_path, entries)
    archive_dir = archive_grade_session(learner_id, grade_path, grade_payload, entries)
    print_path(
        bank_path,
        {
            "added": len(entries),
            "learner_id": learner_id,
            "archive_dir": str(archive_dir),
            "dashboard_hint": f"python scripts/kaoda.py dashboard {learner_id}",
        },
    )
    return {"added": len(entries), "bank_path": str(bank_path), "archive_dir": str(archive_dir)}


def ensure_grade_score_totals_match_results(grade_payload: dict[str, Any]) -> None:
    results = grade_payload.get("question_results", [])
    if not results:
        return
    expected_total = 0
    expected_max = 0
    for result in results:
        score = result.get("score", 0)
        max_score = result.get("max_score", 0)
        if not isinstance(score, (int, float)) or not isinstance(max_score, (int, float)):
            raise KaodaError("grade.json question_results contain non-numeric score/max_score.")
        expected_total += score
        expected_max += max_score
    score_payload = grade_payload.get("score") or {}
    if score_payload.get("total") != expected_total or score_payload.get("max_total") != expected_max:
        raise KaodaError(
            "grade.json score totals do not match question_results. Recalculate score.total and score.max_total before record."
        )


def archive_grade_session(
    learner_id: str,
    grade_path: Path,
    grade_payload: dict[str, Any],
    mistake_entries: list[dict[str, Any]],
) -> Path:
    exam_id = grade_payload.get("exam_id") or "exam"
    stamp = (grade_payload.get("graded_at") or iso_now()).replace(":", "").replace("-", "")
    archive_base = f"{stamp[:15]}-{stable_slug(learner_id + exam_id, 8)}"
    archive_root = data_dir() / "learners" / learner_id / "archive"
    archive_id = archive_base
    archive_dir = archive_root / archive_id
    suffix = 2
    while archive_dir.exists():
        archive_id = f"{archive_base}-{suffix}"
        archive_dir = archive_root / archive_id
        suffix += 1
    archive_dir = ensure_dir(archive_dir)
    copied: dict[str, str] = {}
    run_dir = data_dir() / "runs" / str(grade_payload.get("run_id") or "")
    candidates = {
        "grade": grade_path,
        "exam": grade_path.parent / "exam.json",
        "exam_html": grade_path.parent / "exam.html",
        "attempt": grade_path.parent / "attempt.json",
        "grading_prompt": grade_path.parent / "grading_prompt.md",
        "source": run_dir / "source.json",
        "material_report": run_dir / "material_report.json",
        "deep_research": run_dir / "deep_research.json",
    }
    for name, path in candidates.items():
        if path.exists():
            target = archive_dir / path.name
            shutil.copy2(path, target)
            copied[name] = str(target)
    write_jsonl(archive_dir / "wrong_questions.jsonl", mistake_entries)
    manifest = {
        "version": "1.0",
        "archived_at": iso_now(),
        "learner_id": learner_id,
        "exam_id": exam_id,
        "run_id": grade_payload.get("run_id"),
        "score": grade_payload.get("score", {}),
        "wrong_count": len(mistake_entries),
        "files": copied,
    }
    write_json(archive_dir / "archive_manifest.json", manifest)
    return archive_dir


def make_mistake_entry(
    learner_id: str,
    grade_payload: dict[str, Any],
    result: dict[str, Any],
    question: dict[str, Any],
) -> dict[str, Any]:
    prompt = question.get("prompt", "")
    kp = question.get("knowledge_point", {"id": "unknown", "name": "unknown"})
    question_type = question.get("type", "unknown")
    answer_text = format_answer_for_record(question, result.get("user_answer"))
    correct_text = format_answer_for_record(question, result.get("correct_answer"), correct=True)
    knowledge_explanation = question.get("explanation", "") or objective_deduction_reason(question)
    return {
        "entry_id": f"mistake-{stable_slug(learner_id + grade_payload.get('exam_id', '') + result.get('question_id', '') + iso_now(), 12)}",
        "created_at": iso_now(),
        "learner_id": learner_id,
        "run_id": grade_payload.get("run_id"),
        "exam_id": grade_payload.get("exam_id"),
        "question_id": result.get("question_id"),
        "question_title": mistake_question_title(question),
        "knowledge_point": kp,
        "ability": question.get("ability", "unknown"),
        "mistake_tag": result.get("mistake_tag") or "unknown",
        "mistake_label": MISTAKE_TAG_LABELS.get(result.get("mistake_tag") or "unknown", "未分类错因"),
        "score": result.get("score"),
        "max_score": result.get("max_score"),
        "source": question.get("source", {}),
        "original_question": prompt,
        "question_type": question_type,
        "question_type_label": QUESTION_TYPE_LABELS.get(question_type, question_type),
        "user_answer": answer_text,
        "raw_user_answer": result.get("user_answer"),
        "correct_answer": correct_text,
        "raw_correct_answer": result.get("correct_answer"),
        "error_reason": result.get("deduction_reason", ""),
        "explanation": knowledge_explanation,
        "knowledge_explanation": knowledge_explanation,
        "plain_language_explanation": plain_language_explanation(kp, result, question),
        "next_time_hint": next_time_hint(kp, question),
        "original_prompt_hash": stable_slug(prompt, 16),
        "original_scenario": extract_scenario(prompt),
        "evidence": result.get("evidence", []),
        "deduction_reason": result.get("deduction_reason", ""),
        "review_status": "active",
    }


def mistake_question_title(question: dict[str, Any]) -> str:
    kp_name = question.get("knowledge_point", {}).get("name") or "这个知识点"
    qtype = QUESTION_TYPE_LABELS.get(question.get("type"), question.get("type", "题目"))
    ability = question.get("ability") or "理解检查"
    return f"{kp_name} · {ability} · {qtype}"


def format_answer_for_record(question: dict[str, Any], answer: Any, correct: bool = False) -> str:
    if answer is None or answer == "":
        return "未作答" if not correct else ""
    qtype = question.get("type")
    if qtype == "open":
        return str(answer)
    if qtype == "fill_blank":
        values = answer if isinstance(answer, list) else [answer]
        values = [str(item) for item in values if str(item)]
        return " / ".join(values) if values else ("未作答" if not correct else "")
    values = answer if isinstance(answer, list) else [answer]
    option_by_id = {option.get("id"): option.get("text", "") for option in question.get("options") or []}
    rendered = []
    for item in values:
        text = option_by_id.get(item)
        rendered.append(f"{item}. {text}" if text else str(item))
    return "；".join(rendered) if rendered else ("未作答" if not correct else "")


def plain_language_explanation(knowledge_point: dict[str, Any], result: dict[str, Any], question: dict[str, Any] | None = None) -> str:
    name = knowledge_point.get("name") or "这个知识点"
    reason = result.get("deduction_reason") or "这题没有拿满分。"
    ability = (question or {}).get("ability", "")
    if ability == "边界识别":
        return f"这题不是在问你记不记得「{name}」，而是在问你知不知道它什么时候会失效。先把适用条件说出来，再看选项。{reason}"
    if ability == "错误理解识别":
        return f"这题容易被说得很顺的错误解释骗过去。判断「{name}」时，先找它有没有跳过机制、边界或反例。{reason}"
    if ability == "迁移应用":
        return f"这题考的是换场景后还能不能用「{name}」。不要直接搬答案，先检查新场景的条件有没有变。{reason}"
    return f"这题卡住的地方在「{name}」。先别急着背答案，先把它为什么成立、什么时候不成立说清楚。{reason}"


def next_time_hint(knowledge_point: dict[str, Any], question: dict[str, Any] | None = None) -> str:
    name = knowledge_point.get("name") or "这个知识点"
    qtype = (question or {}).get("type")
    if qtype == "multiple_choice":
        return f"下次遇到「{name}」多选题，逐项问：这句话有没有偷换概念、跳过条件、把案例当通用规律。"
    if qtype == "true_false":
        return f"下次遇到「{name}」判断题，先找绝对化表达，再问它的成立条件和失败条件。"
    if qtype == "fill_blank":
        return f"下次遇到「{name}」填空题，先把描述里的机制词和边界词圈出来，再对应核心概念。"
    return f"下次遇到「{name}」相关题，先问自己：题目要我判断的是定义、机制、边界，还是迁移场景。"


def extract_scenario(prompt: str) -> str:
    match = re.search(r"场景里回答：(.+?)[。\n]", prompt)
    return match.group(1) if match else ""


def review(args: argparse.Namespace) -> dict[str, Any]:
    learner_id = args.learner_id
    bank_path = data_dir() / "learners" / learner_id / "mistake_bank.jsonl"
    mistakes = [m for m in read_jsonl(bank_path) if m.get("review_status") == "active"]
    if not mistakes:
        raise KaodaError(f"No active mistakes for learner: {learner_id}")
    review_id = utc_now().strftime("review-%Y%m%d-%H%M%S")
    review_dir = ensure_dir(data_dir() / "learners" / learner_id / "review" / review_id)
    exam = make_variant_exam(learner_id, review_id, mistakes[: int(args.limit)], "variant_review")
    write_exam_outputs(review_dir, exam, html_name="review.html")
    print_path(review_dir / "review.html", {"questions": len(exam["questions"])})
    return exam


def make_variant_exam(
    learner_id: str,
    exam_id: str,
    mistakes: list[dict[str, Any]],
    exam_kind: str,
    weekly_mix: dict[str, int] | None = None,
) -> dict[str, Any]:
    questions = []
    last_type = ""
    same_type_count = 0
    for index, mistake in enumerate(mistakes, 1):
        qtype = "open" if same_type_count < 2 else "single_choice"
        if qtype == last_type:
            same_type_count += 1
        else:
            same_type_count = 1
            last_type = qtype
        questions.append(make_variant_question(index, mistake, qtype))
    return {
        "version": "1.0",
        "exam_id": exam_id,
        "exam_kind": exam_kind,
        "learner_id": learner_id,
        "title": build_exam_title(
            {"input_type": "mistake_bank"},
            [m.get("knowledge_point", {}) for m in mistakes],
            exam_kind="variant_review",
        ),
        "mode": "有趣拷打模式",
        "created_at": iso_now(),
        "material_source": {"input": "mistake_bank", "input_type": "local_memory"},
        "knowledge_map": {"source_topics": [m.get("knowledge_point") for m in mistakes]},
        "weekly_mix": weekly_mix,
        "variant_rules": [
            "同一知识点可以重复考",
            "同一题干不能重复",
            "同一场景不能连续重复",
            "同一题型最多连续出现 2 次",
            "同一错因必须换角度考",
            "复习题必须更接近真实应用",
        ],
        "questions": questions,
    }


def make_variant_question(index: int, mistake: dict[str, Any], qtype: str) -> dict[str, Any]:
    kp = mistake.get("knowledge_point", {"id": "unknown", "name": "核心知识"})
    tag = mistake.get("mistake_tag", "unknown")
    original_scenario = mistake.get("original_scenario", "")
    scenario = next((s for s in SCENARIO_POOL if s != original_scenario), SCENARIO_POOL[index % len(SCENARIO_POOL)])
    base = {
        "id": f"v{index:02d}",
        "type": qtype,
        "ability": "迁移应用",
        "knowledge_point": kp,
        "difficulty": "hard",
        "extension": True,
        "source": mistake.get("source", {}),
        "mistake_tags": MISTAKE_TAGS,
        "variant_of": {
            "entry_id": mistake.get("entry_id"),
            "mistake_tag": tag,
            "original_prompt_hash": mistake.get("original_prompt_hash"),
        },
    }
    if qtype == "single_choice":
        options, answer = distribute_choice_options(
            [
                {"id": "A", "text": "先说明概念成立的条件，再列出失败信号和验证步骤。"},
                {"id": "B", "text": "直接套原题答案，场景变化不重要。"},
                {"id": "C", "text": "只看自己熟悉的成功案例，不检查反例。"},
                {"id": "D", "text": "把不确定的部分说成确定结论。"},
            ],
            ["A"],
            index,
        )
        return {
            **base,
            "prompt": f"你之前在「{kp.get('name')}」这类题上出错。换到「{scenario}」时，哪种处理更合适？",
            "options": options,
            "answer": answer,
            "explanation": "这题换了场景，检查你是否能补上条件、边界和验证步骤。",
        }
    return {
        **base,
        "prompt": f"把「{kp.get('name')}」用于「{scenario}」。请写出：1. 机制；2. 边界；3. 失败信号；4. 验证方式。",
        "rubric": make_rubric(),
        "reference_answer": "必须换角度回答同一知识点，不能复用原题干或原场景。",
        "explanation": "同一知识点，换真实应用场景，观察是否还会掉进同一错因。",
    }


def weekly(args: argparse.Namespace) -> dict[str, Any]:
    learner_id = args.learner_id
    since_dt = parse_since(args.since)
    bank_path = data_dir() / "learners" / learner_id / "mistake_bank.jsonl"
    all_mistakes = read_jsonl(bank_path)
    mistakes = [m for m in all_mistakes if parse_time(m.get("created_at")) >= since_dt]
    archive_contexts = load_weekly_archive_contexts(learner_id, since_dt)
    if not mistakes and not archive_contexts:
        raise KaodaError(f"No archive or mistakes found for learner {learner_id} since {args.since}")
    week_id = utc_now().strftime("%G-W%V")
    weekly_dir = ensure_dir(data_dir() / "learners" / learner_id / "weekly" / week_id)
    selected = select_weekly_mistakes(mistakes)
    exam = make_weekly_exam(learner_id, week_id, selected, archive_contexts)
    write_json(weekly_dir / "weekly_exam.json", exam)
    render_exam_html(exam, weekly_dir / "weekly_exam.html")
    analysis = make_weekly_analysis(learner_id, week_id, mistakes, archive_contexts, exam)
    (weekly_dir / "analysis.md").write_text(analysis, encoding="utf-8")
    print_path(weekly_dir / "weekly_exam.html", {"week_id": week_id, "questions": len(exam["questions"])})
    return exam


def parse_since(value: str) -> datetime:
    match = re.fullmatch(r"(\d+)d", value.strip())
    if match:
        return utc_now() - timedelta(days=int(match.group(1)))
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KaodaError("Use --since like 7d or an ISO timestamp.") from exc


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromtimestamp(0, timezone.utc)


def select_weekly_mistakes(mistakes: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mistake in mistakes:
        grouped[mistake.get("mistake_tag", "unknown")].append(mistake)
    selected: list[dict[str, Any]] = []
    for _, rows in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
        selected.extend(rows[:3])
        if len(selected) >= limit:
            break
    return selected[:limit]


def resolve_archived_file(archive_dir: Path, manifest: dict[str, Any], key: str, fallback_name: str) -> Path | None:
    raw = (manifest.get("files") or {}).get(key)
    if raw:
        path = Path(raw)
        if path.exists():
            return path
    fallback = archive_dir / fallback_name
    return fallback if fallback.exists() else None


def load_weekly_archive_contexts(learner_id: str, since_dt: datetime) -> list[dict[str, Any]]:
    archive_root = data_dir() / "learners" / learner_id / "archive"
    contexts: list[dict[str, Any]] = []
    if not archive_root.exists():
        return contexts
    for manifest_path in sorted(archive_root.glob("*/archive_manifest.json")):
        manifest = read_json(manifest_path)
        archived_at = parse_time(manifest.get("archived_at"))
        if archived_at < since_dt:
            continue
        archive_dir = manifest_path.parent
        material_path = resolve_archived_file(archive_dir, manifest, "material_report", "material_report.json")
        deep_path = resolve_archived_file(archive_dir, manifest, "deep_research", "deep_research.json")
        exam_path = resolve_archived_file(archive_dir, manifest, "exam", "exam.json")
        source_path = resolve_archived_file(archive_dir, manifest, "source", "source.json")
        context = {
            "archive_dir": str(archive_dir),
            "manifest": manifest,
            "source": read_json(source_path) if source_path else {},
            "material_report": read_json(material_path) if material_path else {},
            "deep_research": read_json(deep_path) if deep_path else {},
            "exam": read_json(exam_path) if exam_path else {},
        }
        contexts.append(context)
    return contexts


def source_ref_to_segment(ref: dict[str, Any], fallback_text: str, run_id: str, index: int) -> dict[str, Any]:
    return {
        "segment_id": ref.get("segment_id") or f"weekly-{stable_slug(run_id, 6)}-{index:03d}",
        "source_id": run_id or "weekly-archive",
        "kind": "archive",
        "locator": ref.get("locator") if isinstance(ref.get("locator"), dict) else {"archive_run_id": run_id},
        "text": ref.get("excerpt") or fallback_text,
    }


def weekly_topic_rows(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for context in contexts:
        manifest = context.get("manifest") or {}
        run_id = manifest.get("run_id") or context.get("exam", {}).get("run_id") or ""
        report = context.get("material_report") or {}
        deep = normalize_deep_research_payload(context.get("deep_research") or {"research": {}})
        research_by_id = {item.get("topic_id"): item for item in deep.get("items", []) if item.get("topic_id")}
        research_by_name = {item.get("topic"): item for item in deep.get("items", []) if item.get("topic")}
        topics = report.get("knowledge_map", {}).get("source_topics", [])
        if not topics:
            topics = context.get("exam", {}).get("knowledge_map", {}).get("source_topics", [])
        for topic in topics[:6]:
            name = topic.get("name") or "核心知识"
            key = f"{run_id}:{name}"
            if key in seen:
                continue
            seen.add(key)
            item = research_by_id.get(topic.get("id")) or research_by_name.get(name) or {}
            merged = dict(topic)
            for field in RESEARCH_ITEM_REQUIRED_FIELDS:
                if item.get(field):
                    merged[field] = item[field]
            refs = item.get("source_refs") or []
            segment = source_ref_to_segment(
                refs[0] if refs else {},
                topic.get("evidence_excerpt") or topic.get("diagnostic_focus") or name,
                run_id,
                len(rows) + 1,
            )
            rows.append({"topic": merged, "segment": segment, "run_id": run_id, "source_title": context.get("source", {}).get("title") or run_id})
    return rows


def make_weekly_topic_question(index: int, row: dict[str, Any], qtype: str, source_layer: str) -> dict[str, Any]:
    question = make_question(
        index,
        "迁移应用" if source_layer == "transfer" else "边界识别",
        row["segment"],
        row["topic"],
        "混合风格",
        extension=source_layer != "material_core",
        question_type=qtype,
        style_family="transfer_scene" if source_layer == "transfer" else "serious_review",
        source_layer=source_layer,
    )
    question["id"] = f"w{index:02d}"
    question["weekly_source"] = source_layer
    question["archive_run_id"] = row.get("run_id")
    if source_layer == "transfer":
        question["prompt"] = f"把「{row['topic'].get('name', '核心知识')}」换到另一个本周材料场景时，哪一项处理更合适？"
    return question


def make_weekly_exam(
    learner_id: str,
    week_id: str,
    mistakes: list[dict[str, Any]],
    archive_contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    target_count = 20 if len(archive_contexts) >= 3 else max(15, min(20, len(mistakes) + 8))
    weak_target = min(len(mistakes), max(1, round(target_count * 0.6))) if mistakes else 0
    core_target = max(0, round(target_count * 0.25))
    transfer_target = max(0, target_count - weak_target - core_target)
    topic_rows = weekly_topic_rows(archive_contexts)
    questions: list[dict[str, Any]] = []

    for mistake in mistakes[:weak_target]:
        index = len(questions) + 1
        question = make_variant_question(index, mistake, "single_choice")
        question["id"] = f"w{index:02d}"
        question["weekly_source"] = "mistake_variant"
        questions.append(question)

    for row in topic_rows[:core_target]:
        index = len(questions) + 1
        qtype = "multiple_choice" if index % 3 == 0 else "single_choice"
        questions.append(make_weekly_topic_question(index, row, qtype, "material_core"))

    transfer_pool = topic_rows[core_target:] or topic_rows
    for row in transfer_pool[:transfer_target]:
        index = len(questions) + 1
        qtype = "true_false" if index % 2 == 0 else "single_choice"
        questions.append(make_weekly_topic_question(index, row, qtype, "transfer"))

    if not questions and mistakes:
        for mistake in mistakes[:target_count]:
            index = len(questions) + 1
            question = make_variant_question(index, mistake, "single_choice")
            question["id"] = f"w{index:02d}"
            question["weekly_source"] = "mistake_variant"
            questions.append(question)

    if not questions:
        raise KaodaError("Not enough archive topics or mistake entries to build a weekly review.")

    weekly_research_items: list[dict[str, Any]] = []
    for context in archive_contexts:
        deep = normalize_deep_research_payload(context.get("deep_research") or {"research": {}})
        weekly_research_items.extend(deep.get("items", [])[:4])
        if len(weekly_research_items) >= 12:
            break

    brief = {
        "version": "1.0",
        "run_id": f"weekly-{week_id}",
        "created_at": iso_now(),
        "learner_goal": "本周综合拷问：错题弱点、材料核心知识和跨材料迁移",
        "review_mode": "正常模式",
        "review_mode_label": REVIEW_MODES["正常模式"]["label"],
        "duration_minutes": 10,
        "question_style": "混合风格",
        "exam_style": "混合风格",
        "question_profile": DEFAULT_QUESTION_PROFILE,
        "checkpoint_count": len(questions),
        "question_mix_target": question_mix_target("正常模式"),
        "review_selection": {"status": "confirmed", "selected_after_research": True},
        "research": {
            "status": "completed",
            "mandatory": True,
            "mode": "source_only" if len(archive_contexts) < 3 else "extended",
            "items": weekly_research_items,
            "notes": "weekly exam synthesized from archived material reports, deep research, and mistake bank.",
        },
        "weekly_mix": {
            "weak_variants": 60,
            "core_knowledge": 25,
            "transfer_challenge": 15,
            "actual_counts": Counter(q.get("weekly_source", "unknown") for q in questions),
            "archive_count": len(archive_contexts),
            "downgraded": len(archive_contexts) < 3,
        },
    }
    return {
        "version": "1.0",
        "exam_id": f"weekly-{week_id}-{stable_slug(learner_id, 6)}",
        "exam_kind": "weekly",
        "learner_id": learner_id,
        "run_id": f"weekly-{week_id}",
        "title": build_exam_title({"input_type": "local_memory"}, [], exam_kind="weekly"),
        "mode": "混合风格",
        "review_mode": "正常模式",
        "duration_minutes": 10,
        "question_style": "混合风格",
        "created_at": iso_now(),
        "material_source": {"input": "archive+mistake_bank", "input_type": "local_memory"},
        "knowledge_map": {"source_topics": [row["topic"] for row in topic_rows]},
        "exam_brief": brief,
        "review_design": {
            "positioning": "weekly synthesis review",
            "review_mode": "正常模式",
            "question_style": "混合风格",
            "checkpoint_count": len(questions),
            "mix": summarize_question_mix(questions),
            "weekly_mix": brief["weekly_mix"],
            "requires_agent_review": any(question.get("type") == "open" for question in questions),
        },
        "question_sections": build_question_sections(questions),
        "variant_rules": [
            "同一知识点可以重复考",
            "同一题干不能重复",
            "同一场景不能连续重复",
            "同一错因必须换角度考",
            "复习题必须更接近真实应用",
        ],
        "questions": questions,
    }


def make_weekly_analysis(
    learner_id: str,
    week_id: str,
    mistakes: list[dict[str, Any]],
    archive_contexts: list[dict[str, Any]],
    exam: dict[str, Any],
) -> str:
    tag_counts = Counter(m.get("mistake_tag", "unknown") for m in mistakes)
    kp_counts = Counter(m.get("knowledge_point", {}).get("name", "unknown") for m in mistakes)
    top_fake = tag_counts.most_common(3)
    source_titles = [
        context.get("source", {}).get("title")
        or context.get("source", {}).get("input")
        or context.get("manifest", {}).get("run_id")
        or "未命名材料"
        for context in archive_contexts
    ]
    weekly_sources = Counter(q.get("weekly_source", "unknown") for q in exam.get("questions", []))
    lines = [
        f"# 本周综合拷问分析：{week_id}",
        "",
        f"- learner_id: `{learner_id}`",
        f"- mistakes: {len(mistakes)}",
        f"- archives: {len(archive_contexts)}",
        f"- weekly_mix: {dict(weekly_sources)}",
        "",
        "## 本周最容易误判的 3 个地方",
    ]
    for tag, count in top_fake:
        lines.append(f"- `{tag}`：出现 {count} 次")
    lines.extend(["", "## 高频薄弱知识点"])
    for kp, count in kp_counts.most_common(8):
        lines.append(f"- {kp}：{count} 次")
    lines.extend(["", "## 跨材料共同模式"])
    if len(archive_contexts) >= 3:
        lines.append("- 本次周考同时使用历史错题、材料核心知识点和跨材料迁移题。")
    else:
        lines.append("- archive 不足 3 个，本次降级为错题变种周复习，避免假装做了跨材料综合。")
    for title in source_titles[:6]:
        lines.append(f"- 材料：{title}")
    lines.extend(["", "## 本次周考题目来源"])
    for source, count in weekly_sources.items():
        label = {
            "mistake_variant": "历史错题弱点变种",
            "material_core": "本周材料核心知识点重组",
            "transfer": "跨材料迁移/综合应用题",
        }.get(source, source)
        lines.append(f"- {label}：{count} 题")
    lines.extend(
        [
            "",
            "## 下周复习建议",
            "- 每个薄弱知识点至少做 1 道变种题。",
            "- 回答开放题时固定写机制、边界、反例、验证步骤。",
            "- 不重复旧题，优先用真实工作或学习场景重新作答。",
        ]
    )
    return "\n".join(lines) + "\n"


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return read_json(path)


def dashboard_link(path: Path, dashboard_dir: Path) -> str:
    return os.path.relpath(path, start=dashboard_dir).replace(os.sep, "/")


def html_text(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def result_is_correct(result: dict[str, Any]) -> bool:
    return result.get("score", 0) >= result.get("max_score", 1)


def archive_session_summary(manifest_path: Path, dashboard_dir: Path) -> dict[str, Any]:
    archive_dir = manifest_path.parent
    manifest = read_json(manifest_path)
    grade = read_json_if_exists(archive_dir / "grade.json") or {}
    exam = read_json_if_exists(archive_dir / "exam.json") or {}
    attempt = read_json_if_exists(archive_dir / "attempt.json") or {}
    results = grade.get("question_results", [])
    answered = len(results)
    correct = sum(1 for row in results if result_is_correct(row))
    wrong = answered - correct
    score = grade.get("score") or manifest.get("score") or {}
    topics = []
    for topic in (exam.get("knowledge_map") or {}).get("source_topics", []):
        if isinstance(topic, dict) and topic.get("name"):
            topics.append(str(topic["name"]))
    links = {}
    for key, filename in [
        ("exam_html", "exam.html"),
        ("exam_json", "exam.json"),
        ("attempt_json", "attempt.json"),
        ("grade_json", "grade.json"),
        ("wrong_questions", "wrong_questions.jsonl"),
    ]:
        path = archive_dir / filename
        if path.exists():
            links[key] = dashboard_link(path, dashboard_dir)
    return {
        "archive_id": archive_dir.name,
        "archived_at": manifest.get("archived_at") or grade.get("graded_at") or exam.get("created_at") or "",
        "exam_id": manifest.get("exam_id") or grade.get("exam_id") or exam.get("exam_id") or archive_dir.name,
        "run_id": manifest.get("run_id") or grade.get("run_id") or exam.get("run_id"),
        "title": exam.get("title") or manifest.get("exam_id") or "未命名复盘",
        "review_mode": exam.get("review_mode") or exam.get("exam_kind") or "",
        "question_count": len(exam.get("questions", [])),
        "answered": answered,
        "correct": correct,
        "wrong": wrong,
        "accuracy": round((correct / answered * 100) if answered else 0, 1),
        "score_percent": score.get("percent", round((correct / answered * 100) if answered else 0, 1)),
        "topics": topics,
        "links": links,
        "has_attempt": bool(attempt),
    }


def load_learner_archive_sessions(learner_id: str, dashboard_dir: Path) -> list[dict[str, Any]]:
    archive_root = data_dir() / "learners" / learner_id / "archive"
    sessions = [
        archive_session_summary(path, dashboard_dir)
        for path in sorted(archive_root.glob("*/archive_manifest.json"))
    ]
    return sorted(sessions, key=lambda row: row.get("archived_at", ""), reverse=True)


def generated_review_summary(review_dir: Path, dashboard_dir: Path) -> dict[str, Any]:
    exam = read_json_if_exists(review_dir / "exam.json") or {}
    links = {}
    for key, filename in [("review_html", "review.html"), ("exam_json", "exam.json"), ("grading_prompt", "grading_prompt.md")]:
        path = review_dir / filename
        if path.exists():
            links[key] = dashboard_link(path, dashboard_dir)
    return {
        "id": review_dir.name,
        "created_at": exam.get("created_at") or review_dir.name,
        "title": exam.get("title") or "薄弱点变种复习卷",
        "question_count": len(exam.get("questions", [])),
        "review_mode": exam.get("review_mode") or exam.get("exam_kind") or "variant_review",
        "links": links,
    }


def load_generated_reviews(learner_id: str, dashboard_dir: Path) -> list[dict[str, Any]]:
    review_root = data_dir() / "learners" / learner_id / "review"
    if not review_root.exists():
        return []
    reviews = [
        generated_review_summary(path, dashboard_dir)
        for path in sorted(review_root.iterdir())
        if path.is_dir()
    ]
    return sorted(reviews, key=lambda row: row.get("created_at", ""), reverse=True)


def weekly_session_summary(weekly_dir: Path, dashboard_dir: Path) -> dict[str, Any]:
    exam = read_json_if_exists(weekly_dir / "weekly_exam.json") or {}
    links = {}
    for key, filename in [("weekly_html", "weekly_exam.html"), ("weekly_json", "weekly_exam.json"), ("analysis", "analysis.md")]:
        path = weekly_dir / filename
        if path.exists():
            links[key] = dashboard_link(path, dashboard_dir)
    mix = (exam.get("exam_brief") or {}).get("weekly_mix") or {}
    return {
        "id": weekly_dir.name,
        "created_at": exam.get("created_at") or weekly_dir.name,
        "title": exam.get("title") or "本周学习内容综合测验",
        "question_count": len(exam.get("questions", [])),
        "archive_count": mix.get("archive_count", 0),
        "downgraded": bool(mix.get("downgraded")),
        "links": links,
    }


def load_weekly_sessions(learner_id: str, dashboard_dir: Path) -> list[dict[str, Any]]:
    weekly_root = data_dir() / "learners" / learner_id / "weekly"
    if not weekly_root.exists():
        return []
    weeks = [
        weekly_session_summary(path, dashboard_dir)
        for path in sorted(weekly_root.iterdir())
        if path.is_dir()
    ]
    return sorted(weeks, key=lambda row: row.get("created_at", ""), reverse=True)


def load_learner_mistakes(learner_id: str) -> list[dict[str, Any]]:
    bank_path = data_dir() / "learners" / learner_id / "mistake_bank.jsonl"
    return read_jsonl(bank_path)


def build_note_clusters(mistakes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for mistake in mistakes:
        kp = (mistake.get("knowledge_point") or {}).get("name") or "未命名知识点"
        tag = mistake.get("mistake_tag") or "unknown"
        grouped[(kp, tag)].append(mistake)
    clusters = []
    for (kp, tag), rows in grouped.items():
        active_count = sum(1 for row in rows if row.get("review_status", "active") == "active")
        example = rows[0]
        reason = example.get("deduction_reason") or "这类题没有拿满分，需要回到机制、边界和证据重新核对。"
        evidence = example.get("evidence") or []
        clusters.append(
            {
                "knowledge_point": kp,
                "mistake_tag": tag,
                "mistake_label": MISTAKE_TAG_LABELS.get(tag, tag),
                "count": len(rows),
                "active_count": active_count,
                "reason": reason,
                "evidence": evidence,
                "entries": rows,
                "note": (
                    f"我这里容易在「{kp}」上出错，主要是{MISTAKE_TAG_LABELS.get(tag, tag)}。"
                    "下次不要先套答案，要先说清楚它成立的条件、边界和能验证的证据。"
                ),
            }
        )
    return sorted(clusters, key=lambda row: (row["active_count"], row["count"]), reverse=True)


def build_learner_dashboard(learner_id: str) -> dict[str, Any]:
    learner_dir = ensure_dir(data_dir() / "learners" / learner_id)
    dashboard_dir = ensure_dir(learner_dir / "dashboard")
    sessions = load_learner_archive_sessions(learner_id, dashboard_dir)
    generated_reviews = load_generated_reviews(learner_id, dashboard_dir)
    weekly_sessions = load_weekly_sessions(learner_id, dashboard_dir)
    mistakes = load_learner_mistakes(learner_id)
    active_mistakes = [row for row in mistakes if row.get("review_status", "active") == "active"]
    answered = sum(row["answered"] for row in sessions)
    correct = sum(row["correct"] for row in sessions)
    wrong = sum(row["wrong"] for row in sessions)
    topic_counts = Counter()
    for session in sessions:
        topic_counts.update(session["topics"])
    weak_counts = Counter((row.get("knowledge_point") or {}).get("name") or "未命名知识点" for row in active_mistakes)
    tag_counts = Counter(row.get("mistake_tag") or "unknown" for row in active_mistakes)
    return {
        "learner_id": learner_id,
        "learner_dir": learner_dir,
        "dashboard_dir": dashboard_dir,
        "generated_at": iso_now(),
        "sessions": sessions,
        "generated_reviews": generated_reviews,
        "weekly_sessions": weekly_sessions,
        "mistakes": mistakes,
        "active_mistakes": active_mistakes,
        "note_clusters": build_note_clusters(mistakes),
        "stats": {
            "completed_reviews": len(sessions),
            "answered": answered,
            "correct": correct,
            "wrong": wrong,
            "accuracy": round((correct / answered * 100) if answered else 0, 1),
            "active_mistakes": len(active_mistakes),
            "learned_topics": len(topic_counts),
            "generated_reviews": len(generated_reviews),
            "weekly_reviews": len(weekly_sessions),
        },
        "top_topics": topic_counts.most_common(12),
        "top_weak_points": weak_counts.most_common(10),
        "mistake_tag_counts": tag_counts.most_common(),
    }


DASHBOARD_CSS = """
:root {
  --bg: #f5f3ea;
  --ink: #1f2933;
  --muted: #64707d;
  --panel: #fffefa;
  --line: #242424;
  --accent: #123c7c;
  --accent-2: #c43b2f;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.6;
}
a { color: var(--accent); }
.shell { max-width: 1120px; margin: 0 auto; padding: 24px; }
.topbar {
  border: 2px solid var(--line);
  background: var(--panel);
  padding: 18px;
  box-shadow: 6px 6px 0 #d1cec4;
}
.topbar h1 { margin: 0 0 6px; font-size: clamp(28px, 5vw, 48px); line-height: 1.1; }
.topbar p { margin: 0; color: var(--muted); }
.nav { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
.nav a {
  border: 2px solid var(--line);
  background: #e7e5dc;
  color: var(--ink);
  padding: 8px 12px;
  text-decoration: none;
  font-weight: 700;
}
.nav a.active { background: var(--accent); color: white; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }
.card, .section {
  border: 2px solid var(--line);
  background: var(--panel);
  padding: 16px;
  margin: 14px 0;
}
.card strong { display: block; font-size: 32px; line-height: 1.1; }
.card span { color: var(--muted); }
h2 { margin: 26px 0 10px; font-size: 24px; }
table { width: 100%; border-collapse: collapse; background: var(--panel); }
th, td { border: 1px solid #9ba1a6; padding: 9px; text-align: left; vertical-align: top; }
th { background: #e7e5dc; }
.pill {
  display: inline-block;
  border: 1px solid var(--line);
  padding: 2px 8px;
  margin: 2px 4px 2px 0;
  background: #f0eee5;
  font-size: 13px;
}
.empty { color: var(--muted); font-style: italic; }
.note { border-left: 6px solid var(--accent); }
code { overflow-wrap: anywhere; }
@media (max-width: 680px) {
  .shell { padding: 14px; }
  table, thead, tbody, tr, th, td { display: block; width: 100%; }
  th { display: none; }
  td { border-top: 0; }
  tr { border: 2px solid var(--line); margin: 12px 0; background: var(--panel); }
}
"""


def dashboard_layout(title: str, active: str, data: dict[str, Any], body: str) -> str:
    nav = [
        ("index.html", "总看板", "index"),
        ("exams.html", "考卷集合", "exams"),
        ("mistakes.html", "错题集", "mistakes"),
        ("notes.html", "复盘建议", "notes"),
    ]
    nav_html = "\n".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for href, label, key in nav
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_text(title)}</title>
  <style>{DASHBOARD_CSS}</style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <h1>{html_text(title)}</h1>
      <p>learner_id: <code>{html_text(data["learner_id"])}</code> · generated_at: {html_text(data["generated_at"])}</p>
    </header>
    <nav class="nav">{nav_html}</nav>
    {body}
  </main>
</body>
</html>
"""


def render_count_list(rows: list[tuple[str, int]], empty_text: str) -> str:
    if not rows:
        return f'<p class="empty">{html_text(empty_text)}</p>'
    return "<ul>" + "".join(f"<li>{html_text(name)}：{count}</li>" for name, count in rows) + "</ul>"


def render_exam_table(sessions: list[dict[str, Any]]) -> str:
    if not sessions:
        return '<p class="empty">暂无归档考卷。</p>'
    rows = []
    for session in sessions:
        link_parts = []
        labels = {
            "exam_html": "打开考卷",
            "grade_json": "grade.json",
            "attempt_json": "attempt.json",
            "exam_json": "exam.json",
            "wrong_questions": "错题",
        }
        for key, label in labels.items():
            if key in session["links"]:
                link_parts.append(f'<a href="{html_text(session["links"][key])}">{label}</a>')
        topics = "".join(f'<span class="pill">{html_text(topic)}</span>' for topic in session["topics"][:5])
        topic_cell = topics or '<span class="empty">暂无主题</span>'
        link_cell = " · ".join(link_parts) or '<span class="empty">无文件</span>'
        rows.append(
            "<tr>"
            f"<td>{html_text(session['archived_at'])}</td>"
            f"<td><strong>{html_text(session['title'])}</strong><br><code>{html_text(session['exam_id'])}</code></td>"
            f"<td>{session['correct']}/{session['answered']} · {session['accuracy']}%</td>"
            f"<td>{topic_cell}</td>"
            f"<td>{link_cell}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>时间</th><th>考卷</th><th>成绩</th><th>知识点</th><th>文件</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_review_table(reviews: list[dict[str, Any]]) -> str:
    if not reviews:
        return '<p class="empty">暂无变体复习卷。运行 review 后，这里会列出薄弱点变种复习。</p>'
    rows = []
    for review in reviews:
        link_parts = []
        labels = {
            "review_html": "打开复习卷",
            "exam_json": "exam.json",
            "grading_prompt": "grading_prompt.md",
        }
        for key, label in labels.items():
            if key in review["links"]:
                link_parts.append(f'<a href="{html_text(review["links"][key])}">{label}</a>')
        link_cell = " · ".join(link_parts) or '<span class="empty">无文件</span>'
        rows.append(
            "<tr>"
            f"<td>{html_text(review['created_at'])}</td>"
            f"<td><strong>{html_text(review['title'])}</strong><br><code>{html_text(review['id'])}</code></td>"
            f"<td>{review['question_count']} 题</td>"
            f"<td>{link_cell}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>时间</th><th>复习卷</th><th>题量</th><th>文件</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_weekly_table(weeks: list[dict[str, Any]]) -> str:
    if not weeks:
        return '<p class="empty">暂无周复盘。运行 weekly 后，这里会列出周度综合复盘。</p>'
    rows = []
    for week in weeks:
        link_parts = []
        labels = {
            "weekly_html": "打开周复盘",
            "weekly_json": "weekly_exam.json",
            "analysis": "analysis.md",
        }
        for key, label in labels.items():
            if key in week["links"]:
                link_parts.append(f'<a href="{html_text(week["links"][key])}">{label}</a>')
        link_cell = " · ".join(link_parts) or '<span class="empty">无文件</span>'
        status = "降级错题变种" if week["downgraded"] else "跨材料综合"
        rows.append(
            "<tr>"
            f"<td>{html_text(week['created_at'])}</td>"
            f"<td><strong>{html_text(week['title'])}</strong><br><code>{html_text(week['id'])}</code></td>"
            f"<td>{week['question_count']} 题<br>{html_text(status)} · archive {week['archive_count']}</td>"
            f"<td>{link_cell}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>时间</th><th>周复盘</th><th>状态</th><th>文件</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def dashboard_status_sentence(data: dict[str, Any]) -> str:
    stats = data["stats"]
    if not stats["completed_reviews"]:
        return "还没有完成归档复盘。先完成一次 exam.html，导出报告给 Agent，运行 grade-report 和 record。"
    if stats["active_mistakes"] and not stats["generated_reviews"]:
        return "已经有活跃错题，但还没有生成变体复习。建议运行 review，把薄弱点换场景再考一次。"
    if stats["generated_reviews"] and not stats["weekly_reviews"]:
        return "已经生成过变体复习，但还没有周复盘。积累几次复盘后运行 weekly，看跨材料共同弱点。"
    if stats["active_mistakes"]:
        return "复盘、错题、变体复习和周复盘链路都已形成；下一步优先处理活跃错题。"
    return "当前没有活跃错题，可以提高模式强度或加入历史错题做迁移复盘。"


def render_dashboard_index(data: dict[str, Any]) -> str:
    stats = data["stats"]
    cards = [
        ("完成复盘", stats["completed_reviews"]),
        ("答题数", stats["answered"]),
        ("答对", stats["correct"]),
        ("答错", stats["wrong"]),
        ("正确率", f"{stats['accuracy']}%"),
        ("活跃错题", stats["active_mistakes"]),
        ("变体复习", stats["generated_reviews"]),
        ("周复盘", stats["weekly_reviews"]),
    ]
    card_html = "".join(
        f'<div class="card"><strong>{html_text(value)}</strong><span>{label}</span></div>'
        for label, value in cards
    )
    recent = (
        render_exam_table(data["sessions"][:6])
        if data["sessions"]
        else '<p class="empty">还没有完成记录。完成一次复盘并运行 record 后，再生成总看板。</p>'
    )
    body = f"""
    <section class="grid">{card_html}</section>
    <h2>当前状态</h2>
    <section class="section">
      <p>{html_text(dashboard_status_sentence(data))}</p>
    </section>
    <h2>最近考卷</h2>
    {recent}
    <h2>最近变体复习</h2>
    {render_review_table(data["generated_reviews"][:3])}
    <h2>最近周复盘</h2>
    {render_weekly_table(data["weekly_sessions"][:3])}
    <h2>高频薄弱点</h2>
    <section class="section">{render_count_list(data["top_weak_points"], "目前没有活跃错题。")}</section>
    <h2>目前学了什么</h2>
    <section class="section">{render_count_list(data["top_topics"], "还没有可统计的学习主题。")}</section>
    """
    return dashboard_layout("拷打式复盘总看板", "index", data, body)


def render_dashboard_exams(data: dict[str, Any]) -> str:
    body = (
        f"<h2>正式复盘记录</h2>{render_exam_table(data['sessions'])}"
        f"<h2>变体复习记录</h2>{render_review_table(data['generated_reviews'])}"
        f"<h2>周复盘记录</h2>{render_weekly_table(data['weekly_sessions'])}"
    )
    return dashboard_layout("考卷集合", "exams", data, body)


def render_dashboard_mistakes(data: dict[str, Any]) -> str:
    mistakes = data["mistakes"]
    if not mistakes:
        body = '<h2>错题集</h2><section class="section"><p class="empty">暂无错题。完成 record 后，这里会按知识点和错因展示。</p></section>'
        return dashboard_layout("错题集", "mistakes", data, body)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mistake in mistakes:
        grouped[(mistake.get("knowledge_point") or {}).get("name") or "未命名知识点"].append(mistake)
    sections = []
    for kp, rows in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
        tag_counts = Counter(row.get("mistake_tag") or "unknown" for row in rows)
        tag_html = "".join(
            f'<span class="pill">{html_text(MISTAKE_TAG_LABELS.get(tag, tag))}：{count}</span>'
            for tag, count in tag_counts.most_common()
        )
        item_html = "".join(
            "<li>"
            f"<strong>{html_text(row.get('created_at'))}</strong> "
            f"<span class=\"pill\">{html_text(row.get('review_status', 'active'))}</span> "
            f"{html_text(row.get('ability', 'unknown'))} · "
            f"{html_text(MISTAKE_TAG_LABELS.get(row.get('mistake_tag') or 'unknown', row.get('mistake_tag') or 'unknown'))}"
            f"<br><code>{html_text(row.get('exam_id'))}/{html_text(row.get('question_id'))}</code>"
            f"<br>{html_text(row.get('deduction_reason', ''))}"
            "</li>"
            for row in rows
        )
        sections.append(f'<section class="section"><h2>{html_text(kp)}</h2>{tag_html}<ul>{item_html}</ul></section>')
    return dashboard_layout("错题集", "mistakes", data, "<h2>错题集</h2>" + "".join(sections))


def render_dashboard_notes(data: dict[str, Any]) -> str:
    clusters = data["note_clusters"]
    if not clusters:
        body = '<h2>复盘建议</h2><section class="section"><p class="empty">暂无复盘建议。错题积累后，这里会按知识点给出下一步。</p></section>'
        return dashboard_layout("复盘建议", "notes", data, body)
    sections = []
    for cluster in clusters:
        evidence = cluster["evidence"]
        evidence_text = "；".join(str(item) for item in evidence[:2]) if evidence else "暂无可展示证据"
        sections.append(
            '<section class="section note">'
            f"<h2>{html_text(cluster['knowledge_point'])}</h2>"
            f"<p>{html_text(cluster['note'])}</p>"
            f"<p><strong>出现次数：</strong>{cluster['count']} 次，活跃错题 {cluster['active_count']} 条。</p>"
            f"<p><strong>这次暴露的问题：</strong>{html_text(cluster['reason'])}</p>"
            f"<p><strong>证据：</strong>{html_text(evidence_text)}</p>"
            "</section>"
        )
    return dashboard_layout("复盘建议", "notes", data, "<h2>复盘建议</h2>" + "".join(sections))


def render_notes_agent_pack(data: dict[str, Any]) -> str:
    lines = [
        "# 错题复盘 Agent 精修包",
        "",
        "## Agent 精修说明",
        "",
        "请把这些草稿改写成像懂的人在陪我复盘：大白话、短句、能直接复习，不要写成老师讲义。",
        "不要新增没有出现在错题、证据、grade 或 source 里的事实。",
        "",
        f"- learner_id: {data['learner_id']}",
        f"- generated_at: {data['generated_at']}",
        f"- active_mistakes: {len(data['active_mistakes'])}",
        "",
    ]
    if not data["note_clusters"]:
        lines.append("暂无错题可精修。")
        return "\n".join(lines) + "\n"
    for cluster in data["note_clusters"]:
        lines.extend(
            [
                f"## {cluster['knowledge_point']} / {cluster['mistake_label']}",
                "",
                f"- count: {cluster['count']}",
                f"- active_count: {cluster['active_count']}",
                f"- deterministic_note: {cluster['note']}",
                f"- deduction_reason: {cluster['reason']}",
                f"- evidence: {json.dumps(cluster['evidence'][:3], ensure_ascii=False)}",
                "",
                "### 原始错题记录",
            ]
        )
        for entry in cluster["entries"][:6]:
            lines.extend(
                [
                    f"- entry_id: {entry.get('entry_id')}",
                    f"  - exam/question: {entry.get('exam_id')}/{entry.get('question_id')}",
                    f"  - status: {entry.get('review_status', 'active')}",
                    f"  - source: {json.dumps(entry.get('source', {}), ensure_ascii=False)}",
                ]
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def dashboard(args: argparse.Namespace) -> dict[str, Any]:
    data = build_learner_dashboard(args.learner_id)
    dashboard_dir = data["dashboard_dir"]
    pages = {
        "index.html": render_dashboard_index(data),
        "exams.html": render_dashboard_exams(data),
        "mistakes.html": render_dashboard_mistakes(data),
        "notes.html": render_dashboard_notes(data),
    }
    for filename, content in pages.items():
        (dashboard_dir / filename).write_text(content, encoding="utf-8")
    (dashboard_dir / "notes_agent_pack.md").write_text(render_notes_agent_pack(data), encoding="utf-8")
    print_path(
        dashboard_dir / "index.html",
        {
            "learner_id": args.learner_id,
            "reviews": data["stats"]["completed_reviews"],
            "active_mistakes": data["stats"]["active_mistakes"],
        },
    )
    return {"dashboard_dir": str(dashboard_dir), "stats": data["stats"]}


def validate(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target).expanduser().resolve()
    payload = read_json(target)
    issues: list[str] = []
    if "questions" in payload:
        brief = payload.get("exam_brief") or {}
        if not brief:
            issues.append("exam missing exam_brief")
        if brief.get("review_selection", {}).get("status") not in {"confirmed", "draft"}:
            issues.append("exam_brief review_selection.status missing")
        if not brief.get("review_mode"):
            issues.append("exam_brief review_mode missing")
        if not brief.get("question_style"):
            issues.append("exam_brief question_style missing")
        if brief.get("research", {}).get("status") not in {"completed", "draft"}:
            issues.append("exam_brief research.status missing")
        if brief.get("research", {}).get("mandatory") is not True and brief.get("research", {}).get("status") != "draft":
            issues.append("exam_brief research.mandatory must be true")
        for question in payload["questions"]:
            for field in ["id", "type", "prompt", "knowledge_point", "source"]:
                if field not in question:
                    issues.append(f"{question.get('id', '?')} missing {field}")
            for label, text in visible_question_texts(question):
                for pattern in BAD_VISIBLE_PROMPT_PATTERNS:
                    if pattern in text:
                        issues.append(f"{question.get('id', '?')} {label} contains banned visible pattern: {pattern}")
                if label == "prompt" or label == "answer_hint" or label.startswith("option "):
                    for pattern in BAD_VISIBLE_CONDITION_PATTERNS:
                        if pattern in text:
                            issues.append(f"{question.get('id', '?')} {label} implies missing visible material context: {pattern}")
            if question.get("type") in {"fill_blank", "single_choice", "multiple_choice", "true_false"} and "answer" not in question:
                issues.append(f"{question.get('id')} objective question missing answer")
            if question.get("type") == "open" and "rubric" not in question:
                issues.append(f"{question.get('id')} open question missing rubric")
    elif target.name == "grade.json":
        for result in payload.get("question_results", []):
            for field in ["question_id", "score", "max_score", "evidence", "mistake_tag"]:
                if field not in result:
                    issues.append(f"result missing {field}")
    else:
        issues.append("Unknown validation target; expected exam.json or grade.json")
    result = {"ok": not issues, "issues": issues}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)
    return result


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, required: bool = False) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    add("python", sys.version_info >= (3, 10), sys.version.split()[0], required=True)
    add("skill_root", (ROOT / "SKILL.md").exists(), str(ROOT), required=True)
    add("html_template", TEMPLATE_PATH.exists(), str(TEMPLATE_PATH), required=True)
    try:
        ensure_dir(data_dir())
        add("data_dir", os.access(data_dir(), os.W_OK), str(data_dir()), required=True)
    except OSError as exc:
        add("data_dir", False, str(exc), required=True)

    codex_skill = Path.home() / ".codex" / "skills" / "kaoda-review"
    if codex_skill.exists():
        try:
            active_ok = codex_skill.resolve() == ROOT
            detail = f"{codex_skill} -> {codex_skill.resolve()}"
        except OSError as exc:
            active_ok = False
            detail = str(exc)
        add("codex_active_skill", active_ok, detail, required=False)
    else:
        add("codex_active_skill", False, f"{codex_skill} not found", required=False)

    optional_tools = {
        "yt-dlp": "video subtitle extraction for YouTube/Bilibili links",
        "pdftotext": "text PDF extraction with page locators",
        "pdftoppm": "scanned PDF OCR image rendering",
        "tesseract": "scanned PDF OCR text recognition",
        "ffmpeg": "optional local audio/video conversion before transcription",
        "whisper": "optional local media transcription when installed with a model",
        "whisper-cli": "optional whisper.cpp media transcription when a local model is configured",
    }
    for command, purpose in optional_tools.items():
        path = shutil.which(command)
        add(command, bool(path), f"{purpose}; {'found at ' + path if path else 'not installed'}", required=False)

    missing_required = [row["name"] for row in checks if row["required"] and not row["ok"]]
    missing_optional = [row["name"] for row in checks if not row["required"] and not row["ok"]]
    result = {
        "ok": not missing_required,
        "root": str(ROOT),
        "data_dir": str(data_dir()),
        "checks": checks,
        "beginner_hint": (
            "You can ask: 用 kaoda-review 拷打式复盘这个视频/PDF/主题，正常模式，混合风格。"
        ),
        "optional_dependency_notes": {
            "video_links": "Install yt-dlp or provide SRT/VTT/TXT transcripts when video subtitles cannot be extracted. The CLI creates a manual transcript workspace instead of inventing content.",
            "media_files": "Audio/video uploads work best with a same-name SRT/VTT/TXT/MD transcript. Optional local Whisper/ffmpeg can be used outside the core path.",
            "pdf": "Text PDFs use pdftotext when available and a small stdlib fallback otherwise. Scanned PDFs need pdftoppm+tesseract, or the CLI creates a manual text workspace.",
        },
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if missing_required:
        raise KaodaError("Required checks failed: " + ", ".join(missing_required))
    return result


def print_path(path: Path, extra: dict[str, Any] | None = None) -> None:
    payload = {"path": str(path.resolve())}
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kaoda", description="拷打式复盘 local-first Agent Skill CLI")
    parser.add_argument("--version", action="version", version=f"kaoda {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="识别输入并生成 segments.jsonl")
    p.add_argument("input", help="YouTube/Bilibili URL, article URL, PDF, subtitle, text/audio/video file, or inline text")
    p.add_argument("--run-id", help="Optional stable run id")
    p.set_defaults(func=ingest)

    p = sub.add_parser("ingest-manual", help="把补充的正文/字幕导入已有 needs_text run")
    p.add_argument("run_id")
    p.add_argument("text_file", nargs="?", default=None, help="默认读取 run 目录下的 manual_input.txt/manual_transcript.txt")
    p.set_defaults(func=ingest_manual)

    p = sub.add_parser("research-topic", help="为只有主题、没有材料的请求创建研究工作区")
    p.add_argument("topic", help="例如 token、RAG、注意力机制")
    p.add_argument("--run-id", help="Optional stable run id")
    p.set_defaults(func=research_topic)

    p = sub.add_parser("ingest-topic", help="把 agent 完成的 topic_research.md 导入成可出题材料")
    p.add_argument("run_id")
    p.add_argument("--topic", default=None)
    p.add_argument("--notes", default=None, help="默认读取 run 目录下的 topic_research.md")
    p.add_argument("--sources", default=None, help="默认读取 run 目录下的 source_links.json")
    p.set_defaults(func=ingest_topic)

    p = sub.add_parser("plan-exam", help="记录研究完成后的复盘模式、题目风格和 exam_brief.json")
    p.add_argument("run_id")
    p.add_argument("--learner-goal", default="综合诊断：检查理解、迁移、误解识别和落地能力")
    p.add_argument("--review-mode", choices=list(REVIEW_MODES.keys()), default="正常模式")
    p.add_argument("--duration-minutes", type=int, default=None)
    p.add_argument("--question-style", choices=QUESTION_STYLE_OPTIONS, default="混合风格")
    p.add_argument("--style", default=None, help=argparse.SUPPRESS)
    p.add_argument("--difficulty", default="normal", help=argparse.SUPPRESS)
    p.add_argument("--question-types", default=",".join(DEFAULT_QUESTION_PROFILE), help=argparse.SUPPRESS)
    p.add_argument("--checkpoint-count", type=int, default=None, help="默认由复盘模式决定，显式传入时限制在 15-50")
    p.add_argument("--source-only", action="store_true", help="只做原文内研究，不引入外部延伸来源")
    p.add_argument("--learner-id", default=None)
    p.add_argument("--mistake-knowledge-policy", choices=MISTAKE_KNOWLEDGE_POLICIES, default="只复盘当前材料")
    p.add_argument("--research-notes", default="agent 已完成核心概念研究；研究方向按内容发散，机制/边界/误解/反例/迁移只是保底。")
    p.add_argument("--selection-notes", default="研究完成后，用户只需选择复盘模式、题目风格，以及有历史错题时是否加入错题知识。")
    p.add_argument("--open-ratio", type=float, default=None, help=argparse.SUPPRESS)
    p.add_argument("--research-status", choices=["completed", "blocked"], default="completed", help=argparse.SUPPRESS)
    p.add_argument("--intake-notes", default="", help=argparse.SUPPRESS)
    p.set_defaults(func=plan_exam)

    p = sub.add_parser("build-exam", help="生成 exam.json 和 HTML 考卷")
    p.add_argument("run_id")
    p.add_argument("--mode", default=None)
    p.add_argument("--draft", action="store_true", help="只用于本地烟测；正式使用必须先运行 plan-exam")
    p.set_defaults(func=build_exam)

    p = sub.add_parser("grade", help="根据 attempt.json 生成 grade.json")
    p.add_argument("attempt")
    p.add_argument("--learner-id", default=None)
    p.set_defaults(func=grade)

    p = sub.add_parser("grade-report", help="读取 kaoda_agent_report.md 并生成 attempt/exam/grade 文件")
    p.add_argument("report")
    p.add_argument("--learner-id", default=None)
    p.add_argument("--out-dir", default=None)
    p.set_defaults(func=grade_report)

    p = sub.add_parser("record", help="把 grade.json 写入本地错题库")
    p.add_argument("grade")
    p.add_argument("--learner-id", default=None)
    p.set_defaults(func=record)

    p = sub.add_parser("review", help="根据错题库生成变种复习卷")
    p.add_argument("learner_id")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=review)

    p = sub.add_parser("weekly", help="生成本周学习内容综合测验")
    p.add_argument("learner_id")
    p.add_argument("--since", default="7d")
    p.set_defaults(func=weekly)

    p = sub.add_parser("dashboard", help="生成 learner 的静态总看板")
    p.add_argument("learner_id")
    p.set_defaults(func=dashboard)

    p = sub.add_parser("validate", help="验证 exam.json 或 grade.json")
    p.add_argument("target")
    p.set_defaults(func=validate)

    p = sub.add_parser("doctor", help="检查本机运行环境、Codex skill 安装态和可选依赖")
    p.set_defaults(func=doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except KaodaError as exc:
        print(f"kaoda: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
