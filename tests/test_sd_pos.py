import soccerdata as sd
fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
sched = fbref.read_schedule()
final_match = sched['game_id'].iloc[-1]
lineups = fbref.read_lineup(match_id=final_match)
print("POSITIONS:", lineups['position'].unique())
