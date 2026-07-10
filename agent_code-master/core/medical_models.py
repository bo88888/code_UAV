from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MedicalTaskStatus(str, Enum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    ROUTE_PLANNING = "ROUTE_PLANNING"
    RESOURCE_RESERVING = "RESOURCE_RESERVING"
    READY_FOR_DISPATCH = "READY_FOR_DISPATCH"
    IN_TRANSIT = "IN_TRANSIT"
    RELAY_ARRIVED = "RELAY_ARRIVED"
    BATTERY_SWAPPING = "BATTERY_SWAPPING"
    ARRIVED = "ARRIVED"
    SIGNING = "SIGNING"
    COMPLETED = "COMPLETED"
    EXCEPTION = "EXCEPTION"
    DIVERTED = "DIVERTED"
    RETURNED = "RETURNED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class UAVStatus(str, Enum):
    IDLE = "IDLE"
    STANDBY = "STANDBY"
    REPOSITIONING = "REPOSITIONING"
    RESERVED = "RESERVED"
    LOADING = "LOADING"
    IN_FLIGHT = "IN_FLIGHT"
    BATTERY_SWAPPING = "BATTERY_SWAPPING"
    MAINTENANCE = "MAINTENANCE"
    UNAVAILABLE = "UNAVAILABLE"


class AlertLevel(str, Enum):
    INFO = "INFO"
    ATTENTION = "ATTENTION"
    RESTRICTED = "RESTRICTED"
    CRITICAL = "CRITICAL"


@dataclass
class MedicalNode:
    node_id: str
    name: str
    node_type: str
    level: int
    longitude: float
    latitude: float
    coordinate_source: str = "unknown"
    district: str = ""
    functions: List[str] = field(default_factory=list)
    pad_count: int = 1
    dock_count: int = 0
    charging_slots: int = 0
    battery_swap_slots: int = 0
    cold_storage_slots: int = 0
    handover_cabinets: int = 0
    supports_battery_swap: bool = False
    supports_cold_chain: bool = False
    supports_ground_feeder: bool = False
    weather_station: bool = False
    remote_id_receiver: bool = False
    communication_mode: List[str] = field(default_factory=list)
    status: str = "AVAILABLE"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MedicalNode":
        return cls(**data)


@dataclass
class RouteSegment:
    segment_id: str
    from_node: str
    to_node: str
    distance_km: float
    max_altitude_m: float
    relay_required: bool = False
    route_id: str = ""
    route_name: str = ""
    route_type: str = ""
    cruise_altitude_m: float = 90.0
    corridor_width_m: float = 120.0
    airspace_rule: str = "controlled_corridor"


@dataclass
class MedicalRoute:
    route_id: str
    name: str
    route_type: str
    daily_frequency: str
    cargo_types: List[str]
    cruise_altitude_m: float
    corridor_width_m: float
    airspace_rule: str
    segments: List[RouteSegment]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MedicalRoute":
        route_id = str(data["route_id"])
        segments = []
        for item in data.get("segments", []):
            segments.append(
                RouteSegment(
                    **item,
                    route_id=route_id,
                    route_name=str(data.get("name", route_id)),
                    route_type=str(data.get("route_type", "")),
                    cruise_altitude_m=float(data.get("cruise_altitude_m", 90.0)),
                    corridor_width_m=float(data.get("corridor_width_m", 120.0)),
                    airspace_rule=str(data.get("airspace_rule", "controlled_corridor")),
                )
            )
        return cls(
            route_id=route_id,
            name=str(data.get("name", route_id)),
            route_type=str(data.get("route_type", "urban_loop")),
            daily_frequency=str(data.get("daily_frequency", "on_demand")),
            cargo_types=list(data.get("cargo_types", [])),
            cruise_altitude_m=float(data.get("cruise_altitude_m", 90.0)),
            corridor_width_m=float(data.get("corridor_width_m", 120.0)),
            airspace_rule=str(data.get("airspace_rule", "controlled_corridor")),
            segments=segments,
        )


@dataclass
class MedicalCargo:
    cargo_type: str
    cargo_subtype: str = ""
    weight_kg: float = 0.0
    quantity: int = 1
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    cold_chain_required: bool = False
    cold_chain_safe_minutes: int = 180
    seal_id: str = ""
    biosafety_level: str = "standard"


@dataclass
class DispatchTask:
    task_id: str
    origin_node_id: str
    destination_node_id: str
    cargo: MedicalCargo
    priority: int = 3
    requested_at: str = ""
    ready_at: str = ""
    deadline: str = ""
    emergency: bool = False
    allow_ground_feeder: bool = True
    status: MedicalTaskStatus = MedicalTaskStatus.REQUESTED
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UAVState:
    uav_id: str
    model: str
    home_node_id: str
    current_node_id: str
    status: str
    battery_percent: float
    payload_capacity_kg: float
    loaded_range_km: float
    empty_range_km: float
    cruise_speed_kmh: float
    max_wind_speed_mps: float
    supported_cargo_types: List[str]
    cold_box_types: List[str]
    communication_links: List[str]
    remote_id_enabled: bool
    maintenance_status: str
    available_at: Optional[str] = None
    flight_hours: float = 0.0
    assigned_task_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UAVState":
        return cls(**data)


@dataclass
class FlightLeg:
    leg_id: str
    sequence: int
    route_id: str
    segment_id: str
    from_node_id: str
    to_node_id: str
    distance_km: float
    cruise_altitude_m: float
    corridor_width_m: float
    airspace_rule: str
    relay_required: bool
    assigned_uav_id: str = ""
    backup_uav_id: str = ""
    reposition_required: bool = False
    reposition_distance_km: float = 0.0
    departure_time: str = ""
    arrival_time: str = ""
    estimated_duration_minutes: float = 0.0
    estimated_energy_percent: float = 0.0
    node_operations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DispatchEvent:
    timestamp: str
    event_type: str
    task_id: str
    actor: str
    message: str
    status: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchAlert:
    alert_id: str
    task_id: str
    level: AlertLevel
    alert_type: str
    message: str
    recommended_actions: List[str]
    created_at: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchPlan:
    task: DispatchTask
    status: MedicalTaskStatus
    node_path: List[str]
    route_ids: List[str]
    legs: List[FlightLeg]
    primary_uav_ids: List[str]
    backup_uav_ids: List[str]
    total_distance_km: float
    estimated_total_minutes: float
    estimated_arrival_time: str
    deadline_met: bool
    cold_chain: Dict[str, Any]
    resource_reservations: List[Dict[str, Any]]
    relay_operations: List[Dict[str, Any]]
    events: List[DispatchEvent]
    alerts: List[DispatchAlert]
    dispatch_summary: Dict[str, Any]


def parse_datetime(value: Optional[str], default: Optional[datetime] = None) -> datetime:
    if value:
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
    return default or datetime.now().astimezone()


def isoformat(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds") if value.tzinfo else value.isoformat(timespec="seconds")


def to_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    return value
