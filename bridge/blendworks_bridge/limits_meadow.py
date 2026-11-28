"""Limits of the meadow fields."""
from .limit_base import PHYSICAL, TIME, limit

MOST_RESPONSES = limit("field_responses", 16, "responses", TIME,
                       "Each response is evaluated at every candidate of its population; sixteen cover every field and effect.")
TALLEST_RESPONSE = limit("response_factor", 4.0, "", PHYSICAL,
                         "A height response past fourfold turns a lawn grass into a reed; another element fits better.")
ELLENBERG_LOWEST = limit("ellenberg_moisture_min", 1.0, "", PHYSICAL, "Ellenberg's moisture scale starts at 1, extreme dryness.")
ELLENBERG_HIGHEST = limit("ellenberg_moisture", 12.0, "", PHYSICAL, "Ellenberg's moisture scale ends at 12, plants under water.")
LEAST_PATH_POINTS = limit("meadow_path_points_min", 2, "points", PHYSICAL, "A path joins at least two points.")
MOST_PATH_POINTS = limit("meadow_path_points", 64, "points", TIME,
                         "Each point costs one least-time search over the path grid; 64 make a dense network.")
