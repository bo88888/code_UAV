from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Dict, List

from core.medical_models import MedicalNode, MedicalRoute, UAVState, to_primitive


class MedicalDispatchRepository:
    """Loads static network data and keeps the mutable fleet snapshot in memory."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[1]
        self.data_dir = self.base_dir / "data"
        self._lock = RLock()
        self._nodes: Dict[str, MedicalNode] = {}
        self._routes: Dict[str, MedicalRoute] = {}
        self._fleet: Dict[str, UAVState] = {}
        self._load_all()

    def _read_json(self, filename: str) -> dict:
        path = self.data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"medical dispatch data not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_all(self) -> None:
        node_payload = self._read_json("handan_medical_nodes.json")
        route_payload = self._read_json("handan_medical_routes.json")
        fleet_payload = self._read_json("uav_fleet.json")
        self._nodes = {
            item["node_id"]: MedicalNode.from_dict(item)
            for item in node_payload.get("nodes", [])
        }
        self._routes = {
            item["route_id"]: MedicalRoute.from_dict(item)
            for item in route_payload.get("routes", [])
        }
        self._fleet = {
            item["uav_id"]: UAVState.from_dict(item)
            for item in fleet_payload.get("fleet", [])
        }

    def reload(self) -> None:
        with self._lock:
            self._load_all()

    def nodes(self) -> Dict[str, MedicalNode]:
        with self._lock:
            return deepcopy(self._nodes)

    def routes(self) -> Dict[str, MedicalRoute]:
        with self._lock:
            return deepcopy(self._routes)

    def fleet(self) -> Dict[str, UAVState]:
        with self._lock:
            return deepcopy(self._fleet)

    def get_node(self, node_id: str) -> MedicalNode:
        with self._lock:
            if node_id not in self._nodes:
                raise KeyError(f"unknown medical node: {node_id}")
            return deepcopy(self._nodes[node_id])

    def get_uav(self, uav_id: str) -> UAVState:
        with self._lock:
            if uav_id not in self._fleet:
                raise KeyError(f"unknown UAV: {uav_id}")
            return deepcopy(self._fleet[uav_id])

    def update_uav(self, uav: UAVState) -> None:
        with self._lock:
            self._fleet[uav.uav_id] = deepcopy(uav)

    def update_fleet(self, fleet: Dict[str, UAVState]) -> None:
        with self._lock:
            self._fleet = deepcopy(fleet)

    def network_payload(self) -> dict:
        with self._lock:
            return {
                "nodes": [to_primitive(item) for item in self._nodes.values()],
                "routes": [to_primitive(item) for item in self._routes.values()],
                "summary": {
                    "node_count": len(self._nodes),
                    "route_count": len(self._routes),
                    "core_hubs": sum(1 for item in self._nodes.values() if item.level == 1),
                    "urban_nodes": sum(1 for item in self._nodes.values() if item.level == 2),
                    "county_or_relay_nodes": sum(1 for item in self._nodes.values() if item.level == 3),
                },
            }

    def fleet_payload(self) -> List[dict]:
        with self._lock:
            return [to_primitive(item) for item in self._fleet.values()]
