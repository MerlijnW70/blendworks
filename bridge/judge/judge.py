import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from judge_common import script_arguments, split_arguments
from judge_pass import PASS_DEFAULTS, run_pass

USAGE = (
    "judge.py -- <asset> <out dir> --stages measure,reference,views,sheet,closeups [--max-triangles n] [--memory-mb n]"
    " [--memory-kind address-space|data] [--measure-address-space yes|no] [--floating-tolerance metres] [--objects yes|no]"
    " [--extras rig,skin,animation,colours] [--weight-tolerance t] [--reference-views front:512] [--reference-frame measured|asset|x0,y0,z0,x1,y1,z1]"
    " [--reference-origin x,y,z] [--render-max-triangles n] [--views front,top] [--title text] [--device CPU|AUTO|OPTIX|CUDA|HIP|METAL|ONEAPI] [--backends OPTIX,CUDA]"
    " [--gpu-fallback yes|no] [--res px] [--samples n] [--closeup-res px] [--closeup-samples n] [--closeup-title text]"
)


def main():
    positional, options = split_arguments(script_arguments(), PASS_DEFAULTS)
    if len(positional) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, out_dir = positional
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    run_pass(os.path.abspath(asset), out_dir, options)


main()
