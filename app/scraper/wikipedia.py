"""
Wikipedia scraper — the core data pipeline.

Fetches Wikitext from the MediaWiki API and parses:
  - Group stage summary page  → match scores + standings
  - Individual match pages    → goal scorers, cards, minutes

MediaWiki API endpoint (no auth needed):
  GET https://en.wikipedia.org/w/api.php
      ?action=parse&page=<PAGE_TITLE>&prop=wikitext&format=json
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"

# WC2026 pages — use WC2022 equivalents for testing before tournament starts
WC2026_GROUP_STAGE_PAGE = "2026_FIFA_World_Cup"
WC2022_GROUP_STAGE_PAGE = "2022_FIFA_World_Cup_Group_A"  # for parser testing
WC2026_KNOCKOUT_PAGE = "2026_FIFA_World_Cup_knockout_stage"


# ---------------------------------------------------------------------------
# Data classes for parsed results
# ---------------------------------------------------------------------------


@dataclass
class ParsedMatch:
    """A match parsed from the group stage summary page."""

    wikipedia_title: str  # page title used to fetch individual match page
    home_team: str
    away_team: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: str = "scheduled"  # scheduled | live | finished
    group_name: Optional[str] = None
    stage: str = "group"
    kickoff_utc: Optional[datetime] = None
    venue: Optional[str] = None
    events: list["ParsedEvent"] = field(default_factory=list)


@dataclass
class ParsedEvent:
    """A match event (goal, card, sub) parsed from an individual match page."""

    type: str  # goal|own_goal|penalty|yellow|red|yellow_red|assist|sub
    player_name: Optional[str] = None
    team_side: Optional[str] = None  # "home" or "away"
    minute: Optional[int] = None
    extra_info: Optional[str] = None


@dataclass
class ParsedMatchDetail:
    """Full match detail from an individual Wikipedia match page."""

    home_team: str = ""
    away_team: str = ""
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    home_score_ht: Optional[int] = None
    away_score_ht: Optional[int] = None
    events: list[ParsedEvent] = field(default_factory=list)
    venue: Optional[str] = None
    date_str: Optional[str] = None


@dataclass
class ParsedStanding:
    """A row in a group standing table."""
    group_name: str
    position: int
    team_name: str
    team_code: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int


@dataclass
class ParsedStandingRow:
    """A row from the group standings wikitable."""

    group_name: str
    position: int
    team_name: str
    team_code: Optional[str]
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0
    points: int = 0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": settings.wikipedia_user_agent},
        timeout=30.0,
        follow_redirects=True,
    )


import urllib.request
import urllib.parse
import json
import asyncio

async def fetch_wikitext(page_title: str) -> Optional[str]:
    """
    Fetch raw Wikitext for a Wikipedia page via the MediaWiki parse API.
    Returns None on any failure.
    Uses urllib because Wikipedia WAF sometimes blocks httpx.
    """
    import random
    # Added randomized jitter sleep to mimic human browsing behavior
    await asyncio.sleep(random.uniform(1.5, 3.5))

    params = {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
    }
    
    url = f"{MEDIAWIKI_API}?{urllib.parse.urlencode(params)}"
    
    def _fetch():
        req = urllib.request.Request(url, headers={"User-Agent": settings.wikipedia_user_agent})
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
            
    max_retries = 3
    for attempt in range(max_retries):
        try:
            data = await asyncio.to_thread(_fetch)
            if "error" in data:
                logger.warning("MediaWiki API error for %s: %s", page_title, data["error"])
                return None
            return data["parse"]["wikitext"]
        except Exception as exc:
            if attempt == max_retries - 1:
                logger.error("Failed to fetch wikitext for %s after %d attempts: %s", page_title, max_retries, exc)
                return None
            
            # Exponential backoff + jitter (e.g. 2s, 4s + random jitter)
            sleep_time = (2 ** attempt) * 2 + random.uniform(1.0, 3.0)
            logger.warning("Fetch failed for %s (attempt %d/%d). Retrying in %.2fs: %s", page_title, attempt + 1, max_retries, sleep_time, exc)
            await asyncio.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Group stage page parser
# ---------------------------------------------------------------------------


def _safe_int(s: str) -> Optional[int]:
    """Parse an integer, returning None on failure."""
    s = s.strip()
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


async def fetch_standings_template(year: int) -> Optional[str]:
    """Fetch the central group tables template for a World Cup."""
    page = f"Template:{year}_FIFA_World_Cup_group_tables"
    return await fetch_wikitext(page)


def parse_standings_template(wikitext: str) -> list["ParsedStanding"]:
    """Parse the {{#invoke:Sports table}} from the central group tables template."""
    standings = []
    
    blocks = re.split(r'\|Group ([A-L])\s*=\s*\{\{#invoke:Sports table\|main', wikitext)
    for i in range(1, len(blocks), 2):
        group_letter = blocks[i]
        content = blocks[i+1]
        
        m_order = re.search(r'\|team_order\s*=\s*([A-Za-z0-9,\s]+)', content)
        if not m_order:
            continue
            
        team_codes = [x.strip() for x in m_order.group(1).split(',')]
        
        for pos, code in enumerate(team_codes, 1):
            def extract_stat(stat):
                m = re.search(fr'\|{stat}_{code}\s*=\s*(\d+)', content)
                return int(m.group(1)) if m else 0
            
            won = extract_stat('win')
            drawn = extract_stat('draw')
            lost = extract_stat('loss')
            gf = extract_stat('gf')
            ga = extract_stat('ga')
            
            standings.append(ParsedStanding(
                group_name=f'Group {group_letter}',
                position=pos,
                team_name=code,  # The pipeline will map this to the full name if needed
                team_code=code,
                played=won + drawn + lost,
                won=won,
                drawn=drawn,
                lost=lost,
                goals_for=gf,
                goals_against=ga,
                goal_diff=gf - ga,
                points=(won * 3) + drawn
            ))
            
    return standings


def parse_group_stage_wikitext(wikitext: str, year: int = 2026) -> list[ParsedMatch]:
    """
    Parse the group stage summary page wikitext.

    The page contains sections like:
        == Group A ==
        {{Fb cl header}}
        {{Fb cl team | ...}}
    and match rows using {{Football box}} templates inline within wikitables.

    We look for {{Football box ...}} templates and extract basic score info.
    """
    matches: list[ParsedMatch] = []
    current_group: Optional[str] = None

    # Regex to match == Group X == section headers
    group_header_re = re.compile(r"^==\s*(Group [A-L])\s*==", re.MULTILINE)

    # Regex to match {{Football box ... }} template blocks
    # We'll find the start then extract the full balanced block
    football_box_starts = list(re.finditer(r"\{\{(?:#invoke:)?(?:F|f)ootball box", wikitext, re.IGNORECASE))

    # Track which group each match belongs to by position in text
    group_positions: list[tuple[int, str]] = []
    for m in group_header_re.finditer(wikitext):
        group_positions.append((m.start(), m.group(1)))

    def get_group_at_pos(pos: int) -> Optional[str]:
        """Return the group name that was most recently defined before this position."""
        current = None
        for gpos, gname in group_positions:
            if gpos <= pos:
                current = gname
            else:
                break
        return current

    for start_match in football_box_starts:
        start = start_match.start()
        group = get_group_at_pos(start)

        # Extract the full template block by counting braces
        depth = 0
        end = start
        for i in range(start, min(start + 5000, len(wikitext))):
            if wikitext[i : i + 2] == "{{":
                depth += 1
            elif wikitext[i : i + 2] == "}}":
                depth -= 1
                if depth == 0:
                    end = i + 2
                    break

        template = wikitext[start:end]
        parsed = _parse_football_box_template(template, year=year)
        if parsed:
            parsed.group_name = group
            matches.append(parsed)

    logger.info("Parsed %d matches from group stage page", len(matches))
    return matches


def _parse_goals(text: str, team_side: str) -> list["ParsedEvent"]:
    """Parse goals1 or goals2 string into ParsedEvent objects."""
    events = []
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        m_goal = re.search(r'\{\{goal\|([^}]+)\}\}', line, re.IGNORECASE)
        if not m_goal:
            continue
            
        name_part = line[:m_goal.start()].strip('* ')
        m_name = re.search(r'\[\[([^|\]]+)(?:\|[^\]]+)?\]\]', name_part)
        if m_name:
            player_name = m_name.group(1).strip()
        else:
            player_name = name_part.strip()
            
        args = m_goal.group(1).split('|')
        current_minute_str = None
        current_event = None
        
        for arg in args:
            arg = arg.strip()
            if not arg:
                continue
                
            if arg[0].isdigit():
                current_minute_str = arg
                minute_int = 0
                try:
                    if '+' in arg:
                        p1, p2 = arg.split('+')
                        minute_int = int(p1) + int(p2)
                    else:
                        minute_int = int(arg)
                except ValueError:
                    pass
                    
                current_event = ParsedEvent(
                    type="goal",
                    player_name=player_name,
                    team_side=team_side,
                    minute=minute_int,
                    extra_info=""
                )
                events.append(current_event)
            else:
                if current_event:
                    current_event.extra_info = arg
                    
    return events


def _parse_football_box_template(template: str, year: int = 2026) -> Optional[ParsedMatch]:
    """
    Parse a {{Football box}} template into a ParsedMatch.

    Key fields:
      | home    = Team Name
      | away    = Team Name
      | score   = 2 – 1   (or TBD / – for upcoming)
      | date    = {{Start date|2026|6|11|...}}
      | stadium = Venue Name
      | report  = URL or wikilink
    """

    def extract_field(name: str) -> Optional[str]:
        # Match from `|name=` up to the next `\n|` or `\n}}`
        pattern = r"\|\s*" + re.escape(name) + r"\s*=\s*(.*?)(?=\n\s*\||\n\s*\}\}|\Z)"
        m = re.search(pattern, template, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
        return None

    home_raw = extract_field("home") or extract_field("team1") or ""
    away_raw = extract_field("away") or extract_field("team2") or ""
    
    home = _clean_wiki_markup(home_raw)
    away = _clean_wiki_markup(away_raw)

    if not home or not away:
        return None

    # Parse score — formats: "2 – 1", "TBD", "–", blank
    score_raw = extract_field("score") or ""
    home_score, away_score = _parse_score(score_raw)

    # Parse goals
    goals1_raw = extract_field("goals1") or ""
    goals2_raw = extract_field("goals2") or ""
    events = []
    if goals1_raw:
        events.extend(_parse_goals(goals1_raw, "home"))
    if goals2_raw:
        events.extend(_parse_goals(goals2_raw, "away"))

    # Date and Time
    date_str = extract_field("date") or ""
    time_str = extract_field("time") or ""
    kickoff = _parse_start_date_template(date_str, time_str)

    # Determine status
    if home_score is not None and away_score is not None:
        status = "finished"
    else:
        now = datetime.now(timezone.utc)
        if kickoff and kickoff <= now:
            status = "live"
        else:
            status = "scheduled"

    # Wikipedia title for individual match page
    # Pattern: Home_v_Away_(2026_FIFA_World_Cup)
    home_slug = home.replace(" ", "_")
    away_slug = away.replace(" ", "_")
    wiki_title = f"{home_slug}_v_{away_slug}_({year}_FIFA_World_Cup)"

    venue = _clean_wiki_markup(extract_field("stadium") or "")

    return ParsedMatch(
        wikipedia_title=wiki_title,
        home_team=home,
        away_team=away,
        home_score=home_score,
        away_score=away_score,
        status=status,
        kickoff_utc=kickoff,
        venue=venue or None,
        events=events
    )


def _parse_score(score_raw: str) -> tuple[Optional[int], Optional[int]]:
    """Parse score strings like '2 – 1', '0–0', 'TBD', '–' into (home, away)."""
    # If using {{score link|...|0–2}}, extract the score part.
    # The score could be followed by other arguments, e.g. {{score link|...|3–3|...}}
    m_score_link = re.search(r"\{\{score link[^}]*\|([0-9]+\s*[–\-]\s*[0-9]+)", score_raw, re.IGNORECASE)
    if m_score_link:
        score_raw = m_score_link.group(1)

    # Strip wiki markup
    score = re.sub(r"\[\[.*?\]\]|\{\{.*?\}\}|'''|''", "", score_raw).strip()
    # Match digits separated by en-dash, hyphen, or similar
    m = re.match(r"(\d+)\s*[–\-]\s*(\d+)", score)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _parse_start_date_template(date_s: str, time_s: str = "") -> Optional[datetime]:
    """
    Parse {{Start date|2026|6|11}} and time string like "12:00 p.m. [[UTC-05:00|UTC-5]]"
    Returns a timezone-aware datetime in UTC.
    """
    m = re.search(
        r"\{\{Start date\|(\d{4})\|(\d{1,2})\|(\d{1,2})(?:\|(\d{1,2})(?:\|(\d{1,2}))?)?",
        date_s,
        re.IGNORECASE,
    )
    if not m:
        return None
        
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hour = int(m.group(4)) if m.group(4) else 0
    minute = int(m.group(5)) if m.group(5) else 0

    if time_s:
        # Time string formats: "12:00 [[UTC-05:00|UTC-5]]" or "15:00 CST (UTC-5)"
        m_time = re.search(r"(\d{1,2}):(\d{2})", time_s)
        if m_time:
            hour = int(m_time.group(1))
            minute = int(m_time.group(2))
            # handle p.m. / a.m.
            if "p.m." in time_s.lower() or "pm" in time_s.lower():
                if hour < 12:
                    hour += 12
            if "a.m." in time_s.lower() or "am" in time_s.lower():
                if hour == 12:
                    hour = 0
            
            # handle UTC offset
            time_s_clean = time_s.replace("−", "-") # replace unicode minus
            m_utc = re.search(r"UTC\s*([+-]\d{1,2})(?::(\d{2}))?", time_s_clean, re.IGNORECASE)
            if m_utc:
                offset_hours = int(m_utc.group(1))
                offset_minutes = int(m_utc.group(2)) if m_utc.group(2) else 0
                if offset_hours < 0:
                    offset_minutes = -offset_minutes
                
                try:
                    dt_local = datetime(year, month, day, hour, minute)
                    offset = timedelta(hours=offset_hours, minutes=offset_minutes)
                    return (dt_local - offset).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def _clean_wiki_markup(text: str) -> str:
    """
    Remove basic wiki markup like links, flag icons, and HTML tags.
    """
    if not text:
        return ""

    # Extract team code from {{#invoke:flag|fb-rt|MEX}} or {{fb|QAT}}
    text = re.sub(r"\{\{#invoke:flagg?[^}]*\|([^|}]+)\}\}", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{fb(?:-rt)?\|([^|}]+).*?\}\}", r"\1", text, flags=re.IGNORECASE)

    # Remove {{flagicon|...}}
    text = re.sub(r"\{\{flagicon[^}]*\}\}", "", text, flags=re.IGNORECASE)
    
    # Strip basic HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    
    # Resolve simple [[Link|Text]] -> Text
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    
    # Remove references <ref>...</ref> or <ref ... />
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*/>", "", text)
    
    # Convert HTML entities
    text = text.replace("&nbsp;", " ")
    
    return text.strip()


# ---------------------------------------------------------------------------
# Individual match page parser
# ---------------------------------------------------------------------------


def parse_match_page_wikitext(wikitext: str) -> ParsedMatchDetail:
    """
    Parse an individual match page like:
      France_v_Morocco_(2022_FIFA_World_Cup)

    The page contains a {{Football box}} infobox with:
      | goals1 = [[Theo Hernandez]] {{goal|5}}\\n[[Randal Kolo Muani]] {{goal|78}}
      | goals2 = ...
      | red1 / red2 = cards
    """
    detail = ParsedMatchDetail()

    # Find the main Football box template
    fb_match = re.search(r"\{\{Football box", wikitext, re.IGNORECASE)
    if not fb_match:
        logger.debug("No Football box found in match page wikitext")
        return detail

    # Extract full template
    start = fb_match.start()
    depth = 0
    end = start
    for i in range(start, min(start + 20000, len(wikitext))):
        if wikitext[i : i + 2] == "{{":
            depth += 1
        elif wikitext[i : i + 2] == "}}":
            depth -= 1
            if depth == 0:
                end = i + 2
                break

    template = wikitext[start:end]

    def extract_field(name: str) -> Optional[str]:
        pattern = rf"\|\s*{re.escape(name)}\s*=\s*(.*?)(?=\n\s*\||\n\s*\}}|\Z)"
        m = re.search(pattern, template, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
        return None

    # Teams
    detail.home_team = _clean_wiki_markup(extract_field("home") or "")
    detail.away_team = _clean_wiki_markup(extract_field("away") or "")

    # Scores
    score_raw = extract_field("score") or ""
    detail.home_score, detail.away_score = _parse_score(score_raw)

    # Half-time scores (report field often has it, or use score1/score2 ht fields)
    ht_raw = extract_field("score1") or ""  # some templates use score1 for HT
    # Try dedicated HT fields first
    ht1 = extract_field("ht1") or extract_field("score1ht") or ""
    ht2 = extract_field("ht2") or extract_field("score2ht") or ""
    if ht1 and ht2:
        detail.home_score_ht = _safe_int(re.sub(r"\D", "", ht1))
        detail.away_score_ht = _safe_int(re.sub(r"\D", "", ht2))

    # Venue
    detail.venue = _clean_wiki_markup(extract_field("stadium") or "")

    # Goals (home team = goals1, away team = goals2)
    goals1_raw = extract_field("goals1") or ""
    goals2_raw = extract_field("goals2") or ""
    detail.events.extend(_parse_goal_events(goals1_raw, "home"))
    detail.events.extend(_parse_goal_events(goals2_raw, "away"))

    # Red cards
    red1_raw = extract_field("red1") or ""
    red2_raw = extract_field("red2") or ""
    detail.events.extend(_parse_card_events(red1_raw, "home", "red"))
    detail.events.extend(_parse_card_events(red2_raw, "away", "red"))

    # Yellow cards
    yellow1_raw = extract_field("yellow1") or ""
    yellow2_raw = extract_field("yellow2") or ""
    detail.events.extend(_parse_card_events(yellow1_raw, "home", "yellow"))
    detail.events.extend(_parse_card_events(yellow2_raw, "away", "yellow"))

    return detail


def _parse_goal_events(raw: str, team_side: str) -> list[ParsedEvent]:
    """
    Parse goal event strings from the goals1/goals2 field.

    Examples:
      [[Kylian Mbappé]] {{goal|12}}{{goal|23|pen}}
      [[Theo Hernandez]] {{goal|5}}\n[[Olivier Giroud]] {{goal|78}}
    """
    events: list[ParsedEvent] = []
    if not raw.strip():
        return events

    # Split by newline or {{goal}} — each player may have multiple goals
    # Pattern: find all [[Player]] + their associated {{goal|min|type?}} calls
    player_re = re.compile(r"\[\[([^\|\]]+)(?:\|([^\]]+))?\]\]")
    goal_re = re.compile(r"\{\{goal\|(\d+)(?:\|([^}]+))?\}\}", re.IGNORECASE)
    og_re = re.compile(r"\{\{(?:own goal|og)\|(\d+)[^}]*\}\}", re.IGNORECASE)
    pen_re = re.compile(r"\{\{(?:pen|penalty)[^}]*\}\}", re.IGNORECASE)

    # Find all own goals first
    for m in og_re.finditer(raw):
        minute = int(m.group(1))
        # Try to find adjacent player name
        before = raw[: m.start()]
        player_m = list(player_re.finditer(before))
        player = player_m[-1].group(2) or player_m[-1].group(1) if player_m else None
        events.append(
            ParsedEvent(
                type="own_goal",
                player_name=_clean_wiki_markup(player or ""),
                team_side=team_side,
                minute=minute,
            )
        )

    # Find all regular goal entries
    for m in goal_re.finditer(raw):
        minute = int(m.group(1))
        modifier = (m.group(2) or "").strip().lower()  # e.g. "pen", "header"

        # Look backward for the most recent player name
        before = raw[: m.start()]
        player_m = list(player_re.finditer(before))
        player = None
        if player_m:
            last = player_m[-1]
            player = last.group(2) or last.group(1)

        event_type = "goal"
        if "pen" in modifier:
            event_type = "penalty"

        events.append(
            ParsedEvent(
                type=event_type,
                player_name=_clean_wiki_markup(player or ""),
                team_side=team_side,
                minute=minute,
                extra_info=modifier if modifier and modifier != "pen" else None,
            )
        )

    return events


def _parse_card_events(raw: str, team_side: str, card_type: str) -> list[ParsedEvent]:
    """
    Parse card event strings like:
      [[Sofyan Amrabat]] {{yel|44}}
      [[Jawad El Yamiq]] {{red|73}}
    """
    events: list[ParsedEvent] = []
    if not raw.strip():
        return events

    card_re = re.compile(
        r"\[\[([^\|\]]+)(?:\|([^\]]+))?\]\][^\{]*\{\{(?:yel|red|yr|yellow|Yellow|Red)\|(\d+)[^}]*\}\}",
        re.IGNORECASE,
    )
    for m in card_re.finditer(raw):
        player = _clean_wiki_markup(m.group(2) or m.group(1))
        minute = int(m.group(3))
        events.append(
            ParsedEvent(
                type=card_type,
                player_name=player,
                team_side=team_side,
                minute=minute,
            )
        )

    return events

def parse_knockout_stage_wikitext(wikitext: str, year: int = 2026, default_stage: str = "knockout") -> list[ParsedMatch]:
    matches: list[ParsedMatch] = []
    
    # Find all level 2 section headers: \n== Header ==\n
    headers = []
    for m in re.finditer(r"\n==\s*([^=]+?)\s*==\s*\n", wikitext):
        headers.append((m.start(), m.group(1).strip()))
        
    football_box_starts = list(re.finditer(r"\{\{(?:#invoke:)?(?:F|f)ootball box", wikitext, re.IGNORECASE))
    print(f"DEBUG: Found {len(football_box_starts)} football box starts")
    
    for start_match in football_box_starts:
        start = start_match.start()
        depth = 0
        end = start
        for i in range(start, min(start + 5000, len(wikitext))):
            if wikitext[i : i + 2] == "{{":
                depth += 1
            elif wikitext[i : i + 2] == "}}":
                depth -= 1
                if depth == 0:
                    end = i + 2
                    break
                    
        block = wikitext[start:end]
        match = _parse_football_box_template(block, year)
        if match:
            # Find the last level 2 header before this template
            current_header = None
            for h_pos, h_text in headers:
                if h_pos < start:
                    current_header = h_text
                else:
                    break
            
            stage = default_stage
            if current_header:
                h = current_header.lower()
                if "round of 32" in h:
                    stage = "r32"
                elif "round of 16" in h:
                    stage = "r16"
                elif "quarter" in h:
                    stage = "qf"
                elif "semi" in h:
                    stage = "sf"
                elif "third place" in h or "final" in h:
                    stage = "final"
                    
            match.stage = stage
            match.group_name = None
            matches.append(match)
        else:
            print("DEBUG: _parse_football_box_template returned None for block")
            
    print(f"DEBUG: returning {len(matches)} matches")
    return matches


# ---------------------------------------------------------------------------
# High-level scrape functions called by the scheduler
# ---------------------------------------------------------------------------


async def scrape_group_stage() -> dict:
    """
    Scrape the group stage summary page and return parsed matches + standings.
    Returns a dict with keys: 'matches', 'error'.
    """
    start = time.monotonic()
    all_matches = []
    
    pages = [
        "2026_FIFA_World_Cup_Group_A", "2026_FIFA_World_Cup_Group_B",
        "2026_FIFA_World_Cup_Group_C", "2026_FIFA_World_Cup_Group_D",
        "2026_FIFA_World_Cup_Group_E", "2026_FIFA_World_Cup_Group_F",
        "2026_FIFA_World_Cup_Group_G", "2026_FIFA_World_Cup_Group_H",
        "2026_FIFA_World_Cup_Group_I", "2026_FIFA_World_Cup_Group_J",
        "2026_FIFA_World_Cup_Group_K", "2026_FIFA_World_Cup_Group_L"
    ]
    year = 2026

    for page in pages:
        wikitext = await fetch_wikitext(page)
        if not wikitext:
            logger.warning(f"Failed to fetch wikitext for {page}")
            continue

        matches = parse_group_stage_wikitext(wikitext, year=year)
        
        # Fallback for group name if testing a single group page
        group_match = re.search(r"Group_([A-L])", page)
        if group_match:
            fallback_group = f"Group {group_match.group(1)}"
            for m in matches:
                if m.group_name is None:
                    m.group_name = fallback_group
                    
        all_matches.extend(matches)
        await asyncio.sleep(0.5)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "matches": all_matches,
        "elapsed_ms": elapsed_ms,
        "error": None
    }


async def scrape_match_detail(wikipedia_title: str) -> dict:
    """
    Scrape an individual match page and return parsed detail.
    Returns a dict with keys: 'detail', 'error'.
    """
    start = time.monotonic()
    wikitext = await fetch_wikitext(wikipedia_title)
    if not wikitext:
        return {"detail": None, "error": f"Failed to fetch {wikipedia_title}"}

    detail = parse_match_page_wikitext(wikitext)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "Scraped match detail %s: %d events in %dms",
        wikipedia_title,
        len(detail.events),
        elapsed_ms,
    )
    return {"detail": detail, "error": None, "elapsed_ms": elapsed_ms}
