import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

from lsystem_helpers import FIG_1_24_A, FIG_1_24_D, FIG_1_27, PARAMETRIC_1_7, text, turtle, words
from blendworks_bridge.lsystem_presets import PRESETS

P = "F[+F]F[-F]F"
FIG_1_24_A_N2 = f"{P}[+{P}]{P}[-{P}]{P}"
FIG_1_24_D_N2 = "FF[+F[+X]F[-X]+X]FF[-F[+X]F[-X]+X]+F[+X]F[-X]+X"


def test_bracketed_derivations_equal_the_hand_worked_strings_of_figure_1_24(bridge):
    assert text("F", FIG_1_24_A, 0) == "F"
    assert text("F", FIG_1_24_A, 1) == P
    assert text("F", FIG_1_24_A, 2) == FIG_1_24_A_N2 == "F[+F]F[-F]F[+F[+F]F[-F]F]F[+F]F[-F]F[-F[+F]F[-F]F]F[+F]F[-F]F"
    assert text("X", FIG_1_24_D, 1) == "F[+X]F[-X]+X"
    assert text("X", FIG_1_24_D, 2) == FIG_1_24_D_N2


def test_the_segment_count_matches_the_derivation(bridge):
    for steps in range(0, 5):
        word = words("F", FIG_1_24_A, steps).word
        assert sum(1 for symbol, _ in word if symbol == "F") == 5**steps
    plant = turtle(text("F", FIG_1_24_A, 2), angle=25.7)
    assert plant.stats["segments"] == 25 and plant.skeleton.count == 26
    plant = turtle(text("X", FIG_1_24_D, 2), angle=20.0)
    assert plant.stats["segments"] == 10 and plant.skeleton.count == 11
    result = bridge.ok("lsystem", name="Weed", preset="bracketed_1_24a", iterations=2, limit=0)
    assert result["lsystem"]["word"] == FIG_1_24_A_N2 and result["lsystem"]["segments"] == 25 and result["nodes"] == 26
    result = bridge.ok("lsystem", name="Fan", preset="bracketed_1_24d", iterations=2, limit=0)
    assert result["lsystem"]["word"] == FIG_1_24_D_N2 and result["lsystem"]["segments"] == 10
    assert result["lsystem"]["string_lengths"] == [1, 12, len(FIG_1_24_D_N2)]


def test_a_parametric_rule_with_a_condition_gives_the_hand_worked_two_steps(bridge):
    axiom = "B(2)A(4,4)"
    assert text(axiom, PARAMETRIC_1_7, 0) == "B(2)A(4,4)"
    assert text(axiom, PARAMETRIC_1_7, 1) == "B(1)B(4)A(1,0)"
    assert text(axiom, PARAMETRIC_1_7, 2) == "B(0)B(3)A(2,1)"
    assert text(axiom, PARAMETRIC_1_7, 3) == "CB(2)A(4,3)"
    assert text(axiom, PARAMETRIC_1_7, 4) == "CB(1)A(8,7)"
    assert text(axiom, PARAMETRIC_1_7, 5) == "CB(0)B(8)A(1.14286,0)"
    assert text("A(9)", ["A(t) : t > 5 -> B(t+1)CD(t^0.5,t-2)"], 1) == "B(10)CD(3,7)"
    assert text("A(5)", ["A(t) : t > 5 -> B(t+1)CD(t^0.5,t-2)"], 1) == "A(5)"
    assert text("A(1,2)", ["A(t) : t > 0 -> B(t)"], 1) == "A(1,2)"


def test_expressions_follow_the_book_operators_and_precedence(bridge):
    rule = "A(x) -> B(x+1, x*2^3, -x^2, (x>1)&(x<5), !0, 7/2, sqrt(x), min(x,3), 2^3^2, x=4, x!=4, 1|0, 8-3-2, k)"
    assert text("A(4)", [rule], 1, constants={"k": 0.25}) == "B(5,32,-16,1,1,3.5,2,3,512,1,0,1,3,0.25)"
    assert text("A(4)", ["A(x) : x > 1 & x < 3 | x = 4 -> B"], 1) == "B"
    assert text("A(2)", ["A(x) : x > 1 -> B(x)", "A(x) -> C"], 1) == "B(2)"


def test_stochastic_rules_are_deterministic_by_seed_and_follow_their_probabilities(bridge):
    first = text("F", FIG_1_27, 5, seed=11)
    assert first == text("F", FIG_1_27, 5, seed=11)
    assert len({text("F", FIG_1_27, 4, seed=seed) for seed in range(12)}) > 6
    successors = {"F[+F]F[-F]F": 0, "F[+F]F": 0, "F[-F]F": 0}
    seeds = 3000
    for seed in range(seeds):
        successors[text("F", FIG_1_27, 1, seed=seed)] += 1
    tolerance = 0.03
    for successor, expected in (("F[+F]F[-F]F", 0.33), ("F[+F]F", 0.33), ("F[-F]F", 0.34)):
        assert abs(successors[successor] / seeds - expected) < tolerance, (successor, successors)
    skewed = ["F -> FF : 0.2", "F -> F : 0.8"]
    doubled = sum(text("F", skewed, 1, seed=seed) == "FF" for seed in range(seeds))
    assert abs(doubled / seeds - 0.2) < tolerance, doubled
    many = text("F" * 4000, skewed, 1, seed=3)
    assert abs((len(many) - 4000) / 4000 - 0.2) < tolerance


def test_the_choice_follows_the_conditions_that_hold(bridge):
    rules = ["A(x) : x > 1 -> B : 0.5", "A(x) : x > 1 -> C : 0.5", "A(x) : x <= 1 -> D : 1"]
    assert text("A(0)", rules, 1) == "D"
    results = {text("A(2)", rules, 1, seed=seed) for seed in range(40)}
    assert results == {"B", "C"}


def test_the_string_cap_refuses_an_exploding_grammar_before_expanding(bridge):
    started = time.perf_counter()
    message = bridge.refuse("lsystem", "bad_args", name="Boom", axiom="F", rules=["F -> FFFFFFFFFF"], iterations=100, max_length=100_000)
    assert time.perf_counter() - started < 5.0
    assert "derivation step 6" in message and "from 100000 modules to at least 1000000" in message and "max_length" in message, message
    message = bridge.refuse("lsystem", "bad_args", name="Boom", axiom="F", rules=["F -> FFFFFFFFFF : 0.5", "F -> F : 0.5"], iterations=100, max_length=2000)
    assert "more than 2000" in message, message
    message = bridge.refuse("lsystem", "bad_args", name="Boom", axiom="A(0)", rules=["A(x) : x < 1 -> A(x)A(x)A(x)A(x)", "A(x) : x >= 1 -> A(x)"], iterations=100, max_length=5000)
    assert "more than 5000" in message, message
    doubling = ["A(x) : x < 1 -> A(x)A(x)"]
    assert bridge.ok("lsystem", name="Edge", axiom="FA(0)", rules=doubling, iterations=3, max_length=9, limit=0)["lsystem"]["string_lengths"] == [2, 3, 5, 9]
    message = bridge.refuse("lsystem", "bad_args", name="Edge2", axiom="FA(0)", rules=doubling, iterations=3, max_length=8)
    assert "derivation step 3 would grow the string from 5 modules to more than 8" in message, message
    message = bridge.refuse("lsystem", "bad_args", name="Boom", axiom="FFFF", max_length=3)
    assert "axiom has 4 modules" in message
    assert [entry["name"] for entry in bridge.ok("scene_info")["objects"]] == ["Edge"]


def test_the_node_cap_is_checked_before_the_turtle_runs(bridge):
    message = bridge.refuse("lsystem", "bad_args", name="Dense", axiom="F", rules=["F -> FF"], iterations=12, max_nodes=1000)
    assert "draws 4097 nodes" in message and "cap of 1000" in message and "max_nodes" in message, message
    message = bridge.refuse("lsystem", "bad_args", name="Dense", preset="compound_leaf_5_11b", iterations=16, max_length=1_000_000)
    assert "max_nodes" in message, message
    assert bridge.ok("scene_info")["objects"] == []


def test_parse_errors_name_the_rule_and_the_position(bridge):
    cases = [
        (["F -> FF", "A(x) : y > 1 -> F"], "rule 2 (A(x) : y > 1 -> F), position 8: unknown name y; known names are x"),
        (["F -> F[+F]F", "F F"], "rule 2 (F F): expected '->' between the predecessor and the successor"),
        (["A(x) -> F(x"], "rule 1 (A(x) -> F(x), position 12: expected a closing parenthesis"),
        (["F -> F{+f}"], "rule 1 (F -> F{+f}), position 7: '{' is not supported: polygons (leaves and flowers are placed with the organs option)"),
        (["[ -> F"], "rule 1 ([ -> F), position 1: brackets replace themselves and cannot be rewritten"),
        (["A(x,x) -> F"], "rule 1 (A(x,x) -> F), position 5: parameter x is listed twice"),
        (["A(x) -> F(x +)"], "rule 1 (A(x) -> F(x +)), position 14: expected a number, a parameter, a function or a parenthesis"),
        (["F -> F : 0.5", "F -> FF : 0.2"], "the probabilities of rules 1, 2 for F add up to 0.7, not 1 [S1, 1.7]"),
        (["F -> F : 0.5", "F -> FF"], "rules 1, 2 all rewrite F with 0 parameter(s): either every one has a probability or none does"),
        (["F -> F : 1.5"], "rule 1 (F -> F : 1.5), position 10: the probability 1.5 is not in (0, 1]"),
        (["F -> F", "F -> FF"], "only the first could ever apply"),
        (["F -> F -> F"], "a rule has one '->'"),
        (["A(x) : x > 1 > -> F"], "rule 1"),
        (["Z -> F(sqrt)"], "rule 1 (Z -> F(sqrt)), position 12: expected ( after sqrt"),
    ]
    for rules, expected in cases:
        message = bridge.refuse("lsystem", "bad_args", name="Bad", axiom="F", rules=rules)
        assert expected in message, (rules, message)
    assert "axiom, position 2" in bridge.refuse("lsystem", "bad_args", name="Bad", axiom="F?", rules=[])
    assert "axiom, position 3: unknown name x" in bridge.refuse("lsystem", "bad_args", name="Bad", axiom="A(x)")
    assert "give an axiom" in bridge.refuse("lsystem", "bad_args", name="Bad", rules=["F -> F"])


def test_arithmetic_failures_during_the_derivation_name_the_rule_and_the_module(bridge):
    message = bridge.refuse("lsystem", "bad_args", name="Bad", axiom="A(0)", rules=["A(x) -> A(1/x)"], iterations=1)
    assert "rule 1 (A(x) -> A(1/x)) applied to A(0) divides by zero" in message, message
    message = bridge.refuse("lsystem", "bad_args", name="Bad", axiom="A(10)", rules=["A(x) -> A(x^400)"], iterations=1)
    assert "applied to A(10)" in message, message
    message = bridge.refuse("lsystem", "bad_args", name="Bad", axiom="A(-1)", rules=["A(x) -> A(sqrt(x))"], iterations=1)
    assert "applied to A(-1) cannot be computed" in message, message


def test_every_preset_cites_the_book_and_derives_within_the_caps(bridge):
    assert len(PRESETS) >= 10
    for name, preset in PRESETS.items():
        assert preset["citation"].startswith("S1, section") and "figure" in preset["citation"], name
        assert preset["description"], name
        result = bridge.ok("lsystem", name=name, preset=name, limit=0, organs=[])
        assert result["lsystem"]["preset"] == name and result["nodes"] > 20, (name, result["nodes"])
        assert result["lsystem"]["string_lengths"][0] == len(words(preset["axiom"], [], 0, constants=preset.get("constants")).word)
        bridge.ok("delete", names=[name])


def test_overrides_replace_the_preset_and_constants_merge(bridge):
    first = bridge.ok("lsystem", name="A", preset="monopodial_2_6a", iterations=3, limit=0)
    second = bridge.ok("lsystem", name="B", preset="monopodial_2_6a", iterations=3, constants=[{"name": "r2", "value": 0.9}], limit=0)
    assert first["lsystem"]["word"] != second["lsystem"]["word"] and first["nodes"] == second["nodes"] == 8
    third = bridge.ok("lsystem", name="C", preset="bracketed_1_24a", rules=["F -> FF"], iterations=2, limit=0)
    assert third["lsystem"]["word"] == "FFFF" and third["lsystem"]["segments"] == 4


run(globals())
