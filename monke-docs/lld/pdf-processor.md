# LLD: pdf_processor

> Container: C1 (synapticore-core) | Subpackage: tools/
> HLD Reference: S3 C1.2.5
> Status: stub (not yet implemented)

## Responsibility

PDF text extraction and chunking for agent consumption. Accepts a file path or raw bytes, extracts text page-by-page, and returns structured page objects suitable for downstream LLM context windows. The PDF library is ADR-gated (OQ-006: PyMuPDF vs. alternatives).

## Public API

### Request & Response Models

| Class | Fields | Notes |
|-------|--------|-------|
| `PdfProcessRequest` | `file_path: str \| bytes`, `pages: list[int] \| None = None`, `chunk_size: int \| None = None`, `chunk_overlap: int \| None = None` | `file_path` is either an absolute filesystem path (str) or raw PDF bytes. `pages` is an optional 0-indexed page filter; `None` means all pages. `chunk_size` and `chunk_overlap` control optional text chunking per page (characters). When both are `None`, full page text is returned unchunked. |
| `PdfPage` | `page_number: int`, `text: str`, `chunks: list[str] \| None = None`, `char_count: int` | Single extracted page. `page_number` is 0-indexed. `text` is the full extracted text of the page. `chunks` is populated only when `chunk_size` is set on the request. `char_count` is `len(text)`. |
| `PdfProcessResult` | `pages: list[PdfPage]`, `total_pages: int`, `extracted_pages: int`, `source: str` | `total_pages` is the total page count of the PDF (regardless of filter). `extracted_pages` is `len(pages)`. `source` is the original file path or `"<bytes>"` for in-memory input. |

### Functions

| Function | Signature | Notes |
|----------|-----------|-------|
| `process_pdf` | `async def process_pdf(request: PdfProcessRequest) -> PdfProcessResult` | Main entry point. Opens the PDF, extracts text for requested pages, optionally chunks, returns structured result. Raises `ToolExecutionError` on any failure. |

## Internal Design

### Key Design Decisions

1. **ADR-gated library dependency (OQ-006)** -- The PDF parsing library is not yet chosen. The HLD lists PyMuPDF as the leading candidate, but alternatives (pdfplumber, pypdf, pdfminer.six) require evaluation via ADR. The internal design is written against an abstract extraction interface so the library can be swapped without changing the public API.
2. **Async wrapper over sync I/O** -- PDF parsing libraries are synchronous. `process_pdf` is `async` for consistency with the tool interface but delegates file I/O and parsing to `asyncio.to_thread()` to avoid blocking the event loop.
3. **Dual input mode: path vs. bytes** -- `file_path` accepts either a filesystem path (str) or raw PDF content (bytes). The bytes path supports in-memory PDFs received from other tools or agents without requiring a temp file. The internal extraction function dispatches on type.
4. **Chunking is optional and page-scoped** -- When `chunk_size` is set, each page's text is split into overlapping chunks. Chunking operates per-page, not across page boundaries, preserving page-level attribution for citations. Overlap defaults to 0 when `chunk_overlap` is None.
5. **0-indexed pages** -- Page numbers are 0-indexed internally, matching PyMuPDF and most PDF libraries. The `pages` filter in `PdfProcessRequest` uses 0-indexed values. Invalid page indices (negative, out of range) are silently skipped with a warning logged, not raised as errors.
6. **No OCR** -- This component handles text-based PDFs only. Scanned/image PDFs return empty text per page. OCR support is out of scope for v1 and would require a separate ADR if added.
7. **File validation up front** -- Before attempting extraction, the function validates: (a) the file exists (for path input), (b) the content starts with the PDF magic bytes (`%PDF`), and (c) the file is not encrypted/password-protected. All validation failures raise `ToolExecutionError` with descriptive messages.

### Module Structure

```
synapticore/tools/pdf_processor.py
    PdfProcessRequest (Pydantic BaseModel)
    PdfPage (Pydantic BaseModel)
    PdfProcessResult (Pydantic BaseModel)
    process_pdf(request: PdfProcessRequest) -> PdfProcessResult
    _extract_pages(source: str | bytes, page_filter: list[int] | None) -> tuple[list[_RawPage], int]
    _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]
    _validate_pdf_source(source: str | bytes) -> None
```

### Internal Types (not exported)

| Type | Fields | Notes |
|------|--------|-------|
| `_RawPage` | `page_number: int`, `text: str` | Intermediate type returned by `_extract_pages`. Decouples library-specific page objects from the public `PdfPage` model. |

### Processing Flow

```
process_pdf(request)
  |
  +--> _validate_pdf_source(request.file_path)
  |      raises ToolExecutionError if:
  |        - path does not exist (str input)
  |        - bytes do not start with %PDF magic
  |        - PDF is encrypted
  |
  +--> asyncio.to_thread(_extract_pages, request.file_path, request.pages)
  |      opens PDF (from path or bytes)
  |      iterates pages, applies page filter
  |      returns (list[_RawPage], total_page_count)
  |
  +--> for each _RawPage:
  |      build PdfPage with text, char_count
  |      if chunk_size is set:
  |        PdfPage.chunks = _chunk_text(text, chunk_size, overlap)
  |
  +--> return PdfProcessResult(pages, total_pages, extracted_pages, source)
```

### Chunking Algorithm (`_chunk_text`)

Simple character-based sliding window:
1. If `len(text) <= chunk_size`, return `[text]`.
2. Otherwise, advance by `chunk_size - overlap` characters per step.
3. Each chunk is `text[start:start + chunk_size]`.
4. The final chunk captures any remaining text (may be shorter than `chunk_size`).

This is intentionally naive. Semantic chunking (sentence-aware, token-aware) is a future enhancement and would require its own design pass.

## Dependencies

### Internal
- `types/common_types` -- `ToolExecutionError` for error raising, `SynaptiCoreError` base class.

### External
- **ADR-gated (OQ-006):** One of `pymupdf` (PyMuPDF/fitz), `pypdf`, `pdfplumber`, or `pdfminer.six`. Until ADR is resolved, the stub implementation raises `ToolExecutionError("pdf_processor", "PDF library not yet selected (OQ-006)")`.
- `pydantic` (BaseModel, Field, field_validator)
- `asyncio` (to_thread)
- `pathlib` (Path -- for file existence checks)
- `logging` (structured warnings for skipped pages)

## Error Contracts

### Raised by this module
- `ToolExecutionError(tool_name="pdf_processor", ...)` for all failures:

| Scenario | `original_error` value |
|----------|----------------------|
| File not found (str path) | `"File not found: {path}"` |
| Invalid PDF (magic bytes check failed) | `"Not a valid PDF file: {source_desc}"` |
| Encrypted/password-protected PDF | `"PDF is encrypted and cannot be processed: {source_desc}"` |
| Library parse error (corrupted PDF, unexpected format) | `"Failed to extract text: {library_error_message}"` |
| ADR not resolved (stub state) | `"PDF library not yet selected (OQ-006)"` |
| Empty bytes input | `"Empty bytes input -- no PDF content provided"` |

### Consumed from other modules
- None. This is a leaf tool module with no internal callers at the tool layer.

### Raised implicitly
- `pydantic.ValidationError` on invalid `PdfProcessRequest` construction (e.g., `file_path` is `None`, `chunk_size` is negative).

## Test Plan

### Unit tests (`tests/unit/tools/test_pdf_processor.py`)

**PdfProcessRequest validation:**
- Constructs with `file_path` as str
- Constructs with `file_path` as bytes
- Constructs with `pages` filter
- Constructs with `chunk_size` and `chunk_overlap`
- Rejects `chunk_size <= 0` (validator)
- Rejects `chunk_overlap >= chunk_size` (validator)
- Defaults: `pages=None`, `chunk_size=None`, `chunk_overlap=None`

**PdfPage model:**
- Constructs with page_number, text, char_count
- `chunks` is `None` when chunking not requested
- `chunks` is populated list when chunking applied
- `char_count` matches `len(text)`

**PdfProcessResult model:**
- `extracted_pages` equals `len(pages)`
- `total_pages` reflects full document page count
- `source` is file path string or `"<bytes>"`

**_chunk_text:**
- Text shorter than chunk_size returns single-element list
- Text exactly equal to chunk_size returns single-element list
- Text longer than chunk_size produces correct number of chunks
- Overlap produces overlapping content between adjacent chunks
- Zero overlap (default) produces non-overlapping chunks
- Empty string returns `[""]`

**_validate_pdf_source:**
- Valid file path passes (mock `Path.exists`)
- Missing file raises `ToolExecutionError`
- Valid bytes with `%PDF` prefix passes
- Invalid bytes (no magic) raises `ToolExecutionError`
- Empty bytes raises `ToolExecutionError`

**process_pdf (mocked extraction):**
- Extracts all pages from a mock PDF (no page filter)
- Extracts filtered pages (pages=[0, 2] of a 5-page PDF)
- Skips out-of-range page indices silently
- Returns unchunked results when `chunk_size` is None
- Returns chunked results when `chunk_size` is set
- Encrypted PDF raises `ToolExecutionError`
- Corrupted PDF raises `ToolExecutionError`
- Bytes input works identically to path input (mock both)
- Stub state raises `ToolExecutionError` with OQ-006 message

**Serialization round-trip:**
- `model_dump()` -> `model_validate()` for `PdfProcessRequest`, `PdfPage`, `PdfProcessResult`

**Edge cases:**
- PDF with 0 extractable text (image-only) returns pages with empty `text` and `char_count=0`
- Single-page PDF with page filter `[0]` returns 1 page
- Single-page PDF with page filter `[1]` returns 0 pages (skipped, out of range)
- Very large `chunk_overlap` relative to `chunk_size` is rejected by validator
- `file_path` as bytes containing valid PDF content

### Integration tests (`tests/integration/tools/test_pdf_processor_integration.py`)

*(Runnable only after OQ-006 ADR is resolved and library is installed.)*

- Extract text from a real multi-page PDF fixture file
- Verify page count matches expected
- Verify extracted text contains expected content
- Chunking produces expected chunk boundaries on real text
- Bytes input with real PDF content matches path input results

## ADR References

- **OQ-006 (Pending):** PyMuPDF vs. alternative PDF library. Candidates: `pymupdf` (fast C-based, GPL-licensed), `pypdf` (pure Python, Apache-2.0), `pdfplumber` (table-aware, MIT), `pdfminer.six` (layout-aware, MIT). Decision impacts: performance, license compatibility, text extraction quality, table handling, install size.

## Maturity

All functions: `stub` (blocked on OQ-006 ADR)
