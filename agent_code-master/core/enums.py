from enum import Enum


class MissionType(str, Enum):
    EMERGENCY_MEDICAL = "emergency_medical"
    EMERGENCY_SUPPLY = "emergency_supply"
    STANDARD_DELIVERY = "standard_delivery"


class VehicleType(str, Enum):
    UAV = "uav"
    GROUND_VEHICLE = "ground_vehicle"
    AIR_GROUND = "air_ground_coordination"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
