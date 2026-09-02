"""Per-role scoring config, loaded once from a JSON file at startup."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .schemas import RoleRequirements


class RoleNotFoundError(Exception):
    def __init__(self, role_id: str):
        self.role_id = role_id
        super().__init__(f"No role config found for role_id={role_id!r}")


@lru_cache(maxsize=1)
def _load_all(config_path: str) -> dict[str, RoleRequirements]:
    data = json.loads(Path(config_path).read_text())
    return {role_id: RoleRequirements(**entry) for role_id, entry in data.items()}


def get_role(role_id: str, config_path: str) -> RoleRequirements:
    roles = _load_all(config_path)
    if role_id not in roles:
        raise RoleNotFoundError(role_id)
    return roles[role_id]


def list_roles(config_path: str) -> dict[str, str]:
    return {role_id: req.role for role_id, req in _load_all(config_path).items()}