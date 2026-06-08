"""
Phase 2: FIFA Match Center Scraper (Mock for 2022 Data)

This module simulates scraping granular event data from the FIFA Match Center.
When the 2026 World Cup goes live, this mock will be replaced with actual HTTP calls.
"""
from typing import Optional
from dataclasses import dataclass
from app.scraper.wikipedia import ParsedEvent

@dataclass
class ParsedFifaMatch:
    home_score: int
    away_score: int
    events: list[ParsedEvent]

async def scrape_fifa_match(home_team: str, away_team: str) -> Optional[ParsedFifaMatch]:
    """
    Mock endpoint that returns hardcoded FIFA granular events for 2022 testing.
    We intentionally introduce a conflict here to test the system.conflict webhook!
    """
    if "QAT" in home_team and "ECU" in away_team:
        # Wikipedia says 0-2 (Qatar 0, Ecuador 2).
        # We'll mock FIFA saying 0-3 to trigger the conflict detector!
        return ParsedFifaMatch(
            home_score=0,
            away_score=3,
            events=[
                # Ecuador goals (mocking Wikipedia ones but adding assists)
                ParsedEvent(type="goal", player_name="Enner Valencia", team_side="away", minute=16, extra_info="penalty"),
                ParsedEvent(type="goal", player_name="Enner Valencia", team_side="away", minute=31, extra_info="assist by Ángelo Preciado"),
                ParsedEvent(type="assist", player_name="Ángelo Preciado", team_side="away", minute=31, extra_info=None),
                
                # Cards (missing from Wikipedia group stage!)
                ParsedEvent(type="yellow", player_name="Saad Al-Sheeb", team_side="home", minute=15, extra_info=None),
                ParsedEvent(type="yellow", player_name="Almoez Ali", team_side="home", minute=22, extra_info=None),
                ParsedEvent(type="yellow", player_name="Karim Boudiaf", team_side="home", minute=36, extra_info=None),
                ParsedEvent(type="yellow", player_name="Akram Afif", team_side="home", minute=78, extra_info=None),
                ParsedEvent(type="yellow", player_name="Moisés Caicedo", team_side="away", minute=29, extra_info=None),
                ParsedEvent(type="yellow", player_name="Jhegson Méndez", team_side="away", minute=56, extra_info=None),
            ]
        )
    return None
