#!/usr/bin/env python3
"""Replace the washing_machine_2_finished detection: finished after a real run, reset when the machine is switched off.

Usage: wm2_rule.py check|apply   (run as root with openHAB stopped for apply)
"""
import sys

src = open("/tmp/awattar_migrate.py").read().replace("\nmain()\n", "\n")
m = type(sys)("m")
exec(compile(src, "awattar_migrate", "exec"), m.__dict__)

UID = "washing_machine_2_finished"
SCRIPT = """const finished_item = items.getItem('washing_machine_2_finished');
const power_item = items.getItem('washing_machine_2_power');
const now = time.ZonedDateTime.now();
const power = power_item.numericState;
const average = power_item.persistence.averageSince(now.minusMinutes(5));
const peak = power_item.persistence.maximumSince(now.minusMinutes(15));

// finished: a program ran within the last 15 minutes, the machine has settled at its display standby
// (3-4.5 W) for five minutes and is still switched on
if (finished_item.state === 'OFF' && power !== null && power >= 1
    && average !== null && average.numericState <= 5 && peak !== null && peak.numericState >= 50) {
  finished_item.postUpdate('ON');
  actions.NotificationAction.sendBroadcastNotification('Waschmaschine 2 ist fertig!');
}

// emptied: the machine is switched off to unload it (below 1 W), or a new program starts
if (finished_item.state !== 'OFF' && power !== null && (power < 1 || power >= 50)) {
  finished_item.postUpdate('OFF');
}"""
DESCRIPTION = ("Sets washing_machine_2_finished after a program (peak of 50 W within 15 minutes, 5-minute average at "
               "most 5 W, still switched on) and clears it when the machine is switched off to unload or starts again.")


def migrate_rules(d):
    rule = d[UID]["value"]
    actions = rule["actions"]
    assert len(actions) == 1 and "washing_machine_2_power" in actions[0]["configuration"]["script"], actions
    actions[0]["configuration"]["script"] = SCRIPT
    rule["description"] = DESCRIPTION
    return d


data, enc = m.detect(m.DB + "automation_rules.json")
text = m.encode(migrate_rules(data), *enc)
print("automation_rules.json: encoder", enc, "ok")
if sys.argv[1] == "apply":
    open(m.DB + "automation_rules.json", "w", encoding="utf-8").write(text)
    print("written")
