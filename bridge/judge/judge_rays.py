import hashlib
import random
from math import sqrt

DIRECTIONS = 64
DIRECTION_SEED = 20261027
HALF_PI_HIGH = 1.57079632673412561417e00
HALF_PI_LOW = 6.07710050650619224932e-11
TWO_OVER_PI = 6.36619772367581382433e-01
SINE_TERMS = 11
MORTON_BITS = 10


def reduced(angle):
    quadrant = int(angle * TWO_OVER_PI + 0.5) if angle >= 0 else -int(-angle * TWO_OVER_PI + 0.5)
    return quadrant % 4, (angle - quadrant * HALF_PI_HIGH) - quadrant * HALF_PI_LOW


def series_sin(x):
    square = x * x
    term = x
    total = x
    for index in range(1, SINE_TERMS):
        term = -term * square / ((2 * index) * (2 * index + 1))
        total += term
    return total


def series_cos(x):
    square = x * x
    term = 1.0
    total = 1.0
    for index in range(1, SINE_TERMS):
        term = -term * square / ((2 * index - 1) * (2 * index))
        total += term
    return total


def portable_sin_cos(angle):
    quadrant, x = reduced(angle)
    sine, cosine = series_sin(x), series_cos(x)
    if quadrant == 0:
        return sine, cosine
    if quadrant == 1:
        return cosine, -sine
    if quadrant == 2:
        return -sine, -cosine
    return -cosine, sine


def seed_number(text):
    digest = text if len(text) == 64 and all(character in "0123456789abcdef" for character in text) else hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest, 16)


def random_rotation(generator):
    while True:
        a, b, c, d = (2.0 * generator.random() - 1.0 for _ in range(4))
        norm = a * a + b * b + c * c + d * d
        if 1e-4 < norm <= 1.0:
            break
    scale = 1.0 / sqrt(norm)
    w, x, y, z = a * scale, b * scale, c * scale, d * scale
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def normalized(vector):
    length = sqrt(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2])
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def fibonacci_directions(generator, count=DIRECTIONS):
    rotation = random_rotation(generator)
    golden = 3.14159265358979311600e00 * (3.0 - sqrt(5.0))
    directions = []
    for index in range(count):
        z = 1.0 - 2.0 * (index + 0.5) / count
        radius = sqrt(max(0.0, 1.0 - z * z))
        sine, cosine = portable_sin_cos(golden * index)
        point = (cosine * radius, sine * radius, z)
        directions.append(normalized(tuple(row[0] * point[0] + row[1] * point[1] + row[2] * point[2] for row in rotation)))
    return directions


def spread(value):
    result = 0
    for bit in range(MORTON_BITS):
        result |= ((value >> bit) & 1) << (3 * bit)
    return result


def morton_codes(points, low, high):
    cells = (1 << MORTON_BITS) - 1
    scales = [cells / (high[axis] - low[axis]) if high[axis] > low[axis] else 0.0 for axis in range(3)]
    codes = []
    for point in points:
        cell = [min(cells, max(0, int((point[axis] - low[axis]) * scales[axis]))) for axis in range(3)]
        codes.append(spread(cell[0]) | (spread(cell[1]) << 1) | (spread(cell[2]) << 2))
    return codes


def stratified_sample(points, low, high, wanted, generator):
    count = len(points)
    if count <= wanted:
        return [(index, 1.0) for index in range(count)]
    codes = morton_codes(points, low, high)
    order = sorted(range(count), key=lambda index: (codes[index], index))
    chosen = []
    for stratum in range(wanted):
        start = stratum * count // wanted
        end = (stratum + 1) * count // wanted
        size = end - start
        chosen.append((order[start + min(size - 1, int(generator.random() * size))], float(size)))
    chosen.sort()
    return chosen


def fixed_directions():
    return fibonacci_directions(random.Random(DIRECTION_SEED))


def generator_for(seed_text):
    return random.Random(seed_number(seed_text))
