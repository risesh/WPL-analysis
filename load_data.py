import json
import os

DATA_DIR= "wpl_json"


def load_all_matches():
    all_matches= []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            filepath=os.path.join(DATA_DIR, filename)
            # print(filepath)
            with open(filepath,"r") as f:
                data=json.load(f)
                match_id=filename.replace(".json","")
            all_matches.append((match_id,data))

    return all_matches

if __name__=="__main__":
    all_matches= load_all_matches()
    print(f"Loaded {len(all_matches)} matches from the directory: {DATA_DIR}")


