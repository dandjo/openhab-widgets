#!/usr/bin/env python3
# Measures the air conditioner's circuit in standby and in fan mode (indoor unit only) for every fan
# stage with and without streamer. Samples the Shelly EM directly every 2 s, drives the unit through
# openHAB item commands, restores the original settings at the end. Run on homepi with nothing else on
# the circuit; writes samples.csv and phases.log to /tmp/ac-baseline. Environment: PHASE_S (seconds per
# phase, 600), STAGES (Q,1,2,3,4,5), STREAMER_ORDER (ON,OFF), PRE (1: standby first), POST_STREAMER (OFF),
# SUFFIX (appended to the phase names), ORIGINAL (JSON of settings to restore instead of the current ones).
# Used on 2026-09-27 for the fan curve in air_conditioning_circuit_power (see e_car_fan_rule.js).
import csv
import json
import os
import threading
import time
import urllib.request

OH = 'http://127.0.0.1:8080/rest/items/'
EM = 'http://10.3.0.12/cm?cmnd=Status%2010'
OUT = '/tmp/ac-baseline'
PHASE_S = int(os.environ.get('PHASE_S', '600'))
STAGES = [x for x in os.environ.get('STAGES', 'Q,1,2,3,4,5').split(',') if x]
PRE = os.environ.get('PRE', '1') == '1'
POST_STREAMER = os.environ.get('POST_STREAMER', 'OFF')
STREAMER_ORDER = os.environ.get('STREAMER_ORDER', 'ON,OFF').split(',')
SUFFIX = os.environ.get('SUFFIX', '')
F = 'faikout_perfera_'

phase = {'label': 'init', 'start': time.time()}
stop = threading.Event()


def log(msg):
    line = time.strftime('%Y-%m-%dT%H:%M:%S') + ' ' + msg
    with open(OUT + '/phases.log', 'a') as f:
        f.write(line + '\n')
    print(line, flush=True)


def get_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def faikin():
    g = get_json(OH + F[:-1] + '?recursive=true')
    return {m['name'][len(F):]: m['state'] for m in g.get('members', [])}


def state(item):
    with urllib.request.urlopen(OH + item + '/state', timeout=3) as r:
        return r.read().decode()


def command(item, value):
    req = urllib.request.Request(OH + item, data=value.encode(), method='POST',
                                 headers={'Content-Type': 'text/plain'})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def ensure(item, value, timeout=90):
    if state(item) == value:
        return True
    t0 = time.time()
    last = 0
    while time.time() - t0 < timeout:
        if time.time() - last >= 20:
            command(item, value)
            log(f'command {item} {value}')
            last = time.time()
        time.sleep(1)
        if state(item) == value:
            log(f'confirmed {item} {value} after {time.time() - t0:.0f} s')
            return True
    log(f'FAILED {item} {value}, state {state(item)}')
    return False


def sampler():
    fields = ['t', 'iso', 'phase', 'phase_t', 'power', 'apparent', 'reactive', 'factor', 'voltage', 'current',
              'switch', 'mode', 'fan', 'streamer_mode', 'fan_speed', 'power_faikin', 'compressor_frequency',
              'swingh', 'swingv', 'car']
    with open(OUT + '/samples.csv', 'a', newline='') as f:
        w = csv.writer(f)
        if f.tell() == 0:
            w.writerow(fields)
        while not stop.is_set():
            t = time.time()
            try:
                e = get_json(EM)['StatusSNS']['ENERGY']
                k = faikin()
                car = state('e_car_power')
                w.writerow([f'{t:.1f}', time.strftime('%H:%M:%S', time.localtime(t)), phase['label'],
                            f'{t - phase["start"]:.0f}', e['Power'][0], e['ApparentPower'][0],
                            e['ReactivePower'][0], e['Factor'][0], e['Voltage'], e['Current'][0],
                            k.get('switch'), k.get('mode'), k.get('fan'), k.get('streamer_mode'),
                            k.get('fan_speed'), k.get('power'), k.get('compressor_frequency'),
                            k.get('swingh'), k.get('swingv'), car])
                f.flush()
            except Exception as ex:  # a missed sample is fine, a dead sampler is not
                log(f'sample error {ex!r}')
            stop.wait(max(0, 2 - (time.time() - t)))


def run(label):
    phase['label'] = label
    phase['start'] = time.time()
    log(f'phase {label} start')
    time.sleep(PHASE_S)
    log(f'phase {label} end')


os.makedirs(OUT, exist_ok=True)
original = {**faikin(), **json.loads(os.environ.get('ORIGINAL', '{}'))}
log('original ' + json.dumps({k: original.get(k) for k in ('switch', 'mode', 'fan', 'streamer_mode', 'swingh', 'swingv')}))
threading.Thread(target=sampler, daemon=True).start()
try:
    if PRE:
        ensure(F + 'switch', 'OFF')
        run('standby_streamer_' + original.get('streamer_mode', 'NULL'))
    ensure(F + 'mode', 'F')
    for stage in STAGES:
        for streamer in STREAMER_ORDER:
            ensure(F + 'fan', stage)
            ensure(F + 'streamer_mode', streamer)
            ensure(F + 'switch', 'ON')
            ensure(F + 'mode', 'F')
            run(f'fan_{stage}_streamer_{streamer}{SUFFIX}')
    ensure(F + 'switch', 'OFF')
    ensure(F + 'streamer_mode', POST_STREAMER)
    run(f'standby_streamer_{POST_STREAMER}_after')
finally:
    phase['label'] = 'restore'
    ensure(F + 'switch', 'OFF')
    for key in ('mode', 'fan', 'streamer_mode'):
        if original.get(key) not in (None, 'NULL', 'UNDEF'):
            ensure(F + key, original[key])
    time.sleep(4)
    stop.set()
    log('done')
