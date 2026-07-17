"""Natural-language requirement extraction with deterministic fallback."""

from __future__ import annotations

import json
import re

from inventory_agent.domain import CapabilityRequest
from inventory_agent.llm.client import LLMClient, MockLLMClient


class RequirementAgent:
    """Convert natural-language inventory requests into validated domain objects."""

    TASK_OBJECTIVES = {
        "inventory_target": "inventory_cost",
        "demand_forecast": "wape",
        "intermittent_demand": "mae",
    }

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or MockLLMClient()

    @staticmethod
    def _fallback_parse(description: str) -> CapabilityRequest:
        """Extract required fields deterministically when LLM parsing is unavailable."""

        item_match = re.search(
            r"(?:item|商品|货品|SKU)[_\s:=号#-]*(\d+)",
            description,
            re.IGNORECASE,
        )
        store_match = re.search(
            r"(?:store|仓库|分仓|区域)[_\s:=号#-]*(all|全国|[A-Za-z0-9_-]+)",
            description,
            re.IGNORECASE,
        )
        horizon_match = re.search(
            r"(?:未来|预测|horizon)[^\d]{0,8}(\d+)\s*(?:天|日|days?)",
            description,
            re.IGNORECASE,
        )
        nationwide = "全国" in description
        if not item_match or (not store_match and not nationwide):
            raise ValueError("需求中必须明确商品 item/SKU 和仓库 store/分仓。")
        store_code = "all" if nationwide else store_match.group(1)
        intermittent_task = bool(
            re.search(
                r"(?:间歇|稀疏|大量零|零需求|备件|Croston|intermittent|sparse)",
                description,
                re.IGNORECASE,
            )
        )
        accuracy_task = bool(
            re.search(
                r"(?:WAPE|RMSE|sMAPE|精度|准确率|日需求)",
                description,
                re.IGNORECASE,
            )
        )
        task_type = (
            "intermittent_demand"
            if intermittent_task
            else "demand_forecast"
            if accuracy_task
            else "inventory_target"
        )
        return CapabilityRequest(
            description=description,
            item_id=int(item_match.group(1)),
            store_code="all" if store_code.lower() == "全国" else store_code,
            horizon=int(horizon_match.group(1)) if horizon_match else 14,
            task_type=task_type,
            objective=RequirementAgent.TASK_OBJECTIVES[task_type],
        )

    def parse(self, description: str) -> CapabilityRequest:
        """Parse a request with deterministic defaults and optional LLM refinement."""

        fallback = self._fallback_parse(description)
        if isinstance(self.llm, MockLLMClient):
            return fallback
        prompt = {
            "description": description,
            "fallback": {
                "item_id": fallback.item_id,
                "store_code": fallback.store_code,
                "horizon": fallback.horizon,
                "task_type": fallback.task_type,
                "objective": fallback.objective,
            },
        }
        response = self.llm.complete(
            (
                "你是库存预测需求分析 Agent。只返回 JSON，保留明确的商品、"
                "仓库、预测周期、task_type 和目标。task_type 可选 "
                "inventory_target、demand_forecast、intermittent_demand。"
            ),
            json.dumps(prompt, ensure_ascii=False),
        )
        try:
            data = json.loads(response)
            task_type = str(data.get("task_type", fallback.task_type))
            if task_type not in self.TASK_OBJECTIVES:
                task_type = fallback.task_type
            return CapabilityRequest(
                description=description,
                item_id=int(data.get("item_id", fallback.item_id)),
                store_code=str(data.get("store_code", fallback.store_code)),
                horizon=int(data.get("horizon", fallback.horizon)),
                task_type=task_type,
                objective=self.TASK_OBJECTIVES[task_type],
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return fallback
