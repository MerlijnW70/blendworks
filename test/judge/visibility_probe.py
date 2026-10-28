import json
import math
import sys

arguments = sys.argv[sys.argv.index("--") + 1 :]
judge_dir, out_path = arguments
sys.path.insert(0, judge_dir)

from judge_rays import fixed_directions, generator_for, portable_sin_cos, stratified_sample

SHA_A = "a" * 64
SHA_B = "b" * 64
COUNT = 1000
WANTED = 100

line = [(index / COUNT, 0.0, 0.0) for index in range(COUNT)]
shuffled = sorted(range(COUNT), key=lambda index: (index * 7919) % COUNT)
scattered = [line[index] for index in shuffled]
low, high = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)


def chosen(points, seed):
    return stratified_sample(points, low, high, WANTED, generator_for(seed))


first = chosen(scattered, SHA_A)
angles = [step * 0.37 - 40.0 for step in range(240)]
directions = fixed_directions()
result = {
    "sameSeed": chosen(scattered, SHA_A) == first,
    "otherSeed": chosen(scattered, SHA_B) == first,
    "count": len(first),
    "weights": sum(weight for _, weight in first),
    "perStratum": sorted({int(scattered[index][0] * COUNT) // (COUNT // WANTED) for index, _ in first}) == list(range(WANTED)),
    "allWhenFew": stratified_sample(line[:50], low, high, WANTED, generator_for(SHA_A)) == [(index, 1.0) for index in range(50)],
    "sineError": max(max(abs(portable_sin_cos(angle)[0] - math.sin(angle)), abs(portable_sin_cos(angle)[1] - math.cos(angle))) for angle in angles),
    "directions": len(directions),
    "unit": max(abs(math.sqrt(sum(value * value for value in direction)) - 1.0) for direction in directions),
    "repeatable": fixed_directions() == directions,
    "spread": min(max(direction[axis] for direction in directions) for axis in range(3)),
}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(result, handle)
