"""Policy accessor tests, including the join-date cycle guard."""

from __future__ import annotations

from datetime import date

from app.policy import Policy


def _policy(members: list[dict]) -> Policy:
    return Policy({"policy_id": "TEST", "members": members})


def test_member_join_date_direct():
    p = _policy([{"member_id": "EMP001", "join_date": "2024-04-01"}])
    assert p.member_join_date("EMP001") == date(2024, 4, 1)


def test_dependent_inherits_primary_join_date():
    p = _policy(
        [
            {"member_id": "EMP001", "join_date": "2024-04-01"},
            {"member_id": "DEP001", "primary_member_id": "EMP001"},
        ]
    )
    assert p.member_join_date("DEP001") == date(2024, 4, 1)


def test_unknown_member_returns_none():
    assert _policy([]).member_join_date("NOPE") is None


def test_cyclic_primary_member_chain_does_not_recurse_forever():
    # A -> B -> A with no join_date anywhere: must return None, not RecursionError.
    p = _policy(
        [
            {"member_id": "A", "primary_member_id": "B"},
            {"member_id": "B", "primary_member_id": "A"},
        ]
    )
    assert p.member_join_date("A") is None


def test_cyclic_chain_still_finds_join_date_before_repeating():
    # A -> B -> A, but B has a join_date: resolve it before the cycle closes.
    p = _policy(
        [
            {"member_id": "A", "primary_member_id": "B"},
            {"member_id": "B", "join_date": "2024-09-01", "primary_member_id": "A"},
        ]
    )
    assert p.member_join_date("A") == date(2024, 9, 1)
