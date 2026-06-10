import soccerdata as sd
fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
sched = fbref.read_schedule()
final_match = sched.iloc[-1]
print(final_match)
