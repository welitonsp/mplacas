from __future__ import annotations

import re

# The Telegram Bot API embeds the bot token directly in the URL path
# (e.g. https://api.telegram.org/bot<TOKEN>/sendMessage). Any log line,
# traceback or span that captures the raw URL leaks a credential that
# grants full control over the bot.
#
# ``_TOKEN_SEGMENT`` matches only the token portion of the path and is used
# where the caller has *already* established the host out of band (e.g.
# ``sanitized_http_url`` in ``tracing.py``, which only substitutes after
# checking ``parsed.hostname``).
#
# ``TELEGRAM_URL_PATTERN`` additionally anchors on the ``api.telegram.org``
# host so it is safe to apply to arbitrary, unstructured text — log
# messages, formatted exceptions/tracebacks — without corrupting unrelated
# content that merely happens to contain ``/bot...`` (e.g. ``/bots/create``,
# a hypothetical bot-status log line).
_TOKEN_SEGMENT = r"/bot[^/\s\"']+"
TELEGRAM_TOKEN_PATTERN = re.compile(_TOKEN_SEGMENT)
TELEGRAM_URL_PATTERN = re.compile(r"api\.telegram\.org" + _TOKEN_SEGMENT, re.IGNORECASE)

_TOKEN_REDACTION = "/bot<redacted>"
_URL_REDACTION = "api.telegram.org/bot<redacted>"


def redact_secrets(text: str) -> str:
    """Return ``text`` with known secret patterns replaced by a placeholder.

    This is intended for arbitrary, unstructured text (log messages,
    formatted exceptions/tracebacks) where the secret's URL host is still
    present, so matching is anchored on the host to avoid false positives.
    """
    return TELEGRAM_URL_PATTERN.sub(_URL_REDACTION, text)
