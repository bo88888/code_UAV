from __future__ import annotations

from typing import Dict, List

from core.medical_models import DispatchAlert


class EmergencyResponseAgent:
    """Maps operational alerts to medical-delivery-specific contingency actions."""

    POLICY: Dict[str, List[str]] = {
        "ROUTE_DEVIATION": [
            "立即执行航线回归或切换备用走廊",
            "若偏离持续扩大，选择最近备降节点",
            "通知调度中心和空域监管接口",
        ],
        "LOW_BATTERY": [
            "锁定最近具备换电能力的节点",
            "启用备用无人机准备接管后续航段",
            "无法安全到达时执行就近备降",
        ],
        "COMMUNICATION_LOST": [
            "切换北斗备份链路",
            "进入预设失链航线并保持安全高度",
            "超过失链阈值后返航或备降",
        ],
        "ALTITUDE_VIOLATION": [
            "立即恢复航线批准高度层",
            "暂停同走廊其他无人机进入冲突区",
            "记录超高事件用于运行审计",
        ],
        "COLD_CHAIN_TEMPERATURE_OUT_OF_RANGE": [
            "改降最近具备冷链交接能力的医疗节点",
            "通知医院准备质量复核和替代物资",
            "保全温度、封签和轨迹证据链",
        ],
        "NODE_UNAVAILABLE": [
            "切换备用起降或中继节点",
            "重新计算后续航段和时间窗",
            "必要时启动地面短驳接续",
        ],
        "WEATHER_RESTRICTED": [
            "暂停受影响航段",
            "评估等待、绕飞或地面接驳方案",
            "紧急任务启动备用节点和备用机联动",
        ],
    }

    def recommend(self, alert_type: str) -> List[str]:
        return list(self.POLICY.get(alert_type, ["请求人工复核", "保持任务安全状态", "记录完整事件链"]))

    def enrich(self, alert: DispatchAlert) -> DispatchAlert:
        if not alert.recommended_actions:
            alert.recommended_actions = self.recommend(alert.alert_type)
        return alert
