#!/usr/bin/env python3
"""e_car_energy: the total becomes the total stored before midnight plus today, recomputed on every run.
Usage: e_car_fix.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys
src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)
OLD = """  // the total carries on from its stored value, across midnight and restarts
  const stored = (item) => {
    if (item.numericState !== null) {
      return item.numericState;
    }
    const persisted = item.persistence.persistedState(time.toZDT(), 'influxdb');
    return persisted !== null && persisted.numericState !== null ? persisted.numericState : 0;
  };
  const todayItem = items.getItem('e_car_energy_today');
  const totalItem = items.getItem('e_car_energy_total');
  const lastUpdate = todayItem.persistence.lastUpdate();
  const sameDay = lastUpdate !== null && !lastUpdate.isBefore(midnight);
  const base = stored(totalItem) - (sameDay ? stored(todayItem) : 0);
  persistEnergy('e_car_energy_today', today, 'kWh');"""
NEW = """  // the total is the last total stored before midnight plus today, the same on every run and after restarts
  const totalItem = items.getItem('e_car_energy_total');
  const atMidnight = totalItem.persistence.persistedState(midnight, 'influxdb');
  const base = atMidnight !== null && atMidnight.numericState !== null ? atMidnight.numericState : 0;
  persistEnergy('e_car_energy_today', today, 'kWh');"""


def migrate_rules(d):
    action = d["e_car_energy"]["value"]["actions"][0]["configuration"]
    assert action["script"].count(OLD) == 1
    action["script"] = action["script"].replace(OLD, NEW)
    return d


data, enc = m.detect(m.DB + "automation_rules.json")
text = m.encode(migrate_rules(data), *enc)
print("automation_rules.json encoder", enc, "ok")
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
