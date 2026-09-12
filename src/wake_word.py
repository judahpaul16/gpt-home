import re
from typing import Optional


def is_repetition(words: list[str]) -> bool:
    for period in (1, 2, 3):
        if len(words) >= 2 * period and words == words[:period] * (len(words) // period):
            return True
    return False


def command_after_wake_word(clean_text: str, keyword: str) -> Optional[str]:
    """The words spoken after the wake word, or None when the wake word is
    absent or the transcript is a transcriber hallucination (a short phrase
    repeated back to back)."""
    words = clean_text.split()
    if is_repetition(words):
        return None

    match = re.search(rf"\b{re.escape(keyword.lower())}\b", clean_text)
    if not match:
        return None

    return clean_text[match.end():].strip()
