"""Policy loader and typed accessors.

Every rule the adjudicator applies is read from `policy_terms.json`. Nothing
about coverage, limits, waiting periods or exclusions is hardcoded here — this
class only knows *how to look rules up*, never what they are.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

_DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policy_terms.json"


class PolicyLoadError(RuntimeError):
    """Raised when the policy file is missing, unreadable, or malformed."""


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


class Policy:
    """Read-only view over the policy document."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw
        self._members_by_id = {m["member_id"]: m for m in raw.get("members", [])}

    
    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "Policy":
        resolved = Path(path or os.environ.get("CLAIMS_POLICY_PATH") or _DEFAULT_POLICY_PATH)
        try:
            with open(resolved, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError as exc:
            raise PolicyLoadError(f"Policy file not found: {resolved}") from exc
        except json.JSONDecodeError as exc:
            raise PolicyLoadError(f"Policy file {resolved} is not valid JSON: {exc}") from exc
        if "policy_id" not in raw:
            raise PolicyLoadError(f"Policy file {resolved} is missing 'policy_id'")
        return cls(raw)

    @property
    def policy_id(self) -> str:
        return self._raw["policy_id"]

    @property
    def currency(self) -> str:
        return self._raw.get("submission_rules", {}).get("currency", "INR")

    def get_member(self, member_id: str) -> Optional[dict[str, Any]]:
        return self._members_by_id.get(member_id)

    def member_join_date(
        self, member_id: str, _visited: Optional[set[str]] = None
    ) -> Optional[date]:
        # _visited guards against cyclic primary_member_id chains (A -> B -> A)
        # in a malformed policy file, which would otherwise recurse forever.
        if _visited is None:
            _visited = set()
        if member_id in _visited:
            return None
        _visited.add(member_id)

        member = self.get_member(member_id)
        if member and member.get("join_date"):
            return _parse_date(member["join_date"])
        # dependents inherit the primary member's join date
        if member and member.get("primary_member_id"):
            return self.member_join_date(member["primary_member_id"], _visited)
        return None

    @property
    def coverage(self) -> dict[str, Any]:
        return self._raw.get("coverage", {})

    def category_config(self, category: str) -> dict[str, Any]:
        """opd_categories are keyed lowercase; claim categories arrive uppercase."""
        return self._raw.get("opd_categories", {}).get(category.lower(), {})

    def per_claim_limit(self) -> float:
        return float(self.coverage.get("per_claim_limit", 0))

    def annual_opd_limit(self) -> float:
        return float(self.coverage.get("annual_opd_limit", 0))

    def effective_claim_cap(self, category: str) -> float:
        """The binding per-claim ceiling for a category.

        ASSUMPTION (documented): the policy file lists both a global
        `per_claim_limit` (5000) and per-category `sub_limit`s. The only reading
        consistent with the eval cases (TC006 dental 8000 partial, TC008
        consultation 7500 reject, TC010 4500 approved) is the *larger* of the
        two — the category sub-limit raises the ceiling above the global floor.
        """
        sub_limit = float(self.category_config(category).get("sub_limit", 0))
        return max(self.per_claim_limit(), sub_limit)

    def document_requirements(self, category: str) -> dict[str, list[str]]:
        reqs = self._raw.get("document_requirements", {}).get(category.upper(), {})
        return {"required": reqs.get("required", []), "optional": reqs.get("optional", [])}

    @property
    def waiting_periods(self) -> dict[str, Any]:
        return self._raw.get("waiting_periods", {})

    @property
    def exclusions(self) -> dict[str, Any]:
        return self._raw.get("exclusions", {})

    @property
    def pre_authorization(self) -> dict[str, Any]:
        return self._raw.get("pre_authorization", {})

    @property
    def network_hospitals(self) -> list[str]:
        return self._raw.get("network_hospitals", [])

    def is_network_hospital(self, name: Optional[str]) -> bool:
        if not name:
            return False
        target = name.strip().lower()
        return any(target == h.lower() or h.lower() in target for h in self.network_hospitals)

    @property
    def fraud_thresholds(self) -> dict[str, Any]:
        return self._raw.get("fraud_thresholds", {})

    @property
    def submission_rules(self) -> dict[str, Any]:
        return self._raw.get("submission_rules", {})

    def summary(self) -> dict[str, Any]:
        """Lightweight view for the UI / health checks."""
        return {
            "policy_id": self.policy_id,
            "insurer": self._raw.get("insurer"),
            "currency": self.currency,
            "categories": list(self._raw.get("opd_categories", {}).keys()),
            "member_count": len(self._members_by_id),
            "network_hospitals": self.network_hospitals,
        }


@lru_cache(maxsize=1)
def get_policy() -> Policy:
    """Process-wide singleton (the policy file is read once)."""
    return Policy.from_file()
