"""
Perlin Noise implementation with 100% frontend parity.

Uses the same permutation table and algorithms as the JavaScript frontend
to ensure identical noise values for the same coordinates.
"""

import math
import geopandas as gpd

from shapely.geometry import Point
from typing import Tuple

from kishin_trails.noise_cache import getCachedNoise, setCachedNoise
from kishin_trails.config import settings
import h3

# Exact permutation table from frontend (256 elements)
# This must match PerlinNoiseOverlay.vue exactly for parity
PERMUTATION_BASE = [
    151,
    160,
    137,
    91,
    90,
    15,
    131,
    13,
    201,
    95,
    96,
    53,
    194,
    233,
    7,
    225,
    140,
    36,
    103,
    30,
    69,
    142,
    8,
    99,
    37,
    240,
    21,
    10,
    23,
    190,
    6,
    148,
    247,
    120,
    234,
    75,
    0,
    26,
    197,
    62,
    94,
    252,
    219,
    203,
    117,
    35,
    11,
    32,
    57,
    177,
    33,
    88,
    237,
    149,
    56,
    87,
    174,
    20,
    125,
    136,
    171,
    168,
    68,
    175,
    74,
    165,
    71,
    134,
    139,
    48,
    27,
    166,
    77,
    146,
    158,
    231,
    83,
    111,
    229,
    122,
    60,
    211,
    133,
    230,
    220,
    105,
    92,
    41,
    55,
    46,
    245,
    40,
    244,
    102,
    143,
    54,
    65,
    25,
    63,
    161,
    1,
    216,
    80,
    73,
    209,
    76,
    132,
    187,
    208,
    89,
    18,
    169,
    200,
    196,
    135,
    130,
    116,
    188,
    159,
    86,
    164,
    100,
    109,
    198,
    173,
    186,
    3,
    64,
    52,
    217,
    226,
    250,
    124,
    123,
    5,
    202,
    38,
    147,
    118,
    126,
    255,
    82,
    85,
    212,
    207,
    206,
    59,
    227,
    47,
    16,
    58,
    17,
    182,
    189,
    28,
    42,
    223,
    183,
    170,
    213,
    119,
    248,
    152,
    2,
    44,
    154,
    163,
    70,
    221,
    153,
    101,
    155,
    167,
    43,
    172,
    9,
    129,
    22,
    39,
    253,
    19,
    98,
    108,
    110,
    79,
    113,
    224,
    232,
    178,
    185,
    112,
    104,
    218,
    246,
    97,
    228,
    251,
    34,
    242,
    193,
    238,
    210,
    144,
    12,
    191,
    179,
    162,
    241,
    81,
    51,
    145,
    235,
    249,
    14,
    239,
    107,
    49,
    192,
    214,
    31,
    181,
    199,
    106,
    157,
    184,
    84,
    204,
    176,
    115,
    121,
    50,
    45,
    127,
    4,
    150,
    254,
    138,
    236,
    205,
    93,
    222,
    114,
    67,
    29,
    24,
    72,
    243,
    141,
    128,
    195,
    78,
    66,
    215,
    61,
    156,
    180
]

# Duplicate permutation table for wraparound (matches frontend implementation)
PERMUTATION = PERMUTATION_BASE + PERMUTATION_BASE


# pylint: disable=invalid-name
def fade(t: float) -> float:
    """
    Smoothstep function for smooth interpolation.

    This is the exact same fade function as the frontend:
    t*t*t*(t*(t*6 - 15) + 10)

    Args:
        t: Input value (typically between 0 and 1)

    Returns:
        Smoothed value
    """
    return t * t * t * (t * (t*6 - 15) + 10)


def lerp(a: float, b: float, t: float) -> float:
    """
    Linear interpolation between two values.

    This is the exact same lerp function as the frontend:
    a + t * (b - a)

    Args:
        a: First value
        b: Second value
        t: Interpolation factor (0 = all a, 1 = all b)

    Returns:
        Interpolated value
    """
    return a + t * (b-a)


def grad(hash_val: int, x: float, y: float) -> float:
    """
    Compute gradient based on hash value.

    This picks one of 4 directions based on the hash, exactly like the frontend.

    Args:
        hash_val: Hash value to determine gradient direction
        x: Distance in X direction
        y: Distance in Y direction

    Returns:
        Gradient value
    """
    h = hash_val & 3
    return ((h & 1) == 0 and x or -x) + ((h & 2) == 0 and y or -y)


def perlin(x: float, y: float) -> float:
    """
    Classic Perlin noise at coordinates (x, y).

    Uses the exact same algorithm as the frontend for parity:
    1. Find grid cell
    2. Calculate local coordinates within cell
    3. Apply fade function for smoothness
    4. Get gradients at 4 corners
    5. Interpolate between corners

    Args:
        x: X coordinate in noise space
        y: Y coordinate in noise space

    Returns:
        Noise value (typically in range [-1, 1] before normalization)
    """
    X = int(math.floor(x)) & 255
    Y = int(math.floor(y)) & 255

    x -= math.floor(x)
    y -= math.floor(y)

    u = fade(x)
    v = fade(y)

    A = PERMUTATION[X] + Y
    B = PERMUTATION[X + 1] + Y

    return lerp(
        lerp(grad(PERMUTATION[A],
                  x,
                  y),
             grad(PERMUTATION[B],
                  x - 1,
                  y),
             u),
        lerp(grad(PERMUTATION[A + 1],
                  x,
                  y - 1),
             grad(PERMUTATION[B + 1],
                  x - 1,
                  y - 1),
             u),
        v
    )


# pylint: enable=invalid-name


def getNoiseValue(mercX: float, mercY: float, scale: int | None = None, octaves: int | None = None, amplitudeDecay: float | None = None) -> float:
    """
    Multi-octave Perlin noise at Mercator coordinates.

    This replicates the frontend's getNoiseValue function exactly:
    - Configurable octaves of noise
    - frequency = scale * 500
    - amplitude starts at 1.0, multiplied by amplitudeDecay each octave
    - frequency multiplied by 2 each octave
    - Final normalization: (value + 1) / 2

    Args:
        mercX: X coordinate in Mercator space (0-1 range, like MapLibre)
        mercY: Y coordinate in Mercator space (0-1 range, like MapLibre)
        scale: Noise scale factor (defaults to settings.NOISE_SCALE)
        octaves: Number of noise octaves (defaults to settings.NOISE_OCTAVES)
        amplitudeDecay: Amplitude decay factor per octave (defaults to settings.NOISE_AMPLITUDE_DECAY)

    Returns:
        Noise value in range [0, 1]
    """
    if scale is None:
        scale = settings.NOISE_SCALE
    if octaves is None:
        octaves = settings.NOISE_OCTAVES
    if amplitudeDecay is None:
        amplitudeDecay = settings.NOISE_AMPLITUDE_DECAY

    value = 0.0
    amplitude = 1.0
    frequency = scale * 500

    for _ in range(octaves):
        value += perlin(mercX * frequency, mercY * frequency) * amplitude
        amplitude *= amplitudeDecay
        frequency *= 2

    return (value+1) / 2


def latLngToMercator(lat: float, lng: float) -> Tuple[float, float]:
    """
    Convert latitude/longitude to Web Mercator coordinates (0-1 range).

    Uses geopandas to transform coordinates from WGS84 (EPSG:4326) to
    Web Mercator (EPSG:3857), then normalizes to 0-1 range to match
    MapLibre's MercatorCoordinate.fromLngLat().

    Args:
        lat: Latitude in degrees
        lng: Longitude in degrees

    Returns:
        Tuple of (merc_x, merc_y) in 0-1 range, matching MapLibre's output
    """
    # Create point in WGS84 (EPSG:4326)
    point = Point(lng, lat)
    gdf = gpd.GeoDataFrame([{
        'geometry': point
    }],
                           crs='EPSG:4326')

    # Transform to Web Mercator (EPSG:3857)
    gdfMerc = gdf.to_crs('EPSG:3857')
    mercPoint = gdfMerc.iloc[0]['geometry']

    # Normalize to 0-1 range
    # Web Mercator bounds: -20037508.34 to +20037508.34 meters
    # This matches MapLibre's coordinate system
    worldSize = 20037508.34 * 2
    mercX = (mercPoint.x + 20037508.34) / worldSize
    mercY = (20037508.34 - mercPoint.y) / worldSize  # Y is inverted

    return mercX, mercY


def getNoiseForCell(cell: str, scale: int | None = None, octaves: int | None = None, amplitudeDecay: float | None = None) -> float:
    """
    Get Perlin noise value for an H3 cell by sampling its center.

    This is the main entry point for getting noise values for H3 cells.
    It:
    1. Gets the cell center coordinates using h3.cell_to_latlng()
    2. Converts to Mercator coordinates
    3. Computes multi-octave Perlin noise
    4. Returns normalized value in [0, 1] range

    Args:
        cell: H3 cell index (resolution 10)
        scale: Noise scale factor (defaults to settings.NOISE_SCALE)
        octaves: Number of noise octaves (defaults to settings.NOISE_OCTAVES)
        amplitudeDecay: Amplitude decay factor per octave (defaults to settings.NOISE_AMPLITUDE_DECAY)

    Returns:
        Noise value in range [0, 1]
    """
    if scale is None:
        scale = settings.NOISE_SCALE
    if octaves is None:
        octaves = settings.NOISE_OCTAVES
    if amplitudeDecay is None:
        amplitudeDecay = settings.NOISE_AMPLITUDE_DECAY

    cached = getCachedNoise(cell, scale, octaves, amplitudeDecay)
    if cached is not None:
        return cached

    lat, lng = h3.cell_to_latlng(cell)
    mercX, mercY = latLngToMercator(lat, lng)
    value = getNoiseValue(mercX, mercY, scale, octaves, amplitudeDecay)

    setCachedNoise(cell, scale, octaves, amplitudeDecay, value)
    return value


def isCellActive(cell: str, scale: int | None = None, octaves: int | None = None, amplitudeDecay: float | None = None) -> bool:
    """
    Check if an H3 cell is active based on its Perlin noise value.

    A cell is considered active if its noise value exceeds the configured threshold.

    Args:
        cell: H3 cell index (resolution 10)
        scale: Noise scale factor (defaults to settings.NOISE_SCALE)
        octaves: Number of noise octaves (defaults to settings.NOISE_OCTAVES)
        amplitudeDecay: Amplitude decay factor per octave (defaults to settings.NOISE_AMPLITUDE_DECAY)

    Returns:
        True if the cell is active (noise > threshold), False otherwise
    """
    noiseValue = getNoiseForCell(cell, scale, octaves, amplitudeDecay)
    return noiseValue > settings.NOISE_ACTIVITY_THRESHOLD
