"""Deterministic, read-only state probes. No helpers, models, or screenshot files."""

import re
from xml.etree import ElementTree

from .errors import SchemaError

STATE_NAME = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
STATE_FIELDS = ("requires_state", "provides_state", "clears_state")


def validate_probe(spec):
    if not isinstance(spec, dict):
        raise SchemaError("state probe must be a mapping")
    if set(spec) == {"not"}:
        # One negation is enough to express an absent selector.
        if not isinstance(spec["not"], dict) or "not" in spec["not"]:
            raise SchemaError("state probe permits one not around a selector")
        return validate_probe(spec["not"])
    locators = set(spec) & {"id", "text", "desc"}
    if spec.get("kind") != "element_present" or len(locators) != 1 or set(spec) != {"kind", *locators}:
        raise SchemaError("state probe must be element_present with exactly one id, text, or desc")
    value = spec[next(iter(locators))]
    if not isinstance(value, str) or not value or "{" in value or "}" in value:
        raise SchemaError("state probe selector must be a nonempty literal string")


def validate_states(skill):
    if not isinstance(skill.state_probes, dict):
        raise SchemaError("state_probes must be a mapping")
    for name, spec in skill.state_probes.items():
        if not isinstance(name, str) or not re.fullmatch(STATE_NAME, name):
            raise SchemaError("state names must be snake_case")
        validate_probe(spec)
    for action in skill.actions:
        if type(action.idempotent) is not bool:
            raise SchemaError("idempotent must be a boolean")
        for field in STATE_FIELDS:
            states = getattr(action, field)
            if not isinstance(states, list) or any(
                not isinstance(s, str) or not re.fullmatch(STATE_NAME, s) for s in states
            ):
                raise SchemaError(f"{field} must be a list of snake_case state names")
            if len(set(states)) != len(states):
                raise SchemaError(f"{field} cannot contain duplicates")
            if set(states) - skill.state_probes.keys():
                raise SchemaError(f"{field} references a state without a state_probes entry")
        if set(action.provides_state) & set(action.clears_state):
            raise SchemaError("an action cannot both provide and clear the same state")


def probe_state(skill, state, device):
    """Return True / False / None (unknown), including unavailable or invalid UI trees."""
    spec = skill.state_probes.get(state)
    if spec is None:
        return None
    try:
        validate_probe(spec)
        from .privacy import dump_xml

        root = ElementTree.fromstring(dump_xml(device))
        nodes = list(root.iter("node"))
        if root.tag != "hierarchy" or not nodes:
            return None
        negate = "not" in spec
        selector = spec["not"] if negate else spec
        key = next(k for k in ("id", "text", "desc") if k in selector)
        attr = {"id": "resource-id", "text": "text", "desc": "content-desc"}[key]
        found = any(n.get(attr) == selector[key] and n.get("visible-to-user", "true") != "false" for n in nodes)
        return not found if negate else found
    except Exception:
        # Do not log device exceptions: they can contain UI/credential text.
        return None
