"""Intersect local domain grants without confusing deny-all with unrestricted.

An ordinary domain includes its subdomains. A leading *. excludes only its
apex. Empty configured lists remain unrestricted; an empty effective overlap
is accompanied by an explicit restriction marker and therefore denies all.
"""
from __future__ import annotations


def _valid_container(values: object) -> bool:
    return isinstance(values, (list, tuple)) and all(isinstance(value, str) for value in values)


def _rules(values: object) -> list[str]:
    if not _valid_container(values):
        return []
    return list(dict.fromkeys(value.strip().lower().rstrip(".") for value in values if value.strip()))


def is_restricted(values: object, restricted: bool = False) -> bool:
    return restricted or not _valid_container(values) or any(value.strip() for value in values)


def host_allowed(host: str, allowed: object, restricted: bool = False) -> bool:
    if not is_restricted(allowed, restricted):
        return True
    host = host.lower().rstrip(".")
    if not host:
        return False
    for rule in _rules(allowed):
        wildcard = rule.startswith("*.")
        base = rule[2:] if wildcard else rule
        if base and (host.endswith("." + base) or (host == base and not wildcard)):
            return True
    return False


def intersect_domains(left: object, right: object, *, left_restricted: bool = False,
                      right_restricted: bool = False) -> tuple[list[str], bool]:
    left_limited = is_restricted(left, left_restricted)
    right_limited = is_restricted(right, right_restricted)
    a, b = _rules(left), _rules(right)
    if not left_limited:
        return b, right_limited
    if not right_limited:
        return a, left_limited
    overlap = []
    for first in a:
        x = first[2:] if first.startswith("*.") else first
        for second in b:
            y = second[2:] if second.startswith("*.") else second
            if not x or not y:
                continue
            if x == y:
                overlap.append("*." + x if first.startswith("*.") or second.startswith("*.") else x)
            elif x.endswith("." + y):
                overlap.append(first)
            elif y.endswith("." + x):
                overlap.append(second)
    return list(dict.fromkeys(overlap)), True
