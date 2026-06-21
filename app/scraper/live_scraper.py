"""
Phase 1: Live Match Scraper using Scrapling targeting ESPN JSON API
"""
import logging
import json
import asyncio
from typing import Optional
from dataclasses import dataclass
from app.scraper.wikipedia import ParsedEvent
import datetime

logger = logging.getLogger(__name__)

@dataclass
class ParsedLineup:
    player_name: str
    team_side: str
    position: Optional[str]
    jersey_number: Optional[int]
    is_starting: bool

@dataclass
class ParsedStat:
    team_side: str
    possession_pct: int
    shots: int
    shots_on_target: int
    corners: int
    fouls: int
    yellow_cards: int
    red_cards: int

@dataclass
class ParsedFifaMatch:
    home_score: int
    away_score: int
    clock: Optional[str]
    events: list[ParsedEvent]
    lineups: list[ParsedLineup]
    stats: list[ParsedStat]
    home_formation: Optional[str] = None
    away_formation: Optional[str] = None

import time
import datetime

async def scrape_live_match(home_team: str, away_team: str, match_date: Optional[datetime.datetime] = None) -> Optional[ParsedFifaMatch]:
    """
    Live match scraper polling ESPN's web API.
    """
    import urllib.request
    import json

    dates_to_try = []

    if match_date:
        dates_to_try.append(match_date.strftime("%Y%m%d"))
        dates_to_try.append((match_date - datetime.timedelta(days=1)).strftime("%Y%m%d"))
        dates_to_try.append((match_date + datetime.timedelta(days=1)).strftime("%Y%m%d"))
    else:
        now = datetime.datetime.utcnow()
        dates_to_try = [
            now.strftime("%Y%m%d"),
            (now - datetime.timedelta(days=1)).strftime("%Y%m%d"),
            (now - datetime.timedelta(days=2)).strftime("%Y%m%d"),
            (now - datetime.timedelta(days=3)).strftime("%Y%m%d"),
            (now - datetime.timedelta(days=4)).strftime("%Y%m%d"),
            (now - datetime.timedelta(days=5)).strftime("%Y%m%d"),
            (now + datetime.timedelta(days=1)).strftime("%Y%m%d"),
        ]
    home_score = 0
    away_score = 0

    game_id = None
    match_clock = None

    for test_date in dates_to_try:
        scoreboard_url = f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={test_date}"
        
        def fetch_espn():
            req = urllib.request.Request(scoreboard_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))

        try:
            data = await asyncio.to_thread(fetch_espn)
        except Exception as e:
            logger.error(f"Failed to fetch ESPN scoreboard for {test_date}: {e}")
            continue

        events = data.get("events", [])
        for event in events:
            comps = event.get("competitions", [])[0]["competitors"]
            team1 = comps[0]["team"]["name"]
            team2 = comps[1]["team"]["name"]
            
            # Match teams dynamically
            team1_names = [comps[0]["team"]["name"].lower(), comps[0]["team"].get("abbreviation", "").lower()]
            team2_names = [comps[1]["team"]["name"].lower(), comps[1]["team"].get("abbreviation", "").lower()]

            def matches_team(target: str, names: list) -> bool:
                target_lower = target.lower()
                return any(target_lower == n or target_lower in n for n in names if n)

            if (matches_team(home_team, team1_names) or matches_team(home_team, team2_names)) and \
               (matches_team(away_team, team1_names) or matches_team(away_team, team2_names)):
                game_id = event["id"]
                match_clock = event.get("status", {}).get("displayClock")
                short_detail = event.get("status", {}).get("type", {}).get("shortDetail")
                if short_detail in ["HT", "FT", "FT-Pens", "AET"]:
                    match_clock = short_detail
                    
                if matches_team(home_team, team1_names):
                    espn_home_idx = 0
                    home_score = int(comps[0].get("score", 0))
                    away_score = int(comps[1].get("score", 0))
                else:
                    espn_home_idx = 1
                    home_score = int(comps[1].get("score", 0))
                    away_score = int(comps[0].get("score", 0))
                    
                final_team1_names = team1_names
                final_team2_names = team2_names
                break
                
        if game_id:
            break
            
    if not game_id:
        logger.info(f"Could not resolve live game ID for {home_team} vs {away_team}")
        return None

    # 2. Fetch deep Match Summary (Timeline, Stats, Lineups)
    summary_url = f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={game_id}"
    def fetch_summary():
        req2 = urllib.request.Request(summary_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'})
        with urllib.request.urlopen(req2, timeout=5) as response:
            return json.loads(response.read().decode('utf-8'))

    try:
        summ_data = await asyncio.to_thread(fetch_summary)
    except Exception as e:
        logger.error(f"Failed to fetch ESPN match summary: {e}")
        return None

    parsed_events = []
    parsed_lineups = []
    parsed_stats = []

    # Parse Boxscore Stats
    boxscore = summ_data.get("boxscore", {})
    teams = boxscore.get("teams", [])
    for i, t in enumerate(teams):
        side = "home" if i == espn_home_idx else "away"
        stats_dict = {s["name"]: s["displayValue"] for s in t.get("statistics", [])}
        parsed_stats.append(ParsedStat(
            team_side=side,
            possession_pct=int(float(stats_dict.get("possessionPct", "0").replace("%", ""))),
            shots=int(stats_dict.get("totalShots", "0")),
            shots_on_target=int(stats_dict.get("shotsOnTarget", "0")),
            corners=int(stats_dict.get("wonCorners", "0")),
            fouls=int(stats_dict.get("foulsCommitted", "0")),
            yellow_cards=int(stats_dict.get("yellowCards", "0")),
            red_cards=int(stats_dict.get("redCards", "0")),
        ))

    # Parse Lineups and Formations
    rosters = summ_data.get("rosters", [])
    home_formation = None
    away_formation = None
    for i, r in enumerate(rosters):
        side = "home" if i == espn_home_idx else "away"
        if side == "home":
            home_formation = r.get("formation")
        else:
            away_formation = r.get("formation")
            
        for p in r.get("roster", []):
            parsed_lineups.append(ParsedLineup(
                player_name=p["athlete"]["displayName"],
                team_side=side,
                position=p.get("position", {}).get("name"),
                jersey_number=p.get("jersey"),
                is_starting=p.get("starter", False)
            ))

    # Parse Timeline Events (Goals, Cards)
    key_events = summ_data.get("keyEvents", [])
    for ev in key_events:
        etype = ev.get("type", {}).get("text", "").lower()
        
        is_penalty_goal = False
        if "penalty" in etype or "pen" in etype:
            is_penalty_goal = True

        if "goal" in etype or "scored" in etype or is_penalty_goal:
            mapped_type = "goal"
        elif "yellow" in etype:
            mapped_type = "card_yellow"
        elif "red" in etype:
            mapped_type = "card_red"
        elif "substitution" in etype:
            mapped_type = "substitution"
        else:
            continue
            
        ev_clock = ev.get("clock", {}).get("displayValue", "0").replace("'", "")
        minute = int(ev_clock.split("+")[0]) if "+" in ev_clock else (int(ev_clock) if ev_clock else 0)
        
        participant = ev.get("participants", [{}])[0].get("athlete", {}).get("displayName", "Unknown")
        ev_team = ev.get("team", {}).get("displayName", "")

        def matches_team(target: str, names: list) -> bool:
            target_lower = target.lower()
            return any(target_lower == n or target_lower in n for n in names if n)

        if matches_team(ev_team, final_team1_names):
            side = "home" if espn_home_idx == 0 else "away"
        elif matches_team(ev_team, final_team2_names):
            side = "home" if espn_home_idx == 1 else "away"
        else:
            side = "away" if ev_team.lower() == away_team.lower() else "home"
        
        import json
        extra_data = {}
        if "+" in ev_clock:
            extra_data["clockDisplay"] = ev_clock
            
        if mapped_type in ("substitution", "goal"):
            parts = ev.get("participants", [])
            if len(parts) > 1:
                extra_data["playerTwo"] = parts[1].get("athlete", {}).get("displayName", "Unknown")
        
        if is_penalty_goal:
            extra_data["isPenalty"] = True

        if ev.get("shootout"):
            extra_data["isShootoutPenalty"] = True
            
        extra = json.dumps(extra_data) if extra_data else None
        
        parsed_events.append(ParsedEvent(
            type=mapped_type,
            player_name=participant,
            team_side=side,
            minute=minute,
            extra_info=extra
        ))

        if mapped_type == "goal":
            parts = ev.get("participants", [])
            if len(parts) > 1:
                assister = parts[1].get("athlete", {}).get("displayName", "Unknown")
                parsed_events.append(ParsedEvent(
                    type="assist",
                    player_name=assister,
                    team_side=side,
                    minute=minute,
                    extra_info=extra
                ))

    logger.info(f"Successfully scraped live ESPN data for {home_team} vs {away_team}")
    return ParsedFifaMatch(
        home_score=home_score,
        away_score=away_score,
        clock=match_clock,
        events=parsed_events,
        lineups=parsed_lineups,
        stats=parsed_stats,
        home_formation=home_formation,
        away_formation=away_formation
    )
