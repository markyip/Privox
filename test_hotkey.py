import json
import os

app_data = os.path.expanduser("~/Library/Application Support/Privox")
prefs = os.path.join(app_data, ".user_prefs.json")

if os.path.exists(prefs):
    with open(prefs, "r") as f:
        data = json.load(f)
        print("Current Hotkey Config:", data.get("hotkey"))
else:
    print("Prefs not found.")
