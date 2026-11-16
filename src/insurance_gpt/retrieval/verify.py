"""Quote verification: is a quote really in the source passage?

Tolerates only differences that don't change the wording: whitespace and line breaks, typographic quotes
and dashes, letter case, list bullets, punctuation at the edges, and "…" / "[…]" for omitted text (each
remaining piece must appear in order). Anything else (a changed, added or missing word) is not verified.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from insurance_gpt.ingest.chunk import ABBREVIATIONS

CHAR_MAP = {
    "„": '"',
    "“": '"',
    "”": '"',
    "«": '"',
    "»": '"',
    "‚": "'",
    "‘": "'",
    "’": "'",
    "`": "'",
    "´": "'",
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "−": "-",
    "•": " ",
    " ": " ",
    "­": "",
}
ELLIPSIS_RE = re.compile(r"\[\s*(?:…|\.\.\.)\s*\]|\(\s*(?:…|\.\.\.)\s*\)|…|\.\.\.")
EDGE_CHARS = " \"'.,;:!?-"
BREAK_RE = re.compile(r"\n|[.!?]\s+")


@dataclass
class QuoteMatch:
    spans: list[tuple[int, int]]  # (start, end) of each quoted piece in the original text
    length: int  # matched characters after normalisation


@dataclass
class Segment:
    text: str
    highlight: bool


def normalize(text: str) -> tuple[str, list[int]]:
    """Normalised text plus, for each of its characters, the index of the original character."""
    out: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        ch = CHAR_MAP.get(ch, ch)
        if not ch:
            continue
        if ch.isspace():
            if not out or out[-1] == " ":
                continue
            ch = " "
        lower = ch.lower()
        out.append(lower if len(lower) == 1 else ch)
        index.append(i)
    return "".join(out), index


def find_quote(quote: str, text: str) -> QuoteMatch | None:
    norm_text, index = normalize(text)
    spans: list[tuple[int, int]] = []
    pos = length = 0
    for part in ELLIPSIS_RE.split(quote):
        norm_part = normalize(part)[0].strip(EDGE_CHARS)
        if not norm_part:
            continue
        found = norm_text.find(norm_part, pos)
        if found < 0:
            return None
        end = found + len(norm_part)
        spans.append((index[found], index[end - 1] + 1))
        pos, length = end, length + len(norm_part)
    if not spans:
        return None
    start, end = spans[-1]
    if text[end : end + 1] in (".", "!", "?"):  # the quote's own sentence end, stripped above
        spans[-1] = (start, end + 1)
    return QuoteMatch(spans, length)


def _breaks(text: str) -> list[tuple[int, int]]:
    """(end, start) of every line break and sentence end: where one sentence ends and the next starts.
    Not after abbreviations ("z. B."), and not at ":" ("Zahnersatz Sofort (ZEZ): Nein." is one sentence)."""
    breaks = []
    for m in BREAK_RE.finditer(text):
        if m.group() != "\n" and text[: m.start() + 1].split()[-1].lstrip('("„') in ABBREVIATIONS:
            continue
        breaks.append((m.start() + (m.group() != "\n"), m.end()))
    return breaks


def sentences(text: str) -> list[str]:
    """Lines, split further at sentence ends."""
    bounds = [0, *(pos for brk in _breaks(text) for pos in brk), len(text)]
    return [s for s in (text[a:b].strip() for a, b in zip(bounds[::2], bounds[1::2], strict=True)) if s]


def closest_sentence(quote: str, text: str, min_coverage: float = 0.6) -> str | None:
    """The sentence of `text` that covers most of the quote, to help the model correct it."""
    norm_quote = normalize(quote)[0]
    best, best_coverage = None, min_coverage
    for sentence in sentences(text):
        matcher = SequenceMatcher(None, norm_quote, normalize(sentence)[0], autojunk=False)
        coverage = sum(block.size for block in matcher.get_matching_blocks()) / max(len(norm_quote), 1)
        if coverage > best_coverage:
            best, best_coverage = sentence, coverage
    return best


def context(text: str, spans: list[tuple[int, int]], reach: int) -> list[Segment]:
    """The quoted pieces (highlighted) with surrounding text: back to the start of the quote's sentence and on
    to its end if within `reach` characters, else cut at a word with "…". A passage of up to 3 × reach is
    shown whole (e.g. a table row with all tariffs). Omitted stretches longer than `reach` become " […] "."""
    if len(text) <= 3 * reach:
        (lo, cut_before), (hi, cut_after) = (0, False), (len(text), False)
    else:
        breaks = _breaks(text)
        lo, cut_before = _start(text, breaks, spans[0][0], reach)
        hi, cut_after = _end(text, breaks, spans[-1][1], reach)
    segments = [Segment(("… " if cut_before else "") + text[lo : spans[0][0]], False)]
    for i, (start, end) in enumerate(spans):
        if i:
            gap = text[spans[i - 1][1] : start]
            segments.append(Segment(gap if len(gap) <= reach else " […] ", False))
        segments.append(Segment(text[start:end], True))
    segments.append(Segment(text[spans[-1][1] : hi] + (" …" if cut_after else ""), False))
    return [s for s in segments if s.text]


def _start(text: str, breaks: list[tuple[int, int]], pos: int, reach: int) -> tuple[int, bool]:
    """(offset, cut mid-sentence) where the context before `pos` starts."""
    starts = [start for _, start in breaks if pos - reach <= start <= pos]
    if starts:
        return max(starts), False
    if pos <= reach:
        return 0, False
    space = text.find(" ", pos - reach, pos)
    return (space + 1, True) if space >= 0 else (pos, True)


def _end(text: str, breaks: list[tuple[int, int]], pos: int, reach: int) -> tuple[int, bool]:
    """(offset, cut mid-sentence) where the context after `pos` ends."""
    ends = [end for end, _ in breaks if pos <= end <= pos + reach]
    if ends:
        return min(ends), False
    if pos + reach >= len(text):
        return len(text), False
    space = text.rfind(" ", pos, pos + reach)
    return (space, True) if space >= 0 else (pos, True)
