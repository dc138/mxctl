import random

from mxctl.sorting import hierarchical_key

EXPECTED_ORDER = [
    "a.a@domain.com",
    "b.a@domain.com",
    "c.a@domain.com",
    "a.b@domain.com",
    "b.b@domain.com",
    "c.b@domain.com",
    "a.a@example.com",
    "b.a@example.com",
    "c.a@example.com",
    "a.b@example.com",
    "b.b@example.com",
    "c.b@example.com",
    "a.a@domain.net",
    "b.a@domain.net",
    "c.a@domain.net",
    "a.b@domain.net",
    "b.b@domain.net",
    "c.b@domain.net",
    "a.a@example.net",
    "b.a@example.net",
    "c.a@example.net",
    "a.b@example.net",
    "b.b@example.net",
    "c.b@example.net",
]


def test_reference_example_order() -> None:
    shuffled = EXPECTED_ORDER.copy()
    random.Random(42).shuffle(shuffled)
    assert sorted(shuffled, key=hierarchical_key) == EXPECTED_ORDER


def test_bare_domains() -> None:
    domains = ["example.net", "domain.net", "example.com", "domain.com"]
    expected = ["domain.com", "example.com", "domain.net", "example.net"]
    assert sorted(domains, key=hierarchical_key) == expected


def test_key_shape() -> None:
    assert hierarchical_key("a.b@domain.com") == ("com", "domain", "b", "a")
    assert hierarchical_key("domain.com") == ("com", "domain")
    assert hierarchical_key("user@domain.com") == ("com", "domain", "user")


def test_domain_sorts_before_its_addresses() -> None:
    items = ["user@domain.com", "domain.com"]
    assert sorted(items, key=hierarchical_key) == ["domain.com", "user@domain.com"]
