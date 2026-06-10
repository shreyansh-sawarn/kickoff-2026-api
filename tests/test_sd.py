import soccerdata as sd
import json

fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
df = fbref.read_player_season_stats(stat_type="standard")

# Print first row
for idx, row in df.head(1).iterrows():
    print("INDEX:", idx)
    for col, val in row.items():
        print(f"COL {col}: {val}")
