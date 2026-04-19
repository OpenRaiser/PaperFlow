import copy
import importlib


must_read_manager = importlib.import_module("agents.must-read-manager.main")


def test_parse_command_supports_plain_remove_without_colon():
    command = must_read_manager.parse_command("去掉机构上海ai lab")

    assert command == {
        "action": "remove",
        "type": "institution",
        "value": "上海ai lab",
    }


def test_parse_command_strips_leading_particle_from_institution_remove():
    command = must_read_manager.parse_command("去掉机构的上海AI Lab")

    assert command == {
        "action": "remove",
        "type": "institution",
        "value": "上海AI Lab",
    }


def test_parse_command_supports_plain_keyword_remove_with_space():
    command = must_read_manager.parse_command("删掉关键词 nlp")

    assert command == {
        "action": "remove",
        "type": "keyword",
        "value": "nlp",
    }


def test_remove_must_read_matches_institution_case_insensitively(sample_profile):
    profile = copy.deepcopy(sample_profile)

    result = must_read_manager.remove_must_read(profile, "institution", "shanghai ai lab")

    assert result["success"] is True
    assert profile["must_read"]["institutions"] == []


def test_add_must_read_rejects_case_only_duplicates(sample_profile):
    profile = copy.deepcopy(sample_profile)

    result = must_read_manager.add_must_read(profile, "keyword", "PHASE TRANSITION")

    assert result["success"] is False
    assert profile["must_read"]["keywords"] == ["phase transition"]


def test_remove_must_read_accepts_value_with_leading_particle(sample_profile):
    profile = copy.deepcopy(sample_profile)

    result = must_read_manager.remove_must_read(profile, "institution", "的Shanghai AI Lab")

    assert result["success"] is True
    assert profile["must_read"]["institutions"] == []


def test_format_must_read_list_mentions_cold_start_and_reading_queue_hints(sample_profile):
    formatted = must_read_manager.format_must_read_list(sample_profile)

    assert "普通“冷启动”会保留这份必读清单" in formatted
    assert "重新冷启动" in formatted
    assert "清空精读列表" in formatted
