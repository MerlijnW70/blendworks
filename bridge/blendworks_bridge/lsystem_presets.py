"""L-system presets such as a bracketed plant and Honda trees."""

STOCHASTIC_1_27 = ["F -> F[+F]F[-F]F : 0.33", "F -> F[+F]F : 0.33", "F -> F[-F]F : 0.34"]
STOCHASTIC_LEAFY = ["F -> F[+FL]F[-FL]FL : 0.33", "F -> F[+FL]FL : 0.33", "F -> F[-FL]FL : 0.34"]
HONDA_RULES = [
    "A(l,w) -> !(w)F(l)[&(a0)B(l*r2,w*wr)]/(d)A(l*r1,w*wr)",
    "B(l,w) -> !(w)F(l)[-(a2)$C(l*r2,w*wr)]C(l*r1,w*wr)",
    "C(l,w) -> !(w)F(l)[+(a2)$B(l*r2,w*wr)]B(l*r1,w*wr)",
]
AONO_RULES = [
    "A(l,w) -> !(w)F(l)[&(a1)B(l*r1,w*wr)]/(180)[&(a2)B(l*r2,w*wr)]",
    "B(l,w) -> !(w)F(l)[+(a1)$B(l*r1,w*wr)][-(a2)$B(l*r2,w*wr)]",
]
TERNARY_RULES = ["A -> !(vr)F(50)[&(a)F(50)A]/(d1)[&(a)F(50)A]/(d2)[&(a)F(50)A]", "F(l) -> F(l*lr)", "!(w) -> !(w*vr)"]


def bracketed(figure, letter, iterations, angle, axiom, rules, step, note):
    return {
        "citation": f"S1, section 1.6.3, figure {figure}({letter})",
        "description": f"Bracketed OL-system, {note}; n={iterations}, angle {angle} degrees.",
        "axiom": axiom,
        "rules": rules,
        "iterations": iterations,
        "angle": angle,
        "step": step,
        "width": 0.35 * step,
        "branch_taper": True,
    }


def honda(figure, letter, r1, r2, a0, a2):
    return {
        "citation": f"S1, section 2.1, figure {figure}({letter}), table 2.1",
        "description": "Monopodial tree of Honda as an L-system: main axis A, lateral apices B and C that alternate sides; the width falls by wr = 0.707 at every step. Organs fit the apices A, B and C.",
        "axiom": "A(1,10)",
        "rules": HONDA_RULES,
        "constants": {"r1": r1, "r2": r2, "a0": a0, "a2": a2, "d": 137.5, "wr": 0.707},
        "iterations": 10,
        "step": 1.0,
        "width": 0.012,
        "branch_taper": False,
    }


PRESETS = {
    "bracketed_1_24a": bracketed("1.24", "a", 5, 25.7, "F", ["F -> F[+F]F[-F]F"], 0.008, "edge rewriting"),
    "bracketed_1_24b": bracketed("1.24", "b", 5, 20.0, "F", ["F -> F[+F]F[-F][F]"], 0.02, "edge rewriting"),
    "bracketed_1_24c": bracketed("1.24", "c", 4, 22.5, "F", ["F -> FF-[-F+F+F]+[+F-F-F]"], 0.02, "edge rewriting"),
    "bracketed_1_24d": bracketed("1.24", "d", 7, 20.0, "X", ["X -> F[+X]F[-X]+X", "F -> FF"], 0.005, "node rewriting, the apices X stay in the string for organs"),
    "bracketed_1_24e": bracketed("1.24", "e", 7, 25.7, "X", ["X -> F[+X][-X]FX", "F -> FF"], 0.005, "node rewriting, the apices X stay in the string for organs"),
    "bracketed_1_24f": bracketed("1.24", "f", 5, 22.5, "X", ["X -> F-[[X]+X]+F[+FX]-X", "F -> FF"], 0.02, "node rewriting, the apices X stay in the string for organs"),
    "bush_1_25": {
        "citation": "S1, section 1.6.3, figure 1.25",
        "description": "Three-dimensional bush: each apex A makes three branches, internodes F lengthen and gain a leaf L at every step. The book draws the leaf as a polygon; here L and the apex A are organ symbols. The book uses n=7; n=6 keeps the node count down. Angle 22.5 degrees.",
        "axiom": "A",
        "rules": ["A -> [&FL!A]/////'[&FL!A]///////'[&FL!A]", "F -> S/////F", "S -> FL"],
        "iterations": 6,
        "angle": 22.5,
        "step": 0.06,
        "width": 0.012,
        "width_ratio": 0.8,
        "branch_taper": False,
    },
    "stochastic_1_27": {
        "citation": "S1, section 1.7, figure 1.27",
        "description": "Stochastic bracketed OL-system: three productions for F with probabilities .33, .33 and .34; different seeds look like specimens of one species. n=5, angle 22.5 degrees.",
        "axiom": "F",
        "rules": STOCHASTIC_1_27,
        "iterations": 5,
        "angle": 22.5,
        "step": 0.018,
        "width": 0.005,
        "branch_taper": True,
    },
    "stochastic_1_27_leafy": {
        "citation": "S1, section 1.7, figure 1.27, with leaves after section 1.6.3, figure 1.25",
        "description": "The productions of figure 1.27 with a leaf L at the end of each lateral branch and a flower K at the end of the main axis; the organ symbols are the only change. n=5, angle 22.5 degrees.",
        "axiom": "FK",
        "rules": STOCHASTIC_LEAFY,
        "iterations": 5,
        "angle": 22.5,
        "step": 0.018,
        "width": 0.005,
        "branch_taper": True,
    },
    "monopodial_2_6a": honda("2.6", "a", 0.9, 0.6, 45.0, 45.0),
    "monopodial_2_6d": honda("2.6", "d", 0.9, 0.7, 30.0, -30.0),
    "sympodial_2_7c": {
        "citation": "S1, section 2.1, figure 2.7(c), table 2.2",
        "description": "Sympodial tree of Aono and Kunii: the apex makes two lateral apices B of unequal contraction; width falls by wr = 0.707. n=10.",
        "axiom": "A(1,10)",
        "rules": AONO_RULES,
        "constants": {"r1": 0.9, "r2": 0.8, "a1": 20.0, "a2": 50.0, "wr": 0.707},
        "iterations": 10,
        "step": 1.0,
        "width": 0.012,
        "branch_taper": False,
    },
    "ternary_2_8a": {
        "citation": "S1, section 2.1, figure 2.8(a), table 2.3",
        "description": "Tree with ternary branching: segments lengthen by lr and thicken by vr = sqrt(3) at every step, and tropism bends the branches down. n=6.",
        "axiom": "!(1)F(200)/(45)A",
        "rules": TERNARY_RULES,
        "constants": {"d1": 94.74, "d2": 132.63, "a": 18.95, "lr": 1.109, "vr": 1.732},
        "iterations": 6,
        "step": 0.007,
        "width": 0.01,
        "tropism": {"vector": [0.0, 0.0, -1.0], "strength": 0.22},
        "branch_taper": False,
    },
    "compound_leaf_5_11b": {
        "citation": "S1, section 5.3, figure 5.11(b), table 5.2",
        "description": "Compound leaf of the wild-carrot kind: the apex A(d) waits D steps, then makes two internodes, two lateral apices and a new main apex, and every internode lengthens by R. D=1, R=1.5. The book uses n=16, which draws 87381 segments, past the node cap, so n=10 here; the book gives no angle and 60 degrees is ours.",
        "axiom": "A(0)",
        "rules": ["A(d) : d > 0 -> A(d-1)", "A(d) : d = 0 -> F(1)[+A(D)][-A(D)]F(1)A(0)", "F(a) -> F(a*R)"],
        "constants": {"D": 1.0, "R": 1.5},
        "iterations": 10,
        "angle": 60.0,
        "step": 0.0027,
        "width": 0.0011,
        "branch_taper": False,
    },
    "compound_leaf_5_12a": {
        "citation": "S1, section 5.3, figure 5.12(a), table 5.3",
        "description": "Compound leaf with alternating branches: lateral apices on the left and right in turn. D=1, R=1.36. The book uses n=20, here n=14; the book gives no angle and 60 degrees is ours.",
        "axiom": "A(0)",
        "rules": [
            "A(d) : d > 0 -> A(d-1)",
            "A(d) : d = 0 -> F(1)[+A(D)]F(1)B(0)",
            "B(d) : d > 0 -> B(d-1)",
            "B(d) : d = 0 -> F(1)[-B(D)]F(1)A(0)",
            "F(a) -> F(a*R)",
        ],
        "constants": {"D": 1.0, "R": 1.36},
        "iterations": 14,
        "angle": 60.0,
        "step": 0.003,
        "width": 0.0012,
        "branch_taper": False,
    },
}


def preset_names():
    return tuple(PRESETS)

