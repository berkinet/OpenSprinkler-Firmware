"""Exercise an already configured local DEMO controller, never production."""
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler

from tools.irrigation_replay.replay import replay


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = build_opener(ProxyHandler({}), NoRedirect())
TARGETS = {str(i): dict(st=4, sd=f"127.0.0.1,18080,sim/{z}/on,sim/{z}/off")
           for i, z in enumerate(("lt", "rm"))}


def get(path, parameters=None, port=80):
    url = f"http://127.0.0.1:{port}/{path}"
    if parameters:
        url += "?" + urlencode(parameters)
    with OPENER.open(url, timeout=5) as response:
        return json.load(response)


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def guard():
    check(get("jo")["hwv"] == 255, "Requires a DEMO firmware build")
    check(get("je") == TARGETS, "Requires exactly the two loopback HTTP test zones")
    names = get("jn")
    check(names["snames"][:2] == ["SIM LinkTap", "SIM RainMachine"], "Unexpected zones")
    check(names["stn_dis"] == [252], "Other stations must be disabled")
    check(get("jp")["nprogs"] == 0, "Scheduled programs must be absent")
    options = get("jo")
    check(all(options[key] == 0 for key in ("mas", "mas2", "mas3", "mas4")),
          "Master outputs must be disabled")


def status():
    data = get("status", port=18080)
    check(data["service"] == "opensprinkler-valve-simulator", "Wrong receiver")
    return data


def command(sid, enable, duration=0):
    guard()
    result = get("cm", dict(sid=sid, en=int(enable), t=duration))
    check(result.get("result") == 1, f"Command rejected: {result}")


def wait_event(zone, action, after, session, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = status()
        check(data["session"] == session, "Receiver restarted during test")
        for event in data["events"]:
            if (event["sequence"] > after and event["zone"] == zone and
                    event["action"] == action and event["changed"]):
                return event
        time.sleep(0.1)
    raise RuntimeError(f"Missing {zone} {action} callback")


def pulse(sid, seconds, stop_early=False):
    zone = ("lt", "rm")[sid]
    before = status()
    command(sid, True, seconds)
    on = wait_event(zone, "on", before["sequence"], before["session"])
    if stop_early:
        time.sleep(1)
        command(sid, False)
    off = wait_event(zone, "off", on["sequence"], before["session"], seconds + 6)
    elapsed = off["monotonic"] - on["monotonic"]
    if stop_early:
        check(0.8 <= elapsed < seconds / 2, "Explicit stop did not shorten run")
    else:
        check(abs(elapsed - seconds) < 1.5, f"Unexpected timed duration: {elapsed}")
    deadline = time.monotonic() + 5
    while get("jc")["nq"] and time.monotonic() < deadline:
        time.sleep(0.1)
    check(get("jc")["nq"] == 0, "Queue did not drain")
    return dict(zone=zone, requested_seconds=seconds, observed_seconds=elapsed,
                on=on["monotonic"], off=off["monotonic"], stopped_early=stop_early)


def main():
    guard()
    check(get("jc")["nq"] == 0, "Controller must initially be idle")
    before = status()
    check(not any(before["states"].values()), "Simulated valves must initially be off")
    report = dict(mode="DEMO_loopback_only", timing_tolerance_seconds=1.5)
    try:
        report["timed_runs"] = [pulse(0, 4), pulse(1, 4)]
        report["explicit_stops"] = [pulse(0, 20, True), pulse(1, 20, True)]
        fixture = Path(__file__).parents[1] / "irrigation_replay/fixtures/capacity-and-soak.json"
        plan = replay(json.loads(fixture.read_text()))
        decision = next(d for d in plan["windows"][0]["decisions"] if d["zone_id"] == "A")
        pulses = decision["pulses"]
        check(len(pulses) == 5 and sum(p["end"] - p["start"] for p in pulses) == 300,
              "Fixture no longer describes five one-minute pulses")
        cycles = []
        # 20x shorter wall-clock test; wait from observed OFF, not a planned end.
        for index, planned in enumerate(pulses):
            if index:
                gap = (planned["start"] - pulses[index - 1]["end"]) / 20
                time.sleep(max(0, cycles[-1]["off"] + gap - time.monotonic()))
            duration = (planned["end"] - planned["start"]) // 20
            cycles.append(pulse(0, duration))
        gaps = [b["on"] - a["off"] for a, b in zip(cycles, cycles[1:])]
        check(all(gap >= 3 for gap in gaps), "Minimum soak violated")
        check(not any(status()["states"].values()), "A simulated valve remained on")
        check(get("jc")["nq"] == 0 and not any(get("jc")["sbits"]), "Controller not idle")
        report.update(result="PASS", cycle_soak=dict(scale=20, pulses=cycles,
                      observed_soak_seconds=gaps, original_on_seconds=300,
                      original_elapsed_seconds=540))
        print(json.dumps(report, indent=2))
    finally:
        # Only clean up these two known simulated stations, and recheck destinations.
        guard()
        state = get("jc")
        for sid in (0, 1):
            if state["ps"][sid][0]:
                command(sid, False)


if __name__ == "__main__":
    main()
