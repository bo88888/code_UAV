import unittest
from datetime import datetime, timedelta

from core.medical_models import MedicalTaskStatus
from scheduler.medical_dispatch_center import MedicalDispatchCenter
from services.medical_dispatch_repository import MedicalDispatchRepository


class MedicalDispatchCenterTest(unittest.TestCase):
    def setUp(self):
        self.repository = MedicalDispatchRepository()
        self.center = MedicalDispatchCenter(self.repository)

    @staticmethod
    def future(minutes: int) -> str:
        return (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat(timespec="seconds")

    def test_network_contains_hierarchical_nodes_and_l1_l8(self):
        payload = self.repository.network_payload()
        self.assertGreaterEqual(payload["summary"]["node_count"], 12)
        self.assertEqual(payload["summary"]["route_count"], 8)
        self.assertEqual({item["route_id"] for item in payload["routes"]}, {f"L{i}" for i in range(1, 9)})

    def test_l1_direct_blood_dispatch(self):
        plan = self.center.submit(
            {
                "task_id": "TEST-L1-BLOOD",
                "origin_node_id": "HD_BLOOD_CENTER",
                "destination_node_id": "HD_CENTER_WEST",
                "cargo_type": "blood",
                "cargo_subtype": "red_cells",
                "cargo_weight_kg": 3.0,
                "priority": 5,
                "emergency": True,
                "deadline": self.future(90),
            }
        )
        self.assertEqual(plan["status"], MedicalTaskStatus.READY_FOR_DISPATCH.value)
        self.assertEqual(plan["route_ids"], ["L1"])
        self.assertEqual(len(plan["legs"]), 1)
        self.assertTrue(plan["cold_chain"]["feasible"])
        self.assertTrue(plan["backup_uav_ids"])

    def test_l6_multi_leg_relay_dispatch(self):
        plan = self.center.submit(
            {
                "task_id": "TEST-L6-WUAN",
                "origin_node_id": "HD_FIRST_HOSPITAL",
                "destination_node_id": "WUAN_HOSPITAL",
                "cargo_type": "emergency_medicine",
                "cargo_subtype": "thrombolytic",
                "cargo_weight_kg": 4.0,
                "priority": 5,
                "emergency": True,
                "deadline": self.future(180),
            }
        )
        self.assertEqual(plan["status"], MedicalTaskStatus.READY_FOR_DISPATCH.value)
        self.assertEqual(plan["route_ids"], ["L6"])
        self.assertEqual(len(plan["legs"]), 3)
        self.assertGreaterEqual(len(plan["relay_operations"]), 2)
        self.assertIn("TAOYI_RELAY", plan["node_path"])
        self.assertGreaterEqual(len(plan["primary_uav_ids"]), 1)

    def test_batch_dispatch_uses_priority_ranking_and_shared_fleet(self):
        result = self.center.submit_batch(
            [
                {
                    "task_id": "TEST-BATCH-SAMPLE",
                    "origin_node_id": "HD_FIRST_HOSPITAL",
                    "destination_node_id": "YONGNIAN_HOSPITAL",
                    "cargo_type": "sample",
                    "cargo_weight_kg": 2.0,
                    "priority": 3,
                    "deadline": self.future(240),
                },
                {
                    "task_id": "TEST-BATCH-BLOOD",
                    "origin_node_id": "HD_BLOOD_CENTER",
                    "destination_node_id": "HD_CENTER_WEST",
                    "cargo_type": "blood",
                    "cargo_weight_kg": 2.5,
                    "priority": 5,
                    "emergency": True,
                    "deadline": self.future(60),
                },
            ]
        )
        self.assertEqual(result["submitted"], 2)
        self.assertEqual(result["plans"][0]["task"]["task_id"], "TEST-BATCH-BLOOD")
        self.assertEqual(result["dispatch_mode"], "priority_aware_multi_task_batch")

    def test_telemetry_alert_and_handover_close_loop(self):
        plan = self.center.submit(
            {
                "task_id": "TEST-MONITOR",
                "origin_node_id": "HD_BLOOD_CENTER",
                "destination_node_id": "HD_CENTER_WEST",
                "cargo_type": "blood",
                "cargo_weight_kg": 2.0,
                "priority": 5,
                "emergency": True,
                "deadline": self.future(90),
            }
        )
        telemetry = self.center.update_telemetry(
            "TEST-MONITOR",
            {
                "uav_id": plan["primary_uav_ids"][0],
                "leg_id": plan["legs"][0]["leg_id"],
                "altitude_m": 90,
                "battery_percent": 15,
                "route_deviation_m": 18,
                "communication_ok": True,
                "remote_id_ok": True,
                "temperature_c": 8.5,
            },
        )
        alert_types = {item["alert_type"] for item in telemetry["alerts"]}
        self.assertIn("LOW_BATTERY", alert_types)
        self.assertIn("ROUTE_DEVIATION", alert_types)
        self.assertIn("COLD_CHAIN_TEMPERATURE_OUT_OF_RANGE", alert_types)
        self.assertEqual(telemetry["status"], MedicalTaskStatus.EXCEPTION.value)

        handover = self.center.complete_handover(
            "TEST-MONITOR",
            {
                "receiver_name": "测试接收人员",
                "seal_verified": True,
                "temperature_verified": False,
                "remarks": "异常任务人工复核后完成交接",
            },
        )
        self.assertEqual(handover["status"], MedicalTaskStatus.COMPLETED.value)


if __name__ == "__main__":
    unittest.main()
