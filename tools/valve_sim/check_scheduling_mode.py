"""Mode-isolation integration check; dedicated DEMO + loopback valves only.

Temporarily creates one Standard program and finishes in soil preview mode.
Run on the authorized test Pi: python3 -m tools.valve_sim.check_scheduling_mode
"""
import json, time
from tools.valve_sim.exercise import get, guard, status, check, wait_event

def main():
    guard()
    check(get('jc')['nq'] == 0, 'idle required')
    original = get('jo')
    for invalid in ['2','-1','abc','','0junk','1.0']:
        check(get('co', {'smode':invalid,'wl':99}).get('result') != 1, 'invalid accepted')
        check(get('jo')['wl'] == original['wl'], 'partial option mutation')
    check(get('co', {'smode':1}).get('result') == 1, 'mode rejected')
    check(get('jo')['smode'] == 1, 'mode not saved')
    print('PASS: both API validation and soil mode selection', flush=True)
    # This synthetic weekly program is due every minute, targets only SIM LinkTap.
    program = [1,127,0,[0,1439,1,0],[2,0,0,0,0,0,0,0]]
    check(get('cp', {'pid':-1,'name':'Mode isolation test','v':json.dumps(program,separators=(',',':'))}).get('result') == 1, 'test program creation failed')
    snapshot = get('jp')
    try:
        before = status()['sequence']
        minute = get('jc')['devt']//60
        deadline = time.monotonic()+70
        while get('jc')['devt']//60 == minute and time.monotonic() < deadline:
            time.sleep(.5)
        time.sleep(4)
        check(get('jc')['nq']==0 and status()['sequence']==before, 'standard auto program ran in soil mode')
        check(get('jp')==snapshot, 'standard program altered')
        print('PASS: due Standard program remained inactive and intact in soil mode', flush=True)
        check(get('co', {'smode':0}).get('result')==1, 'Standard selection rejected')
        deadline = time.monotonic()+70
        while status()['sequence']==before and time.monotonic() < deadline:
            time.sleep(.5)
        check(status()['sequence']>before, 'Standard automatic run did not resume')
        time.sleep(4)
        check(get('jc')['nq']==0 and not any(status()['states'].values()), 'test did not finish')
        print('PASS: same Standard program resumed automatically after switching back', flush=True)
    finally:
        check(get('dp', {'pid':0}).get('result')==1, 'test program cleanup failed')
        get('co', {'smode':1})
    guard()
    # Busy engine switches must reject the whole request; manual test is loopback only.
    before = status()
    get('cm', {'sid':0,'en':1,'t':8})
    on = wait_event('lt', 'on', before['sequence'], before['session'])
    check(get('co', {'smode':0,'wl':99}).get('result')==48, 'busy switch accepted')
    check(get('jo')['smode']==1 and get('jo')['wl']==original['wl'], 'busy request partly applied')
    get('cm', {'sid':0,'en':0})
    wait_event('lt', 'off', on['sequence'], before['session'])
    deadline = time.monotonic() + 10
    while get('jc')['nq'] and time.monotonic() < deadline:
        time.sleep(.2)
    check(get('jc')['nq']==0 and not any(status()['states'].values()), 'not idle')
    print('PASS: busy switch rejected atomically; test Pi left in soil preview, idle', flush=True)


if __name__ == "__main__":
    main()
