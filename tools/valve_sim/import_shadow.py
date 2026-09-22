"""Import an allowlisted shadow configuration into the local, isolated DEMO Pi.

Input contains names/settings/programs only, never production special-station
URLs. Run after installing DEMO_VALVE_SIM_ONLY and taking a data backup.
Does not start watering or convert legacy programs to soil-water programs.
"""
import argparse
import json
from pathlib import Path
from .exercise import OPENER, check
from urllib.parse import urlencode


def get(path, parameters=None, port=80):
    url = f"http://127.0.0.1:{port}/{path}"
    if parameters:
        url += "?" + urlencode(parameters)
    # Weather refreshes can temporarily block the firmware request loop.
    with OPENER.open(url, timeout=45) as response:
        return json.load(response)


def apply(data):
    check(data.get('schema') == 1, 'Unsupported import schema')
    names = data['names']
    check(len(names) in range(8, 201, 8), 'Expected complete station boards')
    check(all(isinstance(n, str) and 0 < len(n.encode()) < 32 for n in names), 'Invalid station names')
    check(len(data['disabled']) == len(names)//8, 'Disabled board mask mismatch')
    check(len(data['groups']) == len(names), 'Station group count mismatch')
    for p in data['programs']:
        check(len(p) == 7 and len(p[3]) == 4 and len(p[4]) == len(names), 'Invalid program dimensions')
    options = get('jo')
    state = get('jc')
    check(options['hwv'] == 255, 'Requires DEMO controller')
    check(options['smode'] == 1 and state['nq'] == 0 and not any(state['sbits']), 'Requires paused soil mode and idle controller')
    check(get('jp')['nprogs'] == 0, 'Existing standard programs require separate migration; will not overwrite')
    sim = get('status', port=18080)
    check(sim['service'] == 'opensprinkler-valve-simulator', 'Wrong simulator')
    check(all(f'zone{i+1}' in sim['states'] for i in range(len(names))), 'Receiver needs more simulated zones')
    check(not any(sim['states'].values()), 'Simulator must be idle')

    def write(path, **params):
        check(get(path, params).get('result') == 1, 'Local configuration write rejected: '+path)

    write('co', ext=len(names)//8-1, tz=data['timezone_offset'], sdt=data['station_delay'],
          loc=data['location'], smode=1, mas=0, mas2=0, mas3=0, mas4=0, sar=0,
          dname='OpenSprinkler Dev - SIMULATED')
    # Disable every station while installing simulator routes.
    write('cs', **{f'd{i}':255 for i in range(len(names)//8)},
          **{f'p{i}':255 for i in range(len(names)//8)})
    targets = {}
    for sid, name in enumerate(names):
        target = dict(st=4, sd=f'127.0.0.1,18080,sim/zone{sid+1}/on,sim/zone{sid+1}/off')
        write('cs', sid=sid, **target, **{f's{sid}':name})
        targets[str(sid)] = target
    check(get('je') == targets, 'Simulator route verification failed; stations remain disabled')
    attributes = {f'g{i}':g for i,g in enumerate(data['groups'])}
    for i, mask in enumerate(data['disabled']):
        attributes.update({f'd{i}':mask, f'i{i}':data['ignore_rain'][i],
                           f'm{i}':0, f'n{i}':0, f'u{i}':0, f'v{i}':0, f'j{i}':0, f'k{i}':0})
    write('cs', **attributes)
    # API interval days are relative to the current controller date. Preserve
    # the supplied snapshot's phase if import occurs on a later local date.
    elapsed = get('jc')['devt']//86400-data['source_local_epoch']//86400
    expected = []
    for p in data['programs']:
        payload = json.loads(json.dumps(p[:5]))
        if ((payload[0] >> 4) & 3) == 3 and payload[2] > 1:
            payload[1] = (payload[1]-elapsed) % payload[2]
        write('cp', pid=-1, v=json.dumps(payload, separators=(',', ':')), name=p[5], **{'from':p[6][1], 'to':p[6][2]})
        expected.append(payload+[p[5], p[6]])
    actual = get('jp')['pd']
    check([p[:7] for p in actual] == expected, 'Standard program readback mismatch')
    stations = get('jn')
    check(stations['snames'] == names and stations['stn_dis'] == data['disabled'], 'Station readback mismatch')
    check(get('jo')['smode'] == 1 and get('jc')['nq'] == 0, 'Controller must stay paused/idle')
    print(json.dumps(dict(result='PASS', stations=len(names), enabled=sum(not(data['disabled'][i//8] & (1 << (i%8))) for i in range(len(names))), standard_programs=len(actual), valve_destinations='loopback simulator only', automatic_watering=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('configuration', type=Path)
    args = parser.parse_args()
    apply(json.loads(args.configuration.read_text()))
