# 拷打式复盘 · kaoda-review

> 看完了，不代表你懂。你还要经得起拷问。

`kaoda-review` 是一个给 Claude Code、Codex、Cursor 等本地 Agent 使用的开源 Skill。它可以把视频、PDF、文章、字幕、笔记，或者一个你想学习的主题，转换成一份可在浏览器里完成的“拷打式复盘单”。

它不是总结器，也不是普通题库。它的目标是暴露四类最常见的“假懂”：

- 只会复述名词，但说不清机制
- 换个场景就不会迁移
- 分不清边界、反例和适用条件
- 看不出别人解释里的错误理解

默认推荐是 `正常模式 · 10分钟`：约 20 个低压力检查点，主要是单选、多选、判断、填空，浏览器内直接判分。更重的模式会加入少量短答或口述题，让 Agent 按 rubric 二次评分。

[安装](#安装) · [能做什么](#能做什么) · [使用流程](#使用流程) · [命令手册](#命令手册) · [开源许可](#开源许可)

---

## 30 秒开始

如果你使用支持 `skills` 安装器的环境：

```bash
npx skills add https://github.com/ziibnchen98-creator/kaoda-review --skill kaoda-review
```

也可以直接把这段话发给有 shell 权限的 AI Agent：

```text
帮我安装 kaoda-review 这个 Agent Skill。
请把 https://github.com/ziibnchen98-creator/kaoda-review 克隆到我的 skills 目录里：
- Codex: ~/.codex/skills/kaoda-review
- Claude Code: ~/.claude/skills/kaoda-review
安装完成后检查 SKILL.md、scripts/、assets/、references/ 是否存在。
以后我说“拷打式复盘这个视频 / PDF / 主题”时，请优先使用这个 skill。
```

手动安装：

```bash
# Codex
git clone https://github.com/ziibnchen98-creator/kaoda-review.git ~/.codex/skills/kaoda-review

# Claude Code
git clone https://github.com/ziibnchen98-creator/kaoda-review.git ~/.claude/skills/kaoda-review
```

安装后，你可以直接对 Agent 说：

```text
用 kaoda-review 拷打式复盘这个视频，正常模式，混合风格。
```

```text
我想了解 token，不给资料，你先研究，再生成一份 10 分钟复盘单。
```

```text
把这份 PDF 做成拷打式复盘，重点检查我能不能迁移应用。
```

---

## 它适合谁

适合：

- 看完课程、文章、播客、论文后，想知道自己到底懂没懂的人
- 学 AI、产品、商业、编程、心理学、方法论时，不想停留在“我好像知道了”的人
- 想把学习材料变成低压力自测题、错题本、周复盘的人
- 想让 Agent 帮自己做“理解诊断”，而不是再给一份摘要的人

不适合：

- 只想要一页总结
- 只想快速生成普通选择题
- 没有文件系统和 shell 权限的纯聊天机器人
- 要做严肃考试、认证题库或标准化测评的场景

---

## 能做什么

| 能力 | 产物 | 说明 |
| --- | --- | --- |
| 材料摄取 | `segments.jsonl` | 从文本、字幕、PDF、文章、视频字幕中提取带来源的学习片段 |
| 主题研究 | `topic_research.md`、`source_links.json` | 只有一个主题词时，先研究再出题，避免凭空编题 |
| 知识地图 | `material_report.json` | 提取核心概念、机制、边界、误解风险和迁移场景 |
| 复盘规划 | `exam_brief.json` | 记录模式、题型风格、研究状态和生成契约 |
| 互动复盘单 | `exam.html` | 单文件 HTML，可直接在浏览器里完成和判分 |
| 浏览器报告 | `kaoda_agent_report.md` | 答完后一键导出给 Agent，包含答案、分数和评分说明 |
| Agent 评分 | `grade.json` | 对短答、口述题按 rubric 评分，补充诊断分析 |
| 错题记忆 | `mistake_bank.jsonl` | 记录薄弱知识点、错因标签和复习优先级 |
| 变体复习 | `review.html` | 根据错题生成不重复的复习题 |
| 周复盘 | `weekly_exam.html` | 汇总最近 7 天错题，生成周度综合复盘 |
| 学习看板 | `dashboard/index.html` | 静态本地看板：总分、正确率、错题、笔记和历史记录 |

---

## 核心机制

### 1. 先研究，再出题

这个 skill 不允许 Agent 直接从一个标题或几段材料开始编题。正常流程必须先完成材料分析和核心研究，再生成复盘单。

如果你只给一个主题，比如 `token`、`RAG`、`注意力机制`，它会先生成研究任务，要求 Agent 写下研究笔记和来源链接，再进入出题流程。

### 2. 拷打的不是记忆，是理解

题目会围绕这些能力设计：

- 复述检查：你能不能说清基本概念
- 机制追问：你能不能解释为什么
- 边界识别：你知道它什么时候不成立吗
- 误解识别：你能看出一个错误说法错在哪吗
- 迁移应用：换到真实场景，你还能用吗
- 反例判断：遇到例外情况，你会不会乱套

### 3. 默认低压力，重模式才长答

默认 `正常模式` 不会把你塞进一堆长答题里。它主要用客观题快速定位薄弱点，浏览器内直接出分。

只有你选择 `拷打模式` 或 `深度拷打` 时，才会加入短答和口述题，用来训练表达、面试追问和真正的解释能力。

### 4. 本地优先，可长期积累

所有产物都在本地文件系统里：复盘记录、错题、周复盘、学习看板都可以持续积累。不需要数据库，不需要服务端，也不绑定某个 Agent 平台。

---

## 使用流程

Skill 会引导 Agent 按这个顺序工作：

1. 摄取材料或研究主题
2. 生成材料报告和知识地图
3. 完成核心研究和深化
4. 确认复盘模式、题目风格和错题策略
5. 生成 `exam.html`
6. 你在浏览器里答题并提交
7. 导出 `kaoda_agent_report.md`
8. Agent 评分并记录错题
9. 刷新学习看板
10. 后续生成变体复习或周复盘

最短本地示例：

```bash
cd ~/.codex/skills/kaoda-review

python3 scripts/kaoda.py ingest tests/fixtures/sample_text.txt --run-id demo
python3 scripts/kaoda.py plan-exam demo \
  --review-mode "正常模式" \
  --question-style "混合风格"
python3 scripts/kaoda.py build-exam demo
open data/runs/demo/exam.html
```

主题学习示例：

```bash
python3 scripts/kaoda.py research-topic "token" --run-id token-demo

# 然后让 Agent 完成：
# data/runs/token-demo/topic_research.md
# data/runs/token-demo/source_links.json

python3 scripts/kaoda.py ingest-topic token-demo
python3 scripts/kaoda.py plan-exam token-demo \
  --review-mode "正常模式" \
  --question-style "混合风格"
python3 scripts/kaoda.py build-exam token-demo
open data/runs/token-demo/exam.html
```

答完后，在浏览器里点击 `提交试卷`，进入学习报告页，再点击 `导出报告给 Agent`。Agent 拿到报告后可以继续：

```bash
python3 scripts/kaoda.py grade data/runs/demo/attempt.json --learner-id demo-user
python3 scripts/kaoda.py record data/runs/demo/grade.json
python3 scripts/kaoda.py dashboard demo-user
python3 scripts/kaoda.py review demo-user
python3 scripts/kaoda.py weekly demo-user --since 7d
```

---

## 复盘模式

| 模式 | 默认时长 | 适合场景 | 题目特点 |
| --- | --- | --- | --- |
| 复盘模式 | 5 分钟 | 刚学完，快速扫盲 | 更轻、更快，客观题为主 |
| 正常模式 | 10 分钟 | 默认推荐 | 约 20 题，浏览器直接判分 |
| 拷打模式 | 30 分钟 | 想练表达和迁移 | 加入短答、口述、追问 |
| 深度拷打 | 45 分钟 | 面试、汇报、深度掌握 | 更重的开放题和综合应用 |

题目风格可以选：

```text
正经复盘 / 趣味拷打 / 毒舌拷打 / 面试官追问 / 老板追问 / 朋友吐槽 / 反例猎人 / 概念诈骗识别 / 弹幕判断 / 混合风格
```

---

## 支持的输入

| 输入 | 支持情况 | 说明 |
| --- | --- | --- |
| 纯文本 / Markdown | 支持 | 最稳定 |
| 字幕文件 `.srt` / `.vtt` | 支持 | 保留时间戳 |
| PDF | 支持 | 需要本机有 `pdftotext`；扫描版可选 OCR |
| YouTube / Bilibili 链接 | 可用 | 优先抓字幕；没有字幕时需要转写能力或你提供文字稿 |
| 文章 URL | 可用 | 取决于网页是否可访问 |
| 单个主题词 | 支持 | 必须先研究，再 `ingest-topic` |

可选工具：

- `yt-dlp`：提取视频字幕
- `pdftotext`：提取 PDF 文本
- `pdftoppm` + `tesseract`：扫描版 PDF OCR

核心 CLI 只依赖 Python 标准库。

---

## 命令手册

```bash
# 摄取已有材料
python3 scripts/kaoda.py ingest <input> --run-id <id>

# 只有主题时，先生成研究任务
python3 scripts/kaoda.py research-topic "<topic>" --run-id <id>

# Agent 完成 topic_research.md 和 source_links.json 后摄取研究笔记
python3 scripts/kaoda.py ingest-topic <id>

# 规划复盘单，写入 exam_brief.json
python3 scripts/kaoda.py plan-exam <id> \
  --review-mode "正常模式" \
  --question-style "混合风格"

# 生成浏览器复盘单
python3 scripts/kaoda.py build-exam <id>

# 对答题结果评分
python3 scripts/kaoda.py grade <attempt.json> --learner-id <learner-id>

# 记录错题和归档
python3 scripts/kaoda.py record <grade.json>

# 生成个人学习看板
python3 scripts/kaoda.py dashboard <learner-id>

# 基于错题生成变体复习
python3 scripts/kaoda.py review <learner-id>

# 生成最近 7 天周复盘
python3 scripts/kaoda.py weekly <learner-id> --since 7d
```

重要约束：`build-exam` 会在缺少 `exam_brief.json` 时失败。这是故意的，目的是防止 Agent 跳过研究和复盘规划，直接生成一份看似完整但很浅的题单。

---

## 文件结构

```text
kaoda-review/
├── SKILL.md                       # Skill 主说明，Agent 入口
├── AGENTS.md                      # 给 Codex / 通用 Agent 的仓库说明
├── CLAUDE.md                      # 给 Claude Code 的使用说明
├── agents/openai.yaml             # OpenAI/Codex 兼容元信息
├── scripts/kaoda.py               # 确定性 CLI
├── assets/exam-template/          # HTML 复盘单模板
├── references/                    # 研究、出题、评分、质量门槛规则
└── tests/                         # 本地回归测试和压力场景
```

运行后会生成：

```text
data/
├── runs/<run_id>/                 # 单次材料、题单、报告
└── learners/<learner_id>/         # 错题、归档、看板、周复盘
```

`data/` 默认不提交到 git，避免把你的学习记录、视频转写和本地答题历史传到远端。

---

## 常见问题

### 它和“总结文章”有什么区别？

总结是在帮你压缩信息；拷打式复盘是在检查你能不能使用信息。它会故意问机制、边界、误解、反例和迁移场景，因为这些地方最容易暴露“我只是看懂了文字，但没真正掌握”。

### 它会自动联网研究吗？

Skill 规则要求 Agent 在出题前完成研究和深化，但是否能联网取决于你使用的 Agent 环境。不能联网时，也可以让 Agent 基于你提供的材料做 source-only 研究；只有当你明确说“只按原文”时才应该限制外部拓展。

### 为什么要有 `plan-exam`？

这是防止跑偏的硬门槛。没有它，Agent 很容易摄取完材料就直接编题，跳过研究、模式选择和题型策略。`exam_brief.json` 是“已经研究过、已经确认怎么复盘”的证明。

### 能不能只出客观题？

可以。默认 `复盘模式` 和 `正常模式` 就是客观题优先，浏览器内直接判分。想训练表达时再选 `拷打模式` 或 `深度拷打`。

### 能不能长期记录我的薄弱点？

可以。`record` 会把错题写入 `mistake_bank.jsonl`，并归档完整复盘。之后 `review` 和 `weekly` 会基于错题生成变体和周复盘。

### 普通 ChatGPT 能不能用？

纯聊天环境不太适合，因为这个 Skill 依赖文件系统、HTML 文件和命令行。更适合 Claude Code、Codex、Cursor 这类能读写文件、执行 shell 的本地 Agent。

---

## 开发与测试

本仓库的测试使用 Python 标准库 `unittest`：

```bash
python3 -m unittest discover -s tests -v
```

项目目前保持轻依赖：核心逻辑集中在 `scripts/kaoda.py`，模板在 `assets/exam-template/index.html`，规则文档在 `references/`。

欢迎提交 issue 或 PR，尤其是：

- 新材料类型的摄取方式
- 更好的题目质量门槛
- 更自然的中文题面
- 更稳定的视频字幕 / PDF 提取流程
- 更好的错题复习和周复盘策略

---

## 开源许可

本项目使用 MIT License。

个人学习、教学、团队内部使用和商业项目都可以免费使用。欢迎 fork、改造、二次分发；保留原始许可证即可。

