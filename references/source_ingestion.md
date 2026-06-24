# Source Ingestion

## Input Routing

Use this order:

1. Local subtitle (`.srt`, `.vtt`) or text supplied by the learner.
2. PDF text extraction.
3. Article正文 extraction.
4. Video subtitles through `yt-dlp`.
5. Local audio/video sidecar transcripts (`same-name .srt/.vtt/.txt/.md`).
6. Manual text fallback through `ingest-manual`.

Never invent missing source content.

## Video URLs

Run:

```bash
python scripts/kaoda.py ingest "<video-url>"
```

The CLI uses `yt-dlp` to request subtitles and auto subtitles. Platform support can break, login may be required, and some videos have no captions.

If subtitle extraction fails:

- The CLI creates `source_status.json`, `manual_transcript.txt`, and `manual_text_request.md`.
- Ask for `.srt`, `.vtt`, `.txt`, or copied transcript.
- Paste text into `manual_transcript.txt`, then run:

```bash
python scripts/kaoda.py ingest-manual <run_id>
```

- Do not summarize from the title or metadata.
- Do not download copyrighted video content unless the user has a lawful basis and the runtime policy permits it.

## Local Audio / Video Files

Run:

```bash
python scripts/kaoda.py ingest "/path/to/lesson.mp4"
```

Best low-dependency path: put a same-name transcript next to the media file:

```text
lesson.mp4
lesson.vtt
# or lesson.srt / lesson.txt / lesson.md
```

If no transcript exists, the CLI creates a manual transcript workspace. Optional local transcription can be done outside the core CLI with `ffmpeg` plus Whisper/whisper.cpp, then saved as `.txt`, `.srt`, or `.vtt`. Do not claim the media was transcribed unless the transcript file exists and was ingested.

## PDFs

The CLI tries `pdftotext` first and preserves page numbers in segment locators. If `pdftotext` is not available or output is thin, it tries a small Python-stdlib text fallback for simple text PDFs. If text is still too thin, it tries OCR with `pdftoppm` and `tesseract`.

If OCR is unavailable:

- The CLI creates `source_status.json`, `manual_input.txt`, and `manual_text_request.md`.
- Ask the user for exported text or OCR output.
- Paste text into `manual_input.txt`, then run `python scripts/kaoda.py ingest-manual <run_id>`.
- Record that scanned pages could not be read.

## Articles

The CLI extracts title, author, publish time when visible, and正文 text. It skips common navigation, header, footer, sidebar, comment, ad, subscribe, and related-content areas. Web extraction is best-effort. If the page is blocked, paywalled, script-rendered, or mostly navigation:

- The CLI creates `manual_input.txt`.
- Ask the user to paste the article title, author/date if visible, and正文.
- Run `python scripts/kaoda.py ingest-manual <run_id>`.
- Do not rely on snippets alone.

## Manual Continuation Contract

When `ingest` returns `status: needs_text`, continue with:

```bash
python scripts/kaoda.py ingest-manual <run_id>
```

Only run this after replacing the placeholder in `manual_input.txt` or `manual_transcript.txt` with real source text. After `ingest-manual`, `segments.jsonl` and `material_report.json` are created and the normal deep-research gate applies.

## Segment Contract

Every `segments.jsonl` row must include:

```json
{
  "segment_id": "source-seg-0001",
  "source_id": "source-id",
  "kind": "source",
  "locator": {"page": 1, "timestamp": "00:00:01 --> 00:00:04", "url": "https://..."},
  "text": "source text"
}
```

At least one locator field must identify where the segment came from.
