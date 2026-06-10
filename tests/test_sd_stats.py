import soccerdata as sd
import json

fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
stats = fbref.read_team_match_stats(stat_type="summary")
# get last match
print(stats.tail(2))
