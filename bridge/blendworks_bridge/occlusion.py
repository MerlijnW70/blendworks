"""Ambient occlusion mask for procedural materials."""

FULL_OCCLUSION = 0.25
SAMPLES = 16


def occlusion_mask(graph, distance, inside, samples=SAMPLES):
    node = graph.node("ShaderNodeAmbientOcclusion", {"Distance": distance}, inside=inside, samples=samples)
    return graph.map_range(graph.math("SUBTRACT", 1.0, node.outputs["AO"]), 0.0, FULL_OCCLUSION)
