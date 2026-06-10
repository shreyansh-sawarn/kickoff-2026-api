import soccerdata as sd
fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
sched = fbref.read_schedule()
final_match = sched['game_id'].iloc[-1]
events = fbref.read_events(match_id=final_match)
print(events[events['event_type'].str.contains('penalty', case=False, na=False)][['team', 'minute', 'player1', 'event_type']])
