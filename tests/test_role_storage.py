from __future__ import annotations

import json

from paperflow import roles


def test_storage_label_uses_user_defined_role_name(monkeypatch, tmp_path):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "gui agent lab": {"user_id": "user_role1"},
                    "science-role": {"user_id": "user_role2"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPERFLOW_ROLES_PATH", str(roles_path))

    assert roles.role_name_for_user_id("user_role1") == "gui agent lab"
    assert roles.storage_label_for_user_id("user_role1") == "gui-agent-lab"
    assert roles.storage_label_for_user_id("user_unknown") == "user_unknown"


def test_apply_user_scope_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPERFLOW_STORAGE_ROLE_SUBDIR", "false")

    assert roles.apply_user_scope(tmp_path / "vault", "user_role1") == tmp_path / "vault"


def test_apply_output_scope_groups_role_and_category(monkeypatch, tmp_path):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps({"roles": {"role1": {"user_id": "user_role1"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPERFLOW_ROLES_PATH", str(roles_path))

    root = tmp_path / "Obsidian Vault"

    assert roles.apply_output_scope(root, "user_role1", category="pdf") == root / "role1" / "pdf"
    assert (
        roles.apply_output_scope(root / "role1" / "pdf", "user_role1", category="pdf")
        == root / "role1" / "pdf"
    )
