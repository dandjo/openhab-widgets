#!/usr/bin/env python3
"""Items and rule for 15-minute temperature means on a shared grid (aligned chart tooltips).

Usage: temp15.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys

src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

ITEMS = [("temperature_indoor_15min", "Temperature Indoor 15 min", "espaltherma_indoor_ambient_temp"),
         ("temperature_outdoor_15min", "Temperature Outdoor 15 min", "espaltherma_ext_ambient_temp")]
RULE_UID = "temperature_15min"
RULE_SCRIPT = """// 15-minute means of both sensors on the same timestamps, so charts can show them together in one tooltip
const slot = time.toZDT().withSecond(0).withNano(0);
const pairs = [
""" + "".join(f"  ['{src_}', '{item}'],\n" for item, _, src_ in ITEMS) + """];
pairs.forEach(([source, target]) => {
  const average = items.getItem(source).persistence.averageSince(slot.minusMinutes(15), 'influxdb');
  if (average !== null && average.numericState !== null) {
    const state = Quantity(average.numericState.toFixed(1) + ' °C');
    items.getItem(target).postUpdate(state);
    items.getItem(target).persistence.persist(slot, state, 'influxdb');
  }
});"""


def migrate_items(d):
    for item, lbl, _ in ITEMS:
        assert item not in d, item
        d = m.insert(d, item, {"class": "org.openhab.core.items.ManagedItemProvider$PersistedItem",
                               "value": {"groupNames": [], "itemType": "Number:Temperature", "tags": [],
                                         "label": lbl, "category": "temperature"}})
    return d


def migrate_metadata(d):
    for item, *_ in ITEMS:
        for ns, value, cfg in (("unit", "°C", {}), ("stateDescription", " ", {"pattern": "%.1f %unit%"})):
            key = f"{ns}:{item}"
            assert key not in d, key
            d = m.insert(d, key, {"class": "org.openhab.core.items.Metadata",
                                  "value": {"key": {"segments": [ns, item], "uid": key}, "value": value,
                                            "configuration": dict(cfg)}})
    return d


def migrate_rules(d):
    assert RULE_UID not in d
    return m.insert(d, RULE_UID, {
        "class": "org.openhab.core.automation.dto.RuleDTO",
        "value": {
            "triggers": [{"id": "1", "configuration": {"cronExpression": "0 0/15 * * * ? *"},
                          "type": "timer.GenericCronTrigger"}],
            "conditions": [],
            "actions": [{"inputs": {}, "id": "2",
                         "configuration": {"script": RULE_SCRIPT, "type": "application/javascript"},
                         "type": "script.ScriptAction"}],
            "configuration": {}, "configDescriptions": [], "templateState": "no-template", "uid": RULE_UID,
            "name": "Temperature 15 min", "tags": [], "visibility": "VISIBLE",
            "description": "Writes 15-minute means of the heat pump's indoor and outdoor sensors on shared timestamps for the dashboard chart.",
        },
    })


FILES = {"org.openhab.core.items.Item.json": migrate_items,
         "org.openhab.core.items.Metadata.json": migrate_metadata,
         "automation_rules.json": migrate_rules}
results = {}
for name, fn in FILES.items():
    data, enc = m.detect(m.DB + name)
    results[name] = m.encode(fn(data), *enc)
    print(name, "encoder", enc, "ok")
if sys.argv[1] == "apply":
    for name, text in results.items():
        open(m.DB + name, "w", encoding="utf-8").write(text)
    print("written")
