"""
Name a freshly created chat after what the user actually asked for.

ChatStorage falls back to a positional name ("Чат 89") when `create_chat` is given no
title, so a user's history reads as an unnavigable list of numbers. The title comes from
the model, which already produces the turn's decision JSON -- asking it for one more
field costs no extra round trip. Everything the model returns still goes through
`resolve_chat_title`: constrained decoding guarantees a string, not a usable heading, and
the local heuristic covers both a bad title and a turn where the model never ran.
"""

import re

FALLBACK_TITLE_RU = "Генерация функционального зонирования"
CUSTOM_FALLBACK_TITLE_RU = "Зонирование загруженной территории"

MAX_TITLE_LENGTH = 60

_MIN_MEANINGFUL_LENGTH = 3
_TRAILING_PUNCTUATION = " .,;:!?-—…\"'«»`"


def _shorten(text: str) -> str:
    """Trim a one-line title to MAX_TITLE_LENGTH, cutting on a word boundary."""

    if len(text) <= MAX_TITLE_LENGTH:
        return text.strip(_TRAILING_PUNCTUATION)

    # A single word longer than the limit has no boundary to cut on and is kept whole.
    head = text[:MAX_TITLE_LENGTH]
    truncated = (head.rsplit(" ", 1)[0] if " " in head else head).strip(_TRAILING_PUNCTUATION)
    return f"{truncated}…" if truncated else ""


def _capitalize(text: str) -> str:
    return text[0].upper() + text[1:] if text else text


def build_chat_title(user_query: str, fallback: str = FALLBACK_TITLE_RU) -> str:
    """
    Derive a chat title from the user's first message.

    The fallback used when the model is not available to name the chat (its call failed)
    or gave nothing usable. Openers too short to mean anything ("да", "?") get the
    generic name instead, which is still more informative than a mangled two-letter one.
    """

    text = re.sub(r"\s+", " ", (user_query or "").strip())
    if len(text) < _MIN_MEANINGFUL_LENGTH:
        return fallback

    first_sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    title = _shorten(first_sentence if len(first_sentence) <= MAX_TITLE_LENGTH else text)
    return _capitalize(title) if title else fallback


def resolve_chat_title(
    model_title: object,
    user_query: str,
    fallback: str = FALLBACK_TITLE_RU,
) -> str:
    """
    Turn the `chat_title` the model returned into a title fit for a chat list.

    Models answer the field with a whole sentence, a quoted phrase or a bare greeting
    often enough that it cannot be trusted verbatim; anything that survives cleaning is
    used, anything that does not falls back to the message-derived title.
    """

    if not isinstance(model_title, str):
        return build_chat_title(user_query, fallback)

    text = re.sub(r"\s+", " ", model_title.strip()).strip(_TRAILING_PUNCTUATION)
    if len(text) < _MIN_MEANINGFUL_LENGTH:
        return build_chat_title(user_query, fallback)

    return _capitalize(_shorten(text)) or build_chat_title(user_query, fallback)
