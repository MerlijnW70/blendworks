"""Geometric error between LOD levels from directed distances."""

import numpy as np

from package_surface import nearest_distances

SEED = 20260101


def directed_distances(source, target, generator, scale):
    points = np.concatenate([source.used_vertices(), source.sample(source.sample_count(scale), generator)])
    return nearest_distances(points, target)


def geometric_error(reference, candidate, seed=SEED, sample_scale=1.0):
    generator = np.random.default_rng(seed)
    outward = directed_distances(reference, candidate, generator, sample_scale)
    inward = directed_distances(candidate, reference, generator, sample_scale)
    both = np.concatenate([outward, inward])
    diagonal = reference.diagonal()
    worst = float(both.max()) if len(both) else 0.0
    return {
        "hausdorff": worst,
        "hausdorffFraction": worst / diagonal if diagonal > 0 else 0.0,
        "mean": float(both.mean()) if len(both) else 0.0,
        "referenceToCandidate": float(outward.max()) if len(outward) else 0.0,
        "candidateToReference": float(inward.max()) if len(inward) else 0.0,
        "samples": int(len(both)),
        "diagonal": diagonal,
    }
