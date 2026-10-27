import numpy as np

ALPHA_THRESHOLD = 0.5
BACKGROUND = 0.18
WINDOW = 7
C1 = (0.01) ** 2
C2 = (0.03) ** 2
LUMA = np.array([0.2126, 0.7152, 0.0722])


def silhouette(rgba):
    return rgba[..., 3] > ALPHA_THRESHOLD


def silhouette_iou(first, second):
    union = np.count_nonzero(first | second)
    if union == 0:
        return 1.0
    return np.count_nonzero(first & second) / union


def luminance(rgba):
    alpha = rgba[..., 3:4]
    colour = rgba[..., :3] * alpha + BACKGROUND * (1.0 - alpha)
    return colour @ LUMA


def window_sums(image, size):
    padded = np.zeros((image.shape[0] + 1, image.shape[1] + 1))
    padded[1:, 1:] = np.cumsum(np.cumsum(image, axis=0), axis=1)
    return padded[size:, size:] - padded[:-size, size:] - padded[size:, :-size] + padded[:-size, :-size]


def ssim_map(first, second, size=WINDOW):
    area = size * size
    mean_first = window_sums(first, size) / area
    mean_second = window_sums(second, size) / area
    variance_first = window_sums(first * first, size) / area - mean_first**2
    variance_second = window_sums(second * second, size) / area - mean_second**2
    covariance = window_sums(first * second, size) / area - mean_first * mean_second
    numerator = (2.0 * mean_first * mean_second + C1) * (2.0 * covariance + C2)
    denominator = (mean_first**2 + mean_second**2 + C1) * (variance_first + variance_second + C2)
    return numerator / denominator


def mean_ssim(first, second, size=WINDOW):
    size = min(size, first.shape[0], first.shape[1])
    return float(ssim_map(first, second, size).mean())


def covered_box(mask, margin, shape):
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    if len(rows) == 0:
        return None
    top = max(0, int(rows[0]) - margin)
    bottom = min(shape[0], int(rows[-1]) + 1 + margin)
    left = max(0, int(columns[0]) - margin)
    right = min(shape[1], int(columns[-1]) + 1 + margin)
    return top, bottom, left, right


def compare_renders(reference, candidate):
    first = silhouette(reference)
    second = silhouette(candidate)
    iou = silhouette_iou(first, second)
    box = covered_box(first | second, WINDOW, first.shape)
    if box is None:
        return {"silhouetteIou": iou, "similarity": 1.0, "silhouettePixels": [0, 0]}
    top, bottom, left, right = box
    similarity = mean_ssim(luminance(reference)[top:bottom, left:right], luminance(candidate)[top:bottom, left:right])
    return {
        "silhouetteIou": float(iou),
        "similarity": similarity,
        "silhouettePixels": [int(np.count_nonzero(first)), int(np.count_nonzero(second))],
    }
