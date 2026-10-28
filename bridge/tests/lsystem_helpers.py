import bpy
import numpy

from blendworks_bridge.lsystem_derive import derive
from blendworks_bridge.lsystem_rules import format_word, parse_axiom, parse_rules
from blendworks_bridge.lsystem_turtle import Settings, interpret
from blendworks_bridge.tree_skeleton import PROPERTY

FIG_1_24_A = ["F -> F[+F]F[-F]F"]
FIG_1_24_D = ["X -> F[+X]F[-X]+X", "F -> FF"]
FIG_1_27 = ["F -> F[+F]F[-F]F : 0.33", "F -> F[+F]F : 0.33", "F -> F[-F]F : 0.34"]
PARAMETRIC_1_7 = ["A(x,y) : y <= 3 -> A(x*2,x+y)", "A(x,y) : y > 3 -> B(x)A(x/y,0)", "B(x) : x < 1 -> C", "B(x) : x >= 1 -> B(x-1)"]


def words(axiom, rules, iterations, seed=0, constants=None, max_length=100_000):
    constants = constants or {}
    start = parse_axiom(axiom, constants)
    return derive(start, parse_rules(rules, constants), iterations, max_length, seed)


def text(axiom, rules, iterations, **options):
    return format_word(words(axiom, rules, iterations, **options).word)


def turtle(word, angle=90.0, step=1.0, width=0.02, width_ratio=0.5, branch_taper=True, tropism=(0.0, 0.0, -1.0), strength=0.0, organs=(), max_nodes=1000):
    settings = Settings(angle, step, width, width_ratio, tropism, strength, branch_taper, max_nodes, organs)
    return interpret(parse_axiom(word, {}), settings)


def tree_data(name):
    data = bpy.data.objects[name][PROPERTY]
    return {key: (value.to_list() if hasattr(value, "to_list") else value) for key, value in data.to_dict().items()}


def positions_of(plant):
    return plant.skeleton.positions.tolist()


def assert_frame(organ, heading, left, up):
    assert numpy.array_equal(numpy.array(organ.heading), numpy.array(heading)), (organ.heading, heading)
    assert numpy.array_equal(numpy.array(organ.left), numpy.array(left)), (organ.left, left)
    assert numpy.array_equal(numpy.array(organ.up), numpy.array(up)), (organ.up, up)
