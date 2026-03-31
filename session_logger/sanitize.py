"""Text sanitization utilities — UTF-8 character filtering and cleanup."""

from __future__ import annotations

import re
import unicodedata

# Characters to strip: control chars (except newline/tab), surrogates,
# private-use area, unassigned codepoints, and byte-order marks.
_CONTROL_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufeff\ufffe\uffff]"
)


def sanitize_text(text: str | None) -> str | None:
    """Remove non-UTF-8-safe characters and normalize Unicode.

    Applies the following filters in order:
      1. NFKC Unicode normalization (collapses compatibility equivalents)
      2. Strip control characters (keeps newline, tab, carriage return)
      3. Replace non-BMP surrogates that slipped through
      4. Collapse runs of whitespace within lines
      5. Strip leading/trailing whitespace

    Returns None unchanged if the input is None.
    """
    if text is None:
        return None

    # 1. Normalize to NFKC (canonical decomposition + compatibility composition)
    text = unicodedata.normalize("NFKC", text)

    # 2. Strip control characters (preserve \n \r \t)
    text = _CONTROL_RE.sub("", text)

    # 3. Remove surrogate codepoints (U+D800–U+DFFF) that may appear in
    #    badly-encoded input; encode→decode with surrogatepass to catch them.
    text = text.encode("utf-8", errors="surrogatepass").decode(
        "utf-8", errors="ignore"
    )

    # 4. Collapse runs of horizontal whitespace (preserve newlines)
    lines = text.splitlines()
    lines = [re.sub(r"[^\S\n]+", " ", line) for line in lines]
    text = "\n".join(lines)

    # 5. Strip outer whitespace
    text = text.strip()

    return text if text else None


def sanitize_tags(tags: list[str]) -> list[str]:
    """Sanitize and deduplicate a list of tag strings."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        t = sanitize_text(tag)
        if t and t not in seen:
            # Tags should be lowercase, no spaces
            t = re.sub(r"\s+", "-", t.lower())
            if t not in seen:
                seen.add(t)
                cleaned.append(t)
    return cleaned
