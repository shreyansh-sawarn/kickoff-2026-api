import soccerdata as sd
import json

fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)

# get a single match to test
try:
    events = fbref.read_events()
    for idx, row in events.head(5).iterrows():
        print("EVENT:", idx, dict(row))
        
    lineups = fbref.read_lineup()
    for idx, row in lineups.head(5).iterrows():
        print("LINEUP:", idx, dict(row))
except Exception as e:
    print("ERROR:", e)
