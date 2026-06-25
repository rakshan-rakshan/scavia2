"""TTS-only pronunciation filter.

Replaces selected words with phonetic respellings *on the synthesis path only* so
brand/proper nouns are voiced correctly (e.g. "Brigade" -> "Brigaid" so it is spoken
"bri-GAYD", rhyming with "parade", not "bri-GAAD").

Pipecat runs TTS text filters AFTER sentence aggregation (default
``TextAggregationMode.SENTENCE``), so each ``filter`` call receives a whole sentence
and individual words stay intact. Chat is never affected because the text-chat path
does not run through a TTS service.
"""

import re
from collections.abc import Mapping
from typing import Any

from pipecat.utils.text.base_text_filter import BaseTextFilter


class PronunciationTextFilter(BaseTextFilter):
    """Whole-word, case-insensitive phonetic respelling for spoken TTS output.

    Args:
        replacements: Mapping of source word -> phonetic respelling. Matching is
            whole-word and case-insensitive; the respelling is substituted
            literally (no regex backreference interpretation).
    """

    def __init__(self, replacements: Mapping[str, str]):
        # Longest keys first so multi-word entries win over single words.
        self._rules: list[tuple[re.Pattern, str]] = [
            (re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE), respelling)
            for word, respelling in sorted(
                replacements.items(), key=lambda kv: len(kv[0]), reverse=True
            )
            if word
        ]

    async def filter(self, text: str) -> str:
        """Apply each respelling rule to the aggregated sentence text."""
        for pattern, respelling in self._rules:
            # Use a function replacement so backslashes/group refs in the
            # respelling (e.g. native-script values) are treated literally.
            text = pattern.sub(lambda _m, r=respelling: r, text)
        return text

    async def update_settings(self, settings: Mapping[str, Any]):
        """No runtime-tunable settings; respellings are fixed at construction."""
        pass

    async def handle_interruption(self):
        """Stateless filter; nothing to reset on interruption."""
        pass

    async def reset_interruption(self):
        """Stateless filter; nothing to restore after interruption."""
        pass
