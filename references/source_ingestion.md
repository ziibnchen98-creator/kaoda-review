# Source Ingestion

## Input Routing

Use this order:

1. Local subtitle (`.srt`, `.vtt`) or text supplied by the learner.
2. PDF text extraction.
3. Article正文 extraction.
4. Video subtitles through `yt-dlp`.
5. Audio transcription only when subtitles are not available and the runtime has a transcription path.

Never invent missing source content.

## Video URLs

Run:

```bash
python scripts/kaoda.py ingest "<video-url>"
```

The CLI uses `yt-dlp` to request subtitles and auto subtitles. Platform support can break, login may be required, and some videos have no captions.

If subtitle extraction fails:

- Ask for `.srt`, `.vtt`, `.txt`, or copied transcript.
- Do not summarize from the title or metadata.
- Do not download copyrighted video content unless the user has a lawful basis and the runtime policy permits it.

## PDFs

The CLI tries `pdftotext` first and preserves page numbers in segment locators. If text is too thin, it tries OCR with `pdftoppm` and `tesseract`.

If OCR is unavailable:

- Ask the user for exported text.
- Record that scanned pages could not be read.

## Articles

The CLI extracts title, author, publish time when visible, and正文 text. Web extraction is best-effort. If the page is blocked, paywalled, script-rendered, or mostly navigation:

- Ask the user to paste the article text.
- Do not rely on snippets alone.

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
