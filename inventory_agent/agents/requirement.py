"""Natural-language requirement extraction with deterministic fallback."""

from __future__ import annotations

import json
import re

from inventory_agent.domain import CapabilityRequest
from inventory_agent.llm.client import LLMClient, MockLLMClient


class RequirementAgent:
    """Convert natural-language inventory requests into validated domain objects."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or MockLLMClient()

    @staticmethod
    def _fallback_parse(description: str) -> CapabilityRequest:
        """Extract required fields deterministically when LLM parsing is unavailable."""

        item_match = re.search(r"(?:item|商品|SKU)[_\s:=号-]*(\d+)", description, re.IGNORECASE)
        store_match = re.search(
            r"(?:store|仓库|分仓|范围)[_\s:=号-]*(all|全国|\d+)",
            description,
            re.IGNORECASE,
        )
        horizon_match = re.search(r"(?:未来|预测|horizon)[^\d]{0,8}(\d+)\s*(?:天|日|days?)", description, re.IGNORECASE)
        nationwide = "全国" in description
        if not item_match or (not store_match and not nationwide):
            raise ValueError("需求中必须明确商品 item/SKU 和仓库 store/分仓。")
        store_code = "all" if nationwide else store_match.group(1)
        accuracy_task = bool(
            re.search(r"(?:WAPE|RMSE|精度|准确率|日需求)", description, re.IGNORECASE)
        )
        return CapabilityRequest(
            description=description,
            item_id=int(item_match.group(1)),
            store_code="all" if store_code.lower() == "全国" else store_code,
            horizon=int(horizon_match.group(1)) if horizon_match else 14,
            task_type="demand_forecast" if accuracy_task else "inventory_target",
            objective="wape" if accuracy_task else "inventory_cost",
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
            "你是库存预测需求分析 Agent。只返回 JSON，保留明确的商品、仓库、预测周期和目标。",
            json.dumps(prompt, ensure_ascii=False),
        )
        try:
            data = json.loads(response)
            task_type = str(data.get("task_type", fallback.task_type))
            if task_type not in {"inventory_target", "demand_forecast"}:
                task_type = fallback.task_type
            objective = "wape" if task_type == "demand_forecast" else "inventory_cost"
            return CapabilityRequest(
                description=description,
                item_id=int(data.get("item_id", fallback.item_id)),
                store_code=str(data.get("store_code", fallback.store_code)),
                horizon=int(data.get("horizon", fallback.horizon)),
                task_type=task_type,
                objective=objective,
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return fallback
