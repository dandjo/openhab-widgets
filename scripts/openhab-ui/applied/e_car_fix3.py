#!/usr/bin/env python3
"""e_car_power also runs at startup and every minute: a plug that idles at a constant power sends no change.
Usage: e_car_fix3.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)


def migrate_rules(d):
    r = d["e_car_power"]["value"]
    items_ = [t["configuration"]["itemName"] for t in r["triggers"] if t["type"] == "core.ItemStateChangeTrigger"]
    triggers = [{"configuration": {"itemName": n}, "type": "core.ItemStateChangeTrigger"} for n in items_]
    triggers += [{"configuration": {"startlevel": 100}, "type": "core.SystemStartlevelTrigger"},
                 {"configuration": {"cronExpression": "0 * * * * ? *"}, "type": "timer.GenericCronTrigger"}]
    r["triggers"] = [{"id": str(i + 1), **t} for i, t in enumerate(triggers)]
    r["actions"][0]["id"] = str(len(triggers) + 1)
    print("triggers:", [t["type"].split(".")[-1] + ":" + str(list(t["configuration"].values())[0]) for t in r["triggers"]])
    return d


data, enc = m.detect(m.DB + "automation_rules.json")
text = m.encode(migrate_rules(data), *enc)
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
