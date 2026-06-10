import soccerdata as sd
import json

fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)

# get schedule
sched = fbref.read_schedule()
# print all match_ids
final_match = sched['game_id'].iloc[-1]
print("Using match ID:", final_match)

try:
    events = fbref.read_events(match_id=final_match)
    print("EVENTS INDEX:", events.index.names)
    for idx, row in events.head(1).iterrows():
        print("EVENTS:", idx, dict(row))
        
    lineups = fbref.read_lineup(match_id=final_match)
    print("LINEUPS INDEX:", lineups.index.names)
    for idx, row in lineups.head(1).iterrows():
        print("LINEUPS:", idx, dict(row))
except Exception as e:
    print("ERROR:", e)
