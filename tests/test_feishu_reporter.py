import importlib
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def feishu_reporter():
    return importlib.import_module("deployments.feishu.feishu-reporter.scripts.feishu_reporter")


def test_send_post_uses_raw_im_api(monkeypatch, feishu_reporter):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(
            stdout=json.dumps({"code": 0, "data": {"message_id": "om_test"}}),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(feishu_reporter, "FEISHU_CLI_CMD", "lark-cli")
    monkeypatch.setattr(feishu_reporter, "DEFAULT_IM_IDENTITY", "user")
    monkeypatch.setattr(feishu_reporter.subprocess, "run", fake_run)

    result = feishu_reporter.send_post(
        "ou_test",
        "Test Title",
        [[{"tag": "text", "text": "Hello"}]],
    )

    assert result["code"] == 0
    assert captured["args"][:6] == [
        "lark-cli",
        "api",
        "POST",
        "/open-apis/im/v1/messages",
        "--as",
        "user",
    ]

    params = json.loads(captured["args"][captured["args"].index("--params") + 1])
    assert params == {"receive_id_type": "open_id"}

    body = json.loads(captured["args"][captured["args"].index("--data") + 1])
    assert body["receive_id"] == "ou_test"
    assert body["msg_type"] == "post"
    assert json.loads(body["content"]) == {
        "zh_cn": {
            "title": "Test Title",
            "content": [[{"tag": "text", "text": "Hello"}]],
        }
    }


def test_send_text_raises_on_api_error(monkeypatch, feishu_reporter):
    def fake_run(args, **kwargs):
        return SimpleNamespace(
            stdout=json.dumps({"code": 999, "msg": "permission denied"}),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(feishu_reporter, "FEISHU_CLI_CMD", "lark-cli")
    monkeypatch.setattr(feishu_reporter.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="permission denied"):
        feishu_reporter.send_text("ou_test", "hello")


def test_send_daily_push_uses_multiline_text(monkeypatch, feishu_reporter):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(
            stdout=json.dumps({"code": 0, "data": {"message_id": "om_daily"}}),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(feishu_reporter, "FEISHU_CLI_CMD", "lark-cli")
    monkeypatch.setattr(feishu_reporter.subprocess, "run", fake_run)

    message = "# Title\n\n- item 1\n- item 2"
    feishu_reporter.send_daily_push("ou_test", message)

    body = json.loads(captured["args"][captured["args"].index("--data") + 1])
    assert body["msg_type"] == "text"
    assert json.loads(body["content"]) == {"text": message}


def test_send_markdown_degrades_to_text(monkeypatch, feishu_reporter):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(
            stdout=json.dumps({"code": 0, "data": {"message_id": "om_markdown"}}),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(feishu_reporter, "FEISHU_CLI_CMD", "lark-cli")
    monkeypatch.setattr(feishu_reporter.subprocess, "run", fake_run)

    markdown = "# Heading\n\nbody"
    feishu_reporter.send_markdown("ou_test", markdown)

    body = json.loads(captured["args"][captured["args"].index("--data") + 1])
    assert body["msg_type"] == "text"
    assert json.loads(body["content"]) == {"text": markdown}


def test_download_file_from_feishu_uses_relative_output_in_target_dir(monkeypatch, tmp_path, feishu_reporter):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        target_path = tmp_path / "paper.pdf"
        target_path.write_bytes(b"%PDF-1.4\n")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(feishu_reporter, "FEISHU_CLI_CMD", "lark-cli")
    monkeypatch.setattr(feishu_reporter, "DEFAULT_IM_IDENTITY", "user")
    monkeypatch.setattr(feishu_reporter.subprocess, "run", fake_run)

    result = feishu_reporter.download_file_from_feishu(
        "om_test",
        "file_v3_123",
        file_name="paper.pdf",
        save_dir=str(tmp_path),
    )

    assert result == str(tmp_path / "paper.pdf")
    assert captured["cwd"] == str(tmp_path)
    assert captured["args"][:6] == [
        "lark-cli",
        "api",
        "GET",
        "/open-apis/im/v1/messages/om_test/resources/file_v3_123",
        "--as",
        "user",
    ]
    assert captured["args"][captured["args"].index("--output") + 1] == "paper.pdf"


def test_create_doc_uses_stdin_markdown(monkeypatch, feishu_reporter):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(
            stdout=json.dumps({"code": 0, "data": {"doc_id": "doc_test", "doc_url": "https://example.feishu.cn/docx/doc_test"}}),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(feishu_reporter, "FEISHU_CLI_CMD", "lark-cli")
    monkeypatch.setattr(feishu_reporter, "DEFAULT_IM_IDENTITY", "user")
    monkeypatch.setattr(feishu_reporter.subprocess, "run", fake_run)

    result = feishu_reporter.create_doc("Test Doc", "# Heading\n\n- item 1\n- item 2")

    assert result["obj_token"] == "doc_test"
    assert result["url"] == "https://example.feishu.cn/docx/doc_test"
    assert captured["args"][captured["args"].index("--markdown") + 1] == "-"
    assert captured["input"] == "# Heading\n\n- item 1\n- item 2"


def test_send_text_records_recent_outbound_chat_message(monkeypatch, feishu_reporter):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(
            stdout=json.dumps({"code": 0, "data": {"message_id": "om_text"}}),
            stderr="",
            returncode=0,
        )

    feishu_reporter.RECENT_OUTBOUND_TEXT_MESSAGES.clear()
    monkeypatch.setattr(feishu_reporter, "FEISHU_CLI_CMD", "lark-cli")
    monkeypatch.setattr(feishu_reporter.subprocess, "run", fake_run)

    feishu_reporter.send_text("oc_test_chat", "bot echo message", use_chat_id=True)

    assert feishu_reporter.is_recent_outbound_text("chat_id", "oc_test_chat", "bot echo message") is True
