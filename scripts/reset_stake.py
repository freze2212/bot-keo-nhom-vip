import glob
import json

for p in glob.glob("logs/daily_state_*.json"):
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    d["stake_level"] = 0
    d["loss_streak"] = 0
    d["skip_next_round"] = False
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(p, "-> stake 100K")
