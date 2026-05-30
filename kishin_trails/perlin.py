"""
Perlin noise implementation with frontend parity via S2 cells.

Uses the same permutation table and algorithms as the JavaScript frontend
to guarantee identical noise values for the same input coordinates.

Coordinate pipeline
-------------------
S2 cell token
  → centre lat/lng  (via ``s2CellIdToLatLng``)
  → Web Mercator (EPSG:3857) in metres  (via pyproj)
  → normalised [0, 1] Mercator space  (matching MapLibre's MercatorCoordinate)
  → multi-octave Perlin noise  → [0, 1] scalar

Normalization
-------------
Raw multi-octave Perlin output is **not** bounded to [-1, 1]; the true range
is [-max_amplitude, +max_amplitude] where::

    max_amplitude = sum(amplitudeDecay**i for i in range(octaves))

``getNoiseValue`` divides by ``max_amplitude`` before the [0, 1] shift, so
the returned value is always in [0, 1] regardless of octave/decay settings.
"""

import math

from typing import Tuple

from pyproj import Transformer

from kishin_trails.noise_cache import getCachedNoise, setCachedNoise
from kishin_trails.config import settings
from kishin_trails.utils import s2CellIdToLatLng

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Semi-circumference of the Earth at the equator in EPSG:3857 (Web Mercator),
# metres.  This is the authoritative bound of the projection: the coordinate
# space spans [-MERCATOR_HALF_WORLD, +MERCATOR_HALF_WORLD] on both axes.
# Source: EPSG registry / OGC Web Mercator specification.
MERCATOR_HALF_WORLD: float = 20037508.342789244

# Module-level pyproj transformer (constructed once, thread-safe for reads).
# ``always_xy=True`` ensures the axis order is (longitude, latitude) —
# i.e. (x, y) — regardless of the CRS definition, matching JS / MapLibre
# conventions.
_WGS84_TO_MERC: Transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:3857",
    always_xy=True,
)

# ---------------------------------------------------------------------------
# Classic Perlin noise primitives
# ---------------------------------------------------------------------------

#: Reference permutation table (256 values, duplicated to avoid modular
#: indexing at lookup time).  Must be identical to the frontend implementation.
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

PERMUTATION: list[int] = PERMUTATION_BASE + PERMUTATION_BASE

# pylint: disable=invalid-name


def fade(t: float) -> float:
    """
    Quintic smoothstep (Ken Perlin's improved fade curve).

    Computes ``6t⁵ − 15t⁴ + 10t³``, which has zero first and second
    derivatives at ``t = 0`` and ``t = 1``.  This eliminates the visual
    interpolation artefacts produced by the cubic smoothstep used in
    classic Perlin noise.

    Identical to the frontend expression ``t*t*t*(t*(t*6 - 15) + 10)``.

    Args:
        t: Input value, typically in [0, 1].

    Returns:
        Smoothed value in [0, 1].
    """
    return t * t * t * (t * (t*6 - 15) + 10)


def lerp(a: float, b: float, t: float) -> float:
    """
    Linear interpolation between *a* and *b*.

    Computes ``a + t * (b − a)``, identical to the frontend implementation.

    Args:
        a: Start value (returned when ``t == 0``).
        b: End value (returned when ``t == 1``).
        t: Interpolation factor.

    Returns:
        Interpolated value.
    """
    return a + t * (b-a)


def grad(hash_val: int, x: float, y: float) -> float:
    """
    Select and apply one of four gradient vectors based on *hash_val*.

    The lower two bits of *hash_val* select a gradient direction from
    ``{(+x,+y), (-x,+y), (+x,-y), (-x,-y)}``, matching the 2-D gradient
    table used by the frontend.

    Args:
        hash_val: Hash value whose lower two bits determine the gradient.
        x: Distance from the grid corner along the X axis.
        y: Distance from the grid corner along the Y axis.

    Returns:
        Dot product of the chosen pseudo-random gradient with the distance
        vector ``(x, y)``.
    """
    h = hash_val & 3
    gx = x if (h & 1) == 0 else -x
    gy = y if (h & 2) == 0 else -y
    return gx + gy


def perlin(x: float, y: float) -> float:
    """
    Classic 2-D Perlin noise at coordinates ``(x, y)``.

    Algorithm (identical to the frontend):

    1. Locate the unit-square grid cell that contains ``(x, y)``.
    2. Compute the local fractional offsets within that cell.
    3. Apply the quintic fade curve to both offsets.
    4. Hash the four corner integers via the permutation table.
    5. Compute gradient contributions at all four corners.
    6. Bilinearly interpolate using the faded offsets.

    Args:
        x: X coordinate in noise space.
        y: Y coordinate in noise space.

    Returns:
        Raw noise value.  Range is approximately [-1, 1] for a single
        octave but is **not** strictly bounded; use ``getNoiseValue`` for
        a normalised result.
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
        lerp(
            grad(
                PERMUTATION[A],
                x,
                y,
            ),
            grad(
                PERMUTATION[B],
                x - 1,
                y,
            ),
            u,
        ),
        lerp(
            grad(
                PERMUTATION[A + 1],
                x,
                y - 1,
            ),
            grad(
                PERMUTATION[B + 1],
                x - 1,
                y - 1,
            ),
            u,
        ),
        v,
    )


# pylint: enable=invalid-name

# ---------------------------------------------------------------------------
# Multi-octave noise
# ---------------------------------------------------------------------------


def getNoiseValue(
    mercX: float,
    mercY: float,
    scale: int | None = None,
    octaves: int | None = None,
    amplitudeDecay: float | None = None,
) -> float:
    """
    Multi-octave Perlin noise at normalised Mercator coordinates.

    Replicates the frontend's ``getNoiseValue`` function:

    * Initial frequency = ``scale × 500``.
    * Each octave doubles the frequency and multiplies the amplitude by
      ``amplitudeDecay``.
    * The raw sum is divided by the total possible amplitude
      (``Σ amplitudeDecay^i`` for ``i`` in ``[0, octaves)``) before the
      final [0, 1] shift, guaranteeing the result is always in [0, 1].

    .. note::
        If the JavaScript frontend does **not** perform this amplitude
        normalisation, parity will diverge for multi-octave configurations.
        Verify the frontend implementation when changing octave settings.

    Args:
        mercX: Normalised Mercator X coordinate in [0, 1].
        mercY: Normalised Mercator Y coordinate in [0, 1].
        scale: Noise scale factor.  Defaults to ``settings.NOISE_SCALE``.
        octaves: Number of octaves to accumulate.
            Defaults to ``settings.NOISE_OCTAVES``.
        amplitudeDecay: Per-octave amplitude multiplier (persistence).
            Defaults to ``settings.NOISE_AMPLITUDE_DECAY``.

    Returns:
        Noise value in [0, 1].
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

    # Normalise: divide by the geometric sum of amplitudes so that the result
    # is in [-1, 1], then shift to [0, 1].
    # Without this step, multi-octave sums exceed [-1, 1] and the final value
    # can fall outside [0, 1].
    maxAmplitude = sum(amplitudeDecay**i for i in range(octaves))
    return (value/maxAmplitude + 1) / 2


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


def latLngToMercator(lat: float, lng: float) -> Tuple[float, float]:
    """
    Convert WGS84 latitude/longitude to normalised Web Mercator coordinates.

    Uses a module-level ``pyproj.Transformer`` (EPSG:4326 → EPSG:3857) to
    project the point, then normalises the result to [0, 1] using the
    ``MERCATOR_HALF_WORLD`` bound — matching the behaviour of MapLibre's
    ``MercatorCoordinate.fromLngLat()``.

    This implementation replaces an earlier ``geopandas``-based approach.
    The ``GeoDataFrame`` construction overhead was significant for per-cell
    calls; the ``Transformer`` object is constructed once at module load and
    reused for every call.

    Args:
        lat: Latitude in degrees (WGS84).
        lng: Longitude in degrees (WGS84).

    Returns:
        ``(mercX, mercY)`` in [0, 1], where ``(0, 0)`` is the top-left
        corner of the Web Mercator extent (north-west) and ``(1, 1)`` is
        the bottom-right corner (south-east), matching MapLibre's convention.
    """
    mercX_m, mercY_m = _WGS84_TO_MERC.transform(lng, lat)  # note: x=lng, y=lat
    world_size = MERCATOR_HALF_WORLD * 2
    mercX = (mercX_m+MERCATOR_HALF_WORLD) / world_size
    mercY = (MERCATOR_HALF_WORLD-mercY_m) / world_size

    return mercX, mercY


# ---------------------------------------------------------------------------
# S2 cell helpers
# ---------------------------------------------------------------------------


def getNoiseForCell(
    cell: str,
    scale: int | None = None,
    octaves: int | None = None,
    amplitudeDecay: float | None = None,
) -> float:
    """
    Return the Perlin noise value for an S2 cell, with caching.

    The pipeline is:

    1. Check the noise cache; return immediately on a hit.
    2. Resolve the cell token to a centre lat/lng via ``s2CellIdToLatLng``.
    3. Convert to normalised Mercator coordinates.
    4. Compute multi-octave Perlin noise.
    5. Persist the result to the cache and return it.

    Args:
        cell: S2 cell hex token.
        scale: Noise scale factor.  Defaults to ``settings.NOISE_SCALE``.
        octaves: Number of noise octaves.  Defaults to ``settings.NOISE_OCTAVES``.
        amplitudeDecay: Per-octave amplitude multiplier.
            Defaults to ``settings.NOISE_AMPLITUDE_DECAY``.

    Returns:
        Noise value in [0, 1].
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

    lat, lng = s2CellIdToLatLng(cell)
    mercX, mercY = latLngToMercator(lat, lng)
    value = getNoiseValue(mercX, mercY, scale, octaves, amplitudeDecay)

    setCachedNoise(cell, scale, octaves, amplitudeDecay, value)
    return value


def isCellActive(
    cell: str,
    scale: int | None = None,
    octaves: int | None = None,
    amplitudeDecay: float | None = None,
) -> bool:
    """
    Return whether an S2 cell's noise value exceeds the activity threshold.

    A cell is considered *active* when its noise value is strictly greater
    than ``settings.NOISE_ACTIVITY_THRESHOLD``.

    Args:
        cell: S2 cell hex token.
        scale: Noise scale factor.  Defaults to ``settings.NOISE_SCALE``.
        octaves: Number of noise octaves.  Defaults to ``settings.NOISE_OCTAVES``.
        amplitudeDecay: Per-octave amplitude multiplier.
            Defaults to ``settings.NOISE_AMPLITUDE_DECAY``.

    Returns:
        ``True`` if ``noiseValue > settings.NOISE_ACTIVITY_THRESHOLD``.
    """
    noiseValue = getNoiseForCell(cell, scale, octaves, amplitudeDecay)
    return noiseValue > settings.NOISE_ACTIVITY_THRESHOLD
