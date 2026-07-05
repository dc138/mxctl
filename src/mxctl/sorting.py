"""Hierarchical sort key for email addresses and domains.

Addresses sort as if the string were read right to left one dot separated
label at a time: domain labels from the TLD down, then local part labels
the same way. A bare domain is the same key without local part labels.

Example order: a.a@domain.com, b.a@domain.com, a.b@domain.com,
a.a@example.com, a.a@domain.net.
"""

from __future__ import annotations


def hierarchical_key(address: str) -> tuple[str, ...]:
    local, _, domain = address.rpartition("@")
    key = list(reversed(domain.split(".")))
    if local:
        key.extend(reversed(local.split(".")))
    return tuple(key)
