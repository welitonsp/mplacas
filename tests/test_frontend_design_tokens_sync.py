"""Guards against silent drift between `frontend/src/index.css` (the real
design tokens, both themes) and `frontend/src/test/designTokens.ts` (a manual
hex mirror the frontend test suite consumes instead, because Vitest mocks
every `.css` import — including `?raw` — before Vite can process the query,
so `contrastRatio.test.ts` cannot read the compiled CSS at test time; see the
docstring at the top of `designTokens.ts` and ADR-071 Decisão 7).

Without this test, an edit to a hex value (or an added/removed token) in
`index.css` with no matching edit in `designTokens.ts` would leave
`contrastRatio.test.ts` green while checking stale values — a real
contrast regression could ship to the actual app undetected by that suite.
This test reads both source files directly (same precedent as
`tests/test_frontend_auth_contract.py`, which reads frontend source from the
backend test suite) and fails with the exact token name/values whenever the
two files disagree.

One asymmetry is legitimate, not drift: `designTokens.ts`'s `LIGHT_TOKENS`
carries the ten `--color-gray-*` steps, but `index.css`'s light `:root` block
never declares them as a literal hex custom property — Tailwind v4 generates
that scale itself as `oklch(...)` inside its own `@layer theme` (ADR-071,
Contexto). `designTokens.ts` documents (see the comment above its `gray-*`
entries) that those ten light values are a manual OKLab->sRGB conversion of
the real compiled output, present only so the light/dark contrast test has
something to check. `_LIGHT_GRAY_SCALE` below is the one documented
exception to "every key must match exactly"; anything else diverging is a
real bug this test must catch.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_CSS = ROOT / "frontend" / "src" / "index.css"
DESIGN_TOKENS_TS = ROOT / "frontend" / "src" / "test" / "designTokens.ts"

_HEX = r"#[0-9a-fA-F]{3,8}"

# CSS side: capture the raw body of each `:root` block, strip `/* ... */`
# comments (none of which happen to contain a literal `--color-x: #hex;`
# today, but stripping first makes that true by construction rather than by
# luck), then pull out every custom-property declaration.
_CSS_LIGHT_BLOCK = re.compile(r":root \{(.*?)\n\}", re.DOTALL)
_CSS_DARK_BLOCK = re.compile(r':root\[data-theme="dark"\] \{(.*?)\n\}', re.DOTALL)
_CSS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_PAIR = re.compile(r"(--color-[\w-]+):\s*(" + _HEX + r");")

# TS side: same idea for the `LIGHT_TOKENS`/`DARK_TOKENS` object literals.
_TS_LIGHT_BLOCK = re.compile(r"export const LIGHT_TOKENS = \{(.*?)\n\} as const", re.DOTALL)
_TS_DARK_BLOCK = re.compile(r"export const DARK_TOKENS = \{(.*?)\n\} as const", re.DOTALL)
_TS_LINE_COMMENT = re.compile(r"//[^\n]*")
_TS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_TS_PAIR = re.compile(r"'(--color-[\w-]+)':\s*'(" + _HEX + r")'")

_LIGHT_GRAY_SCALE = {
    f"--color-gray-{step}" for step in (50, 100, 200, 300, 400, 500, 600, 700, 800, 900)
}


def _extract_css_pairs(css_text: str, block_pattern: re.Pattern[str]) -> dict[str, str]:
    match = block_pattern.search(css_text)
    assert match, (
        f"could not locate a block matching {block_pattern.pattern!r} in "
        f"{INDEX_CSS} — has the `:root` selector syntax changed?"
    )
    block = _CSS_BLOCK_COMMENT.sub("", match.group(1))
    return dict(_CSS_PAIR.findall(block))


def _extract_ts_pairs(ts_text: str, block_pattern: re.Pattern[str]) -> dict[str, str]:
    match = block_pattern.search(ts_text)
    assert match, (
        f"could not locate a block matching {block_pattern.pattern!r} in "
        f"{DESIGN_TOKENS_TS} — has the export syntax changed?"
    )
    block = _TS_BLOCK_COMMENT.sub("", match.group(1))
    block = _TS_LINE_COMMENT.sub("", block)
    return dict(_TS_PAIR.findall(block))


def _assert_themes_match(
    theme: str,
    css_pairs: dict[str, str],
    ts_pairs: dict[str, str],
    *,
    allowed_ts_only: set[str] = frozenset(),
) -> None:
    css_keys = set(css_pairs)
    ts_keys = set(ts_pairs)

    # Every token literally declared in index.css must have a mirror in
    # designTokens.ts — no documented exception goes in this direction.
    missing_in_ts = sorted(css_keys - ts_keys)
    assert not missing_in_ts, (
        f"[{theme}] token(s) declared in {INDEX_CSS} with no mirror in "
        f"{DESIGN_TOKENS_TS}: "
        + ", ".join(f"{name}={css_pairs[name]}" for name in missing_in_ts)
    )

    # Any designTokens.ts key absent from index.css must be exactly the
    # documented gray-* exception (light theme only) — anything else is
    # either stale (removed from CSS, never removed from the TS mirror) or a
    # new token added to the TS mirror without the corresponding CSS change.
    unexpected_ts_only = sorted((ts_keys - css_keys) - allowed_ts_only)
    assert not unexpected_ts_only, (
        f"[{theme}] token(s) present in {DESIGN_TOKENS_TS} with no matching "
        f"declaration in {INDEX_CSS} (and not covered by the documented "
        f"gray-* exception): "
        + ", ".join(f"{name}={ts_pairs[name]}" for name in unexpected_ts_only)
    )

    # The documented exception itself must be complete, not partially there.
    missing_allowed = sorted(allowed_ts_only - ts_keys)
    assert not missing_allowed, (
        f"[{theme}] expected exception token(s) missing from "
        f"{DESIGN_TOKENS_TS}: {', '.join(missing_allowed)}"
    )

    # Finally, every token present in both files must agree on the hex value.
    mismatched = sorted(
        name
        for name in css_keys & ts_keys
        if css_pairs[name].lower() != ts_pairs[name].lower()
    )
    assert not mismatched, (
        f"[{theme}] token value(s) diverged between {INDEX_CSS} and "
        f"{DESIGN_TOKENS_TS}: "
        + "; ".join(
            f"{name} is {css_pairs[name]} in index.css but {ts_pairs[name]} "
            "in designTokens.ts"
            for name in mismatched
        )
    )


def test_light_theme_tokens_match_between_index_css_and_design_tokens_ts() -> None:
    css_text = INDEX_CSS.read_text(encoding="utf-8")
    ts_text = DESIGN_TOKENS_TS.read_text(encoding="utf-8")

    css_pairs = _extract_css_pairs(css_text, _CSS_LIGHT_BLOCK)
    ts_pairs = _extract_ts_pairs(ts_text, _TS_LIGHT_BLOCK)

    assert css_pairs, f"extracted zero light tokens from {INDEX_CSS} — regex broken?"
    assert ts_pairs, f"extracted zero light tokens from {DESIGN_TOKENS_TS} — regex broken?"

    _assert_themes_match(
        "light", css_pairs, ts_pairs, allowed_ts_only=_LIGHT_GRAY_SCALE
    )


def test_dark_theme_tokens_match_between_index_css_and_design_tokens_ts() -> None:
    css_text = INDEX_CSS.read_text(encoding="utf-8")
    ts_text = DESIGN_TOKENS_TS.read_text(encoding="utf-8")

    css_pairs = _extract_css_pairs(css_text, _CSS_DARK_BLOCK)
    ts_pairs = _extract_ts_pairs(ts_text, _TS_DARK_BLOCK)

    assert css_pairs, f"extracted zero dark tokens from {INDEX_CSS} — regex broken?"
    assert ts_pairs, f"extracted zero dark tokens from {DESIGN_TOKENS_TS} — regex broken?"

    # Dark theme has no documented gray-* exception: `index.css` redefines
    # `--color-gray-50..900` explicitly (ADR-071 Decisão 3/4), so the two
    # sets are expected to match exactly, key for key.
    _assert_themes_match("dark", css_pairs, ts_pairs)
