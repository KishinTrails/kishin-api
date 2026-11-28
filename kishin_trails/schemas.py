"""
Pydantic schemas for data validation and serialisation.

Provides request/response models for the API endpoints.
"""

import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    """Schema for the JWT access token response.

    Attributes:
        access_token: The JWT token string.
        token_type: The token type (typically 'bearer').
    """

    access_token: str
    token_type: str


class MapCenterOut(BaseModel):
    """A point in degrees (WGS84)."""

    lat: float
    lon: float


class ClientConfigOut(BaseModel):
    """Settings of this server that the app reads after login.

    Attributes:
        default_center: Where the map opens before the device gives a position
            (DEFAULT_CENTER_LAT, DEFAULT_CENTER_LON).
    """

    default_center: MapCenterOut


class POIBase(BaseModel):
    """Base schema for Point of Interest data.

    Attributes:
        osm_id: OpenStreetMap element ID.
        name: Name of the POI.
        lat: Latitude coordinate.
        lon: Longitude coordinate.
        elevation: Elevation in meters (optional).
    """

    osm_id: int
    name: str | None
    lat: float
    lon: float
    elevation: int | None


class POIOut(POIBase):
    """Schema for POI responses with ORM model support."""
    model_config = ConfigDict(from_attributes=True)


class TileOut(BaseModel):
    """Schema for tile (S2 cell) responses.

    Attributes:
        s2_cell: The S2 cell identifier (hex token).
        tile_type: Type of POI in the tile.
        pois: List of POIs within this tile.
    """

    s2_cell: str
    tile_type: str | None
    pois: List[POIOut] = []

    model_config = ConfigDict(from_attributes=True)


class ExploredTilesOut(BaseModel):
    """Schema for explored tiles response.

    Attributes:
        explored: List of explored S2 cell identifiers (hex tokens).
    """

    explored: List[str]


class NoiseRequest(BaseModel):
    """Request model for noise calculation."""

    cells: List[str]
    scale: int = 50
    octaves: int = 3
    amplitudeDecay: float = 0.5


class NoiseResponse(BaseModel):
    """Response model for single cell noise value."""

    cell: str
    noise: float


class AddExploredTilesRequest(BaseModel):
    """Request model for marking S2 cells as explored.

    Attributes:
        cells: List of S2 cell identifiers (hex tokens).
    """

    cells: List[str]


class SkippedCell(BaseModel):
    """Schema for a cell that was skipped during exploration.

    Attributes:
        cell: The S2 cell identifier.
        reason: Reason for skipping ('invalid' or 'not_found').
    """

    cell: str
    reason: str


class AddExploredTilesResult(BaseModel):
    """Response model for add explored tiles operation.

    Attributes:
        added: List of S2 cell identifiers that were marked as explored.
        skipped: List of cells that were skipped with reasons.
    """

    added: List[str]
    skipped: List[SkippedCell]


# ---------------------------------------------------------------------------
# Athlete data (read-only, from the health-sync database)
#
# Units are metric. GarminDB times are device-local and carry no time zone.
# ---------------------------------------------------------------------------


class ActivitySummaryOut(BaseModel):
    """One Garmin activity in a list.

    ``avg_speed_kmh`` is distance over moving time when Garmin gives no speed.
    """

    model_config = ConfigDict(from_attributes=True)

    activity_id: str
    name: str | None
    sport: str | None
    sub_sport: str | None
    start_time: datetime.datetime | None
    stop_time: datetime.datetime | None
    elapsed_sec: int | None
    moving_sec: int | None
    distance_km: float | None
    ascent_m: float | None
    descent_m: float | None
    avg_hr: int | None
    max_hr: int | None
    calories: int | None
    avg_speed_kmh: float | None
    training_effect: float | None
    anaerobic_training_effect: float | None


class DailyActivitiesOut(BaseModel):
    """Totals of the activities started on one device-local day."""

    model_config = ConfigDict(from_attributes=True)

    date: datetime.date
    count: int
    distance_km: float
    moving_sec: int
    elapsed_sec: int
    ascent_m: float


class HrZoneOut(BaseModel):
    """Time spent in one heart rate zone; ``hr`` is the zone's threshold in bpm."""

    zone: int
    hr: int | None
    time_sec: int | None


class LapOut(BaseModel):
    """One lap of an activity."""

    lap: int
    start_time: datetime.datetime | None
    stop_time: datetime.datetime | None
    elapsed_sec: int | None
    moving_sec: int | None
    distance_km: float | None
    avg_speed_kmh: float | None
    max_speed_kmh: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_cadence: int | None
    max_cadence: int | None
    ascent_m: float | None
    descent_m: float | None
    calories: int | None
    avg_temperature_c: float | None
    hr_zones: List[HrZoneOut]


class RunningDynamicsOut(BaseModel):
    """Running details of an activity (GarminDB's ``steps_activities``)."""

    steps: int | None
    avg_pace_sec_per_km: float | None
    avg_moving_pace_sec_per_km: float | None
    max_pace_sec_per_km: float | None
    avg_steps_per_min: int | None
    max_steps_per_min: int | None
    avg_step_length_mm: float | None
    avg_vertical_ratio_pct: float | None
    avg_vertical_oscillation_mm: float | None
    avg_ground_contact_time_ms: float | None
    vo2_max: float | None


class ActivityDetailOut(ActivitySummaryOut):
    """Every stored field of one activity, with its heart rate zones, running details and laps."""

    description: str | None
    type: str | None
    lap_count: int | None
    device_serial_number: int | None
    self_eval_feel: str | None
    self_eval_effort: str | None
    training_load: float | None
    cycles: float | None
    avg_cadence: int | None
    max_cadence: int | None
    max_speed_kmh: float | None
    avg_rr: float | None
    max_rr: float | None
    avg_temperature_c: float | None
    min_temperature_c: float | None
    max_temperature_c: float | None
    start_lat: float | None
    start_lon: float | None
    stop_lat: float | None
    stop_lon: float | None
    hr_zones_method: str | None
    hr_zones: List[HrZoneOut]
    running: RunningDynamicsOut | None
    laps: List[LapOut]


class LineStringOut(BaseModel):
    """GeoJSON LineString geometry; positions are ``[lon, lat]``."""

    type: Literal["LineString"] = "LineString"
    coordinates: List[List[float]]


class TrackPropertiesOut(BaseModel):
    """Properties of a track feature."""

    activity_id: str
    points: int


class TrackOut(BaseModel):
    """GPS track of an activity as a GeoJSON Feature, readable by Leaflet's ``L.geoJSON``.

    ``bbox`` is ``[min lon, min lat, max lon, max lat]``, or None when the
    activity has no position (a treadmill run).
    """

    type: Literal["Feature"] = "Feature"
    geometry: LineStringOut
    properties: TrackPropertiesOut
    bbox: List[float] | None


class RecordsOut(BaseModel):
    """The records of one activity, one list per field, all lists the same length and in time order.

    ``elapsed_sec`` counts from the first record.
    """

    activity_id: str
    timestamp: List[datetime.datetime | None]
    elapsed_sec: List[float | None]
    distance_km: List[float | None]
    altitude_m: List[float | None]
    hr: List[int | None]
    speed_kmh: List[float | None]
    cadence: List[int | None]
    temperature_c: List[float | None]
    lat: List[float | None]
    lon: List[float | None]


class MeasureDayOut(BaseModel):
    """Withings readings of one calendar day (``TIMEZONE`` setting): the last reading of the day per type.

    The moving averages run over every reading up to that day.
    """

    date: datetime.date
    weight_kg: float | None
    fat_ratio_pct: float | None
    fat_ratio_ema: float | None
    muscle_mass_kg: float | None
    muscle_mass_ema: float | None
    fat_mass_kg: float | None
    fat_free_mass_kg: float | None
    bone_mass_kg: float | None
    hydration_kg: float | None


# ---------------------------------------------------------------------------
# Training plan progression
# ---------------------------------------------------------------------------


class PlanSegmentOut(BaseModel):
    """One segment of a planned run."""

    position: int
    type: str
    duration_sec: int | None
    distance_km: float | None
    rpe_min: int | None
    rpe_max: int | None
    pace_min_km: float | None


class CompletionActivityOut(BaseModel):
    """The Garmin activity that completed a run; None fields when the health database is unavailable."""

    activity_id: str
    name: str | None
    start_time: datetime.datetime | None
    distance_km: float | None
    moving_sec: int | None


class CompletionOut(BaseModel):
    """That a training is done; runs carry the activity and the RPE."""

    completed_at: datetime.datetime
    rpe: int | None
    activity: CompletionActivityOut | None


class PlanTrainingOut(BaseModel):
    """One training of a week, with its targets and its completion."""

    id: int
    position: int
    type: str
    is_tick: bool
    target_distance_km: float | None
    target_duration_sec: int | None
    segments: List[PlanSegmentOut]
    completion: CompletionOut | None


class WeekRunningOut(BaseModel):
    """What Garmin recorded as running in one plan week."""

    run_count: int
    run_km: float
    run_moving_sec: int
    longest_run_km: float | None


class PlanWeekOut(BaseModel):
    """One week of the plan, Monday to Sunday."""

    week_number: int
    phase: str
    start: datetime.date
    end: datetime.date
    trainings: List[PlanTrainingOut]
    running: WeekRunningOut | None


class PlanOut(BaseModel):
    """The active plan and its progression.

    ``current_week`` is the week containing today in ``TIMEZONE``; it is below 1
    before the plan starts and above ``week_count`` after it ends.
    ``health_available`` is False when the Garmin parts could not be read.
    """

    plan_id: int
    name: str
    goal_type: str | None
    target_fat_ratio: float | None
    target_muscle_mass_kg: float | None
    start_date: datetime.date
    current_week: int
    week_count: int
    health_available: bool
    weeks: List[PlanWeekOut]


class CompleteTrainingIn(BaseModel):
    """Body of a completion: a Garmin activity and an RPE for a run, nothing for a tick item."""

    activity_id: str | None = None
    rpe: int | None = Field(default=None, ge=1, le=10)
