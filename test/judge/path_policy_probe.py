import json
import sys

arguments = sys.argv[sys.argv.index("--") + 1 :]
judge_dir, cases_path, out_path = arguments
sys.path.insert(0, judge_dir)

from judge_paths import check_reference

with open(cases_path, encoding="utf-8") as handle:
    cases = json.load(handle)

results = []
for case in cases:
    path, problem = check_reference(case["raw"], case["style"])
    results.append({"path": path} if problem is None else {"refused": problem[0], "reason": problem[1]})

with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(results, handle)
