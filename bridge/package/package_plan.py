import math

REFERENCE_HEIGHT_PIXELS = 1080
REFERENCE_FOV_DEGREES = 60.0
SWITCH_PIXELS = 1.0
MIN_DISTANCE_RADII = 2.0
REACH_TOLERANCE = 1.05
MIN_RATIO = 0.01
MIN_TRIANGLES = 12
CROP_STEP = 32
CROP_MIN = 128
CROP_MAX = 512
CROP_MARGIN = 1.25
MAX_LEVELS = 8


def pixels_per_metre_at_one_metre():
    return REFERENCE_HEIGHT_PIXELS / (2.0 * math.tan(math.radians(REFERENCE_FOV_DEGREES) / 2.0))


def screen_error_pixels(error_metres, distance_metres):
    return error_metres * pixels_per_metre_at_one_metre() / distance_metres


def allowed_error_metres(max_screen_error_pixels, distance_metres):
    return max_screen_error_pixels * distance_metres / pixels_per_metre_at_one_metre()


def switch_distance(error_metres, radius_metres, previous=0.0):
    derived = error_metres * pixels_per_metre_at_one_metre() / SWITCH_PIXELS
    return max(derived, radius_metres * MIN_DISTANCE_RADII, previous)


def projected_pixels(size_metres, distance_metres):
    return size_metres * pixels_per_metre_at_one_metre() / distance_metres


def crop_pixels(projected):
    wanted = math.ceil(projected * CROP_MARGIN / CROP_STEP) * CROP_STEP
    return int(min(CROP_MAX, max(CROP_MIN, wanted)))


def crop_angle(crop):
    return 2.0 * math.atan((crop / 2.0) / pixels_per_metre_at_one_metre())


def reached(achieved_ratio, target_ratio):
    return achieved_ratio <= target_ratio * REACH_TOLERANCE


def level_plan(config):
    count = config["count"]
    if not 0 <= count <= MAX_LEVELS:
        raise ValueError(f"count must be from 0 to {MAX_LEVELS}")
    if count == 0:
        return []
    ratios = config.get("ratios")
    screen = config.get("maxScreenError")
    distances = config.get("distances")
    if (ratios is None) == (screen is None):
        raise ValueError("give either ratios or maxScreenError")
    if ratios is not None and (len(ratios) != count or not all(0 < ratio < 1 for ratio in ratios) or any(later >= earlier for earlier, later in zip(ratios, ratios[1:]))):
        raise ValueError("ratios needs one value per level, each between 0 and 1 and smaller than the one before")
    if distances is not None and (len(distances) != count or any(later <= earlier for earlier, later in zip(distances, distances[1:])) or distances[0] <= 0):
        raise ValueError("distances needs one value per level, each larger than the one before")
    if screen is not None and distances is None:
        raise ValueError("maxScreenError needs distances")
    plan = []
    for index in range(count):
        plan.append(
            {
                "level": index + 1,
                "ratio": None if ratios is None else float(ratios[index]),
                "distance": None if distances is None else float(distances[index]),
                "budget": None if screen is None else allowed_error_metres(float(screen), float(distances[index])),
            }
        )
    return plan
