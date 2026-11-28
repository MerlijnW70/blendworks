"""The validate command: checks a call or a plan of calls against the schemas without running it."""

from ..limits import MAX_PLAN_CALLS
from ..plan import PlanState, check_plan
from ..registry import command
from ..schema import array, boolean, obj, string

CALL = obj(
    {
        "cmd": string("Command name, as describe lists it (without the blender_ prefix)."),
        "args": {"type": "object", "description": "Arguments of the call; timeout_seconds is allowed and ignored.",
                 "properties": {}, "required": [], "additionalProperties": True},
    },
    ["cmd"],
)


@command(
    "validate",
    "Check one call or a whole plan of calls against the schemas and the names earlier calls make, without running any; reports every problem at once.",
    {
        "calls": array(CALL, "The calls in order, each {cmd, args}.", 1, MAX_PLAN_CALLS),
        "from_scene": boolean("Start from the names in the current scene; false starts from an empty one.", True),
    },
    ["calls"],
    mutates=False,
    family="scene",
    intents=("check my plan before running it", "validate these calls", "how big can a scene be", "dry run a list of tool calls"),
    nearest=(("scene_info", "to see what the scene holds now"),),
)
def validate(ctx, args):
    state = PlanState.from_scene() if args["from_scene"] else PlanState()
    calls = [{"cmd": call["cmd"], "args": call.get("args", {})} for call in args["calls"]]
    problems = check_plan(ctx.registry, calls, state)
    return {"valid": not problems, "calls": len(calls), "problems": problems, "ran": 0}
