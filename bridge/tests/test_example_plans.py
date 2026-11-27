import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

HERE = os.path.dirname(os.path.abspath(__file__))
PLANS = os.path.join(HERE, "fixtures", "example_plans.json")
EXAMPLES = os.path.join(HERE, "..", "..", "docs", "examples")


def load():
    with open(PLANS, encoding="utf-8") as handle:
        return json.load(handle)


def read(name):
    with open(os.path.join(EXAMPLES, name), encoding="utf-8") as handle:
        return handle.read()


def test_every_example_is_recorded(bridge):
    """Every example that drives the bridge is recorded; helper modules such as character_models.py are not."""
    scripts = {name for name in os.listdir(EXAMPLES) if name.endswith(".py") and "Handler(" in read(name)}
    plans = load()
    assert scripts <= set(plans), sorted(scripts - set(plans))
    assert all(len(plans[name]) >= 3 for name in scripts), {name: len(plans[name]) for name in scripts}


def test_validate_finds_no_problem_in_a_call_that_ran(bridge):
    """Every example script, replayed as one plan from an empty scene: validate reports a problem only on calls that
    really failed when the script ran (bridge/tests/record_plans.py records them)."""
    false = {}
    for name, recorded in sorted(load().items()):
        calls = [{"cmd": call["cmd"], "args": call["args"]} for call in recorded]
        result = bridge.ok("validate", calls=calls, from_scene=False)
        wrong = [problem for problem in result["problems"] if problem["call"] is None or recorded[problem["call"]]["ok"]]
        if wrong:
            false[name] = [(p["call"], p["cmd"], p["argument"], p["message"][:160]) for p in wrong[:5]]
        assert result["ran"] == 0
    assert not false, json.dumps(false, indent=1)


run(globals())
