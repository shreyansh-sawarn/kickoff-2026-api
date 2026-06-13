"""
Tests for the Wikipedia scraper parser — tested against WC2022 pages.
These hit the real MediaWiki API (no mocking needed for parser dev).
"""
import pytest

from app.scraper.wikipedia import (
    _parse_football_box_template,
    _parse_goal_events,
    _parse_score,
    fetch_wikitext,
    parse_group_stage_wikitext,
    parse_match_page_wikitext,
)


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------


def test_parse_score_normal():
    assert _parse_score("2 – 1") == (2, 1)


def test_parse_score_zero():
    assert _parse_score("0 – 0") == (0, 0)


def test_parse_score_hyphen():
    assert _parse_score("3-2") == (3, 2)


def test_parse_score_tbd():
    assert _parse_score("TBD") == (None, None)


def test_parse_score_empty():
    assert _parse_score("") == (None, None)


def test_parse_goal_events_basic():
    raw = "[[Kylian Mbappé]] {{goal|12}}{{goal|79|pen}}"
    events = _parse_goal_events(raw, "home")
    assert len(events) >= 1
    goal = events[0]
    assert goal.minute == 12
    assert goal.type == "goal"


def test_parse_goal_penalty():
    raw = "[[Kylian Mbappé]] {{goal|79|pen}}"
    events = _parse_goal_events(raw, "home")
    pen_events = [e for e in events if e.type == "penalty"]
    assert len(pen_events) >= 1
    assert pen_events[0].minute == 79


# ---------------------------------------------------------------------------
# Integration tests (real network — test against WC2022 pages)
# ---------------------------------------------------------------------------





@pytest.mark.asyncio
async def test_parse_group_stage_2022():
    """Parse the WC2022 group stage page — should yield multiple matches."""
    from app.scraper.wikipedia import WC2022_GROUP_STAGE_PAGE, fetch_wikitext

    wikitext = await fetch_wikitext(WC2022_GROUP_STAGE_PAGE)
    if wikitext is None:
        pytest.skip("Could not fetch WC2022 group stage page")

    matches = parse_group_stage_wikitext(wikitext)
    # WC2022 had 48 group stage matches
    assert len(matches) > 0, "Should parse at least some matches"
