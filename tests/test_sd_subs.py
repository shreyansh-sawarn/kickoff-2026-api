import soccerdata as sd

fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
sched = fbref.read_schedule()
final_match = sched['game_id'].iloc[-1]

try:
    events = fbref.read_events(match_id=final_match)
    subs = events[events['event_type'] == 'Substitute_in']
    if subs.empty:
        subs = events[events['event_type'] == 'substitute_in']
    if subs.empty:
        print("UNIQUE EVENT TYPES:", events['event_type'].unique())
        subs = events[events['event_type'].str.contains('sub', case=False, na=False)]
        
    for idx, row in subs.head(3).iterrows():
        print("SUB:", dict(row))
except Exception as e:
    print("ERROR:", e)
