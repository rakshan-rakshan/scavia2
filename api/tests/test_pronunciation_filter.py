"""Tests for the TTS-only pronunciation filter.

The filter respells brand/proper nouns on the synthesis path so they are voiced
correctly (e.g. "Brigade" -> "Brigaid" = "bri-GAYD"). It runs after sentence
aggregation, so each call receives a whole sentence.
"""

import pytest

from api.services.pipecat.pronunciation_filter import PronunciationTextFilter


@pytest.mark.asyncio
async def test_replaces_whole_word_case_insensitive():
    f = PronunciationTextFilter({"Brigade": "Brigaid"})
    assert await f.filter("Welcome to Brigade Gateway.") == "Welcome to Brigaid Gateway."
    assert await f.filter("BRIGADE is great.") == "Brigaid is great."
    assert await f.filter("the Brigade Group's flagship") == "the Brigaid Group's flagship"


@pytest.mark.asyncio
async def test_leaves_non_matches_untouched():
    f = PronunciationTextFilter({"Brigade": "Brigaid"})
    assert await f.filter("No brand here.") == "No brand here."
    # Substrings are not matched (whole-word only).
    assert await f.filter("Brigadier general") == "Brigadier general"


@pytest.mark.asyncio
async def test_indic_native_script_replacement():
    f = PronunciationTextFilter({"Brigade": "బ్రిగేడ్"})
    assert await f.filter("Welcome to Brigade Gateway.") == "Welcome to బ్రిగేడ్ Gateway."


@pytest.mark.asyncio
async def test_empty_map_is_passthrough():
    f = PronunciationTextFilter({})
    assert await f.filter("Welcome to Brigade Gateway.") == "Welcome to Brigade Gateway."


@pytest.mark.asyncio
async def test_replacement_value_with_regex_chars_is_literal():
    # Replacement must be substituted literally (no backreference interpretation).
    f = PronunciationTextFilter({"Brigade": r"Bri\1gaid$"})
    assert await f.filter("a Brigade b") == r"a Bri\1gaid$ b"
