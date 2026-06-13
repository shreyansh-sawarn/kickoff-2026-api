"""
Phase 1: Live Match Scraper using Scrapling targeting ESPN JSON API
"""
import logging
from typing import Optional
from dataclasses import dataclass
from app.scraper.wikipedia import ParsedEvent

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

async def scrape_live_match(home_team: str, away_team: str) -> Optional[ParsedFifaMatch]:
    """
    Live match scraper using Scrapling to poll ESPN's hidden JSON API.
    """
    try:
        from scrapling import Fetcher
    except ImportError:
        logger.error("Scrapling not installed.")
        return None

    fetcher = Fetcher(auto_match=False) # lightweight fetch without rendering
    
    # 1. Resolve Game ID from ESPN scoreboard for FIFA World Cup
    # We poll the current day (or specific dates) to find the match
    import datetime
    today = datetime.datetime.utcnow().strftime("%Y%m%d")
    scoreboard_url = f"http://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={today}"
    
    try:
        score_resp = fetcher.get(scoreboard_url)
        data = score_resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch ESPN scoreboard: {e}")
        return None

    game_id = None
    match_clock = None
    home_score = 0
    away_score = 0
    
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
                home_score = int(comps[0].get("score", 0))
                away_score = int(comps[1].get("score", 0))
            else:
                home_score = int(comps[1].get("score", 0))
                away_score = int(comps[0].get("score", 0))
            break
            
    if not game_id:
        logger.info(f"Could not resolve live game ID for {home_team} vs {away_team}")
        return None

    # 2. Fetch deep Match Summary (Timeline, Stats, Lineups)
    summary_url = f"http://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={game_id}"
    try:
        summ_resp = fetcher.get(summary_url)
        summ_data = summ_resp.json()
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
        side = "home" if i == 0 else "away"
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

    # Parse Lineups
    rosters = summ_data.get("rosters", [])
    for i, r in enumerate(rosters):
        side = "home" if i == 0 else "away"
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
        if "goal" in etype or "scored" in etype:
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
        side = "away" if ev_team.lower() == away_team.lower() else "home"
        
        import json
        extra_data = {}
        if "+" in ev_clock:
            extra_data["clockDisplay"] = ev_clock
            
        if mapped_type == "substitution":
            parts = ev.get("participants", [])
            if len(parts) > 1:
                extra_data["playerTwo"] = parts[1].get("athlete", {}).get("displayName", "Unknown")
        
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

    logger.info(f"Successfully scraped live ESPN data for {home_team} vs {away_team}")
    return ParsedFifaMatch(
        home_score=home_score,
        away_score=away_score,
        clock=match_clock,
        events=parsed_events,
        lineups=parsed_lineups,
        stats=parsed_stats
    )
