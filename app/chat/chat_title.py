"""
Name a freshly created chat after what the user actually asked for.

ChatStorage falls back to a positional name ("Чат 89") when `create_chat` is given no
title, so a user's history reads as an unnavigable list of numbers. The title is derived
from the first message locally rather than asked of the LLM: the chat is created before
the model runs, and a title is not worth either an extra round trip or a schema field the
model would have to re-decide on every later turn.
"""

import re

FALLBACK_TITLE_RU = "Генерация функционального зонирования"
CUSTOM_FALLBACK_TITLE_RU = "Зонирование загруженной территории"

MAX_TITLE_LENGTH = 60

_MIN_MEANINGFUL_LENGTH = 3
_TRAILING_PUNCTUATION = " .,;:!?-—…"


def build_chat_title(user_query: str, fallback: str = FALLBACK_TITLE_RU) -> str:
    """
    Build a chat title from the user's first message.

    Falls back to a generic name for openers too short to mean anything ("да", "?"),
    which would otherwise produce a title even less useful than the positional one.
    """

    text = re.sub(r"\s+", " ", (user_query or "").strip())
    if len(text) < _MIN_MEANINGFUL_LENGTH:
        return fallback

    first_sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first_sentence) <= MAX_TITLE_LENGTH:
        title = first_sentence.strip(_TRAILING_PUNCTUATION)
    else:
        # Cut on a word boundary so the ellipsis never lands mid-word; a single
        # word longer than the limit has no boundary to cut on and is kept whole.
        head = text[:MAX_TITLE_LENGTH]
        truncated = (head.rsplit(" ", 1)[0] if " " in head else head).strip(_TRAILING_PUNCTUATION)
        title = f"{truncated}…" if truncated else ""

    if not title:
        return fallback
    return title[0].upper() + title[1:]
