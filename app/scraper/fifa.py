"""
Phase 2: FIFA Match Center Scraper (Mock for 2022 Data)

This module simulates scraping granular event data from the FIFA Match Center.
When the 2026 World Cup goes live, this mock will be replaced with actual HTTP calls.
"""
from typing import Optional
from dataclasses import dataclass
from app.scraper.wikipedia import ParsedEvent

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

@dataclass
class ParsedFifaMatch:
    home_score: int
    away_score: int
    events: list[ParsedEvent]
    lineups: list[ParsedLineup]
    stats: list[ParsedStat]

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
            ],
            lineups=[
                # Qatar Mock Lineup (11 Starters)
                ParsedLineup(player_name="Saad Al-Sheeb", team_side="home", position="GK", jersey_number=1, is_starting=True),
                ParsedLineup(player_name="Pedro Miguel", team_side="home", position="DEF", jersey_number=2, is_starting=True),
                ParsedLineup(player_name="Abdelkarim Hassan", team_side="home", position="DEF", jersey_number=3, is_starting=True),
                ParsedLineup(player_name="Homam Ahmed", team_side="home", position="DEF", jersey_number=14, is_starting=True),
                ParsedLineup(player_name="Bassam Al-Rawi", team_side="home", position="DEF", jersey_number=15, is_starting=True),
                ParsedLineup(player_name="Boualem Khoukhi", team_side="home", position="DEF", jersey_number=16, is_starting=True),
                ParsedLineup(player_name="Abdulaziz Hatem", team_side="home", position="MID", jersey_number=6, is_starting=True),
                ParsedLineup(player_name="Karim Boudiaf", team_side="home", position="MID", jersey_number=12, is_starting=True),
                ParsedLineup(player_name="Hassan Al-Haydos", team_side="home", position="FWD", jersey_number=10, is_starting=True),
                ParsedLineup(player_name="Akram Afif", team_side="home", position="FWD", jersey_number=11, is_starting=True),
                ParsedLineup(player_name="Almoez Ali", team_side="home", position="FWD", jersey_number=19, is_starting=True),
                
                # Ecuador Mock Lineup (11 Starters)
                ParsedLineup(player_name="Hernán Galíndez", team_side="away", position="GK", jersey_number=1, is_starting=True),
                ParsedLineup(player_name="Félix Torres", team_side="away", position="DEF", jersey_number=2, is_starting=True),
                ParsedLineup(player_name="Piero Hincapié", team_side="away", position="DEF", jersey_number=3, is_starting=True),
                ParsedLineup(player_name="Pervis Estupiñán", team_side="away", position="DEF", jersey_number=7, is_starting=True),
                ParsedLineup(player_name="Ángelo Preciado", team_side="away", position="DEF", jersey_number=17, is_starting=True),
                ParsedLineup(player_name="Romario Ibarra", team_side="away", position="MID", jersey_number=10, is_starting=True),
                ParsedLineup(player_name="Gonzalo Plata", team_side="away", position="MID", jersey_number=19, is_starting=True),
                ParsedLineup(player_name="Jhegson Méndez", team_side="away", position="MID", jersey_number=20, is_starting=True),
                ParsedLineup(player_name="Moisés Caicedo", team_side="away", position="MID", jersey_number=23, is_starting=True),
                ParsedLineup(player_name="Michael Estrada", team_side="away", position="FWD", jersey_number=11, is_starting=True),
                ParsedLineup(player_name="Enner Valencia", team_side="away", position="FWD", jersey_number=13, is_starting=True),
            ],
            stats=[
                ParsedStat(team_side="home", possession_pct=47, shots=5, shots_on_target=0, corners=1, fouls=15),
                ParsedStat(team_side="away", possession_pct=53, shots=6, shots_on_target=3, corners=3, fouls=15),
            ]
        )
    return None
