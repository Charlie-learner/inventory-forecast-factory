"""Natural-language requirement extraction with deterministic fallback."""

from __future__ import annotations

import json
import re

from inventory_agent.domain import CapabilityRequest
from inventory_agent.llm.client import LLMClient, MockLLMClient


class RequirementAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or MockLLMClient()

    @staticmethod
    def _fallback_parse(description: str) -> CapabilityRequest:
        item_match = re.search(r"(?:item|商品|SKU)[_\s:=号-]*(\d+)", description, re.IGNORECASE)
        store_match = re.search(r"(?:store|仓库|分仓)[_\s:=号-]*(all|\d+)", description, re.IGNORECASE)
        horizon_match = re.search(r"(?:未来|预测|horizon)[^\d]{0,8}(\d+)\s*(?:天|日|days?)", description, re.IGNORECASE)
        if not item_match or not store_match:
            raise ValueError("需求中必须明确商品 item/SKU 和仓库 store/分仓。")
        return CapabilityRequest(
            description=description,
            item_id=int(item_match.group(1)),
            store_code=store_match.group(1),
            horizon=int(horizon_match.group(1)) if horizon_match else 14,
        )

    def parse(self, description: str) -> CapabilityRequest:
        fallback = self._fallback_parse(description)
        if isinstance(self.llm, MockLLMClient):
            return fallback
        prompt = {
            "description": description,
            "fallback": {
                "item_id": fallback.item_id,
                "store_code": fallback.store_code,
                "horizon": fallback.horizon,
            },
        }
        response = self.llm.complete(
            "你是库存预测需求分析 Agent。只返回 JSON，保留明确的商品、仓库、预测周期和目标。",
            json.dumps(prompt, ensure_ascii=False),
        )
        try:
            data = json.loads(response)
            return CapabilityRequest(
                description=description,
                item_id=int(data.get("item_id", fallback.item_id)),
                store_code=str(data.get("store_code", fallback.store_code)),
                horizon=int(data.get("horizon", fallback.horizon)),
                objective=str(data.get("objective", "inventory_cost")),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return fallback

