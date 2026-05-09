from __future__ import annotations

from app.services.schema_validation_service import SchemaValidationService


def test_schema_validation_accepts_valid_object() -> None:
    result = SchemaValidationService().validate_tool_input(
        {
            "type": "object",
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
            "additionalProperties": False,
        },
        {"expression": "1 + 2"},
    )

    assert result.valid is True
    assert result.missing_fields == []
    assert result.errors == []


def test_schema_validation_reports_missing_fields_and_unknown_keys() -> None:
    result = SchemaValidationService().validate_tool_input(
        {
            "type": "object",
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
            "additionalProperties": False,
        },
        {"query": "1 + 2"},
    )

    assert result.valid is False
    assert result.missing_fields == ["expression"]
    assert "未声明字段" in result.errors[0]


def test_schema_validation_checks_const_enum_and_number_range() -> None:
    result = SchemaValidationService().validate_tool_input(
        {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string", "const": "cli://git/log-oneline"},
                "max_count": {"type": "integer", "minimum": 1, "maximum": 20},
                "mode": {"type": "string", "enum": ["short", "full"]},
            },
        },
        {
            "rule_id": "cli://git/diff",
            "max_count": 30,
            "mode": "unknown",
        },
    )

    assert result.valid is False
    assert any("必须等于" in error for error in result.errors)
    assert any("不能大于" in error for error in result.errors)
    assert any("必须是" in error for error in result.errors)
