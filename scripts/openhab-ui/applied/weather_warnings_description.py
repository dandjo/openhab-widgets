#!/usr/bin/env python3
"""Give the rule weather_warnings its description from i18n/de_labels.py, which names what the rule writes: the highest
level of the warnings in effect now or within 24 hours, that warning as a short text, every warning not ended yet as
JSON, and the broadcast from orange on.
Usage: weather_warnings_description.py check|apply   (with openHAB stopped for apply)"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "awattar_migrate.py")).read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
sys.path.insert(0, os.path.join(HERE, "..", "i18n"))
from de_labels import RULE_DESCRIPTIONS  # noqa: E402
NAME = "automation_rules.json"
data, enc = m.detect(m.DB + NAME)
rule = data["weather_warnings"]["value"]
print("old:", rule["description"])
rule["description"] = RULE_DESCRIPTIONS["weather_warnings"]
print("new:", rule["description"])
text = m.encode(data, *enc)
print(f"{NAME}: encoder html={enc[0]} newline={enc[1]} ok")
if sys.argv[1] == "apply":
    open(m.DB + NAME, "w", encoding="utf-8").write(text)
    print("written")
