from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SchemaValidationResult:
    """工具输入 schema 校验结果。"""

    valid: bool                                             # 是否通过校验
    missing_fields: list[str] = field(default_factory=list) # 缺失的必填字段
    errors: list[str] = field(default_factory=list)         # 详细错误列表


class SchemaValidationService:
    """轻量 JSON Schema 子集校验。

    当前只实现 ToolHub 工具 schema 已使用到的常见字段，避免为了路由阶段的
    轻量判断引入完整 JSON Schema 依赖。真正执行前的严格校验后续仍可替换为
    jsonschema 这类成熟库。
    """

    def validate_tool_input(
        self,
        schema: dict[str, Any] | None,
        tool_input: dict[str, Any] | None,
    ) -> SchemaValidationResult:
        """校验 tool_input 是否满足工具 input_schema。"""
        # 无 schema → 直接通过（宽松模式）
        if not schema:
            return SchemaValidationResult(valid=True)

        # 类型检查：必须是 dict
        value = tool_input or {}
        if not isinstance(value, dict):
            return SchemaValidationResult(
                valid=False,
                errors=["tool_input 必须是 object"],
            )

        # 检查必填字段
        missing_fields = self._missing_required_fields(schema, value)
        # 检查根节点类型
        errors: list[str] = []
        expected_type = schema.get("type")
        if expected_type and not self._matches_type(value, expected_type):
            errors.append(f"根输入类型必须是 {expected_type}")
        # 递归验证对象属性
        errors.extend(self._validate_object(schema, value, path="tool_input"))
        return SchemaValidationResult(
            valid=not missing_fields and not errors,
            missing_fields=missing_fields,
            errors=errors,
        )

    def _missing_required_fields(
        self,
        schema: dict[str, Any],
        value: dict[str, Any],
    ) -> list[str]:
        """必填字段检查"""
        required = schema.get("required") or []
        if not isinstance(required, list):
            return []
        return [
            str(field_name)
            for field_name in required
            if str(field_name) not in value
        ]

    def _validate_object(
        self,
        schema: dict[str, Any],
        value: dict[str, Any],
        *,
        path: str,
    ) -> list[str]:
        errors: list[str] = []
        properties = schema.get("properties") or {}
        if not isinstance(properties, dict):
            return errors
        #  检查 additionalProperties
        if schema.get("additionalProperties") is False:
            unknown_keys = sorted(set(value) - set(properties))
            if unknown_keys:
                errors.append(f"{path} 包含未声明字段：{unknown_keys}")
        # 递归验证每个属性
        for key, item_schema in properties.items():
            if key not in value or not isinstance(item_schema, dict):
                continue
            errors.extend(
                self._validate_value(
                    item_schema,
                    value[key],
                    path=f"{path}.{key}",
                )
            )
        return errors

    def _validate_value(
        self,
        schema: dict[str, Any],
        value: Any,
        *,
        path: str,
    ) -> list[str]:
        errors: list[str] = []
        # const 约束（必须等于固定值）
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path} 必须等于 {schema['const']!r}")
        # enum 约束（枚举值）
        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            errors.append(f"{path} 必须是 {enum_values} 之一")
        # type 约束（类型检查）
        expected_type = schema.get("type")
        if expected_type and not self._matches_type(value, expected_type):
            errors.append(f"{path} 类型必须是 {expected_type}")
            return errors
        # 递归验证嵌套对象
        if isinstance(value, dict):
            errors.extend(self._validate_object(schema, value, path=path))
        # 数值范围约束
        if isinstance(value, int | float):
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"{path} 不能小于 {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{path} 不能大于 {maximum}")

        return errors

    def _matches_type(self, value: Any, expected_type: Any) -> bool:
        if isinstance(expected_type, list):
            return any(self._matches_type(value, item) for item in expected_type)

        mapping = {
            "object": dict,
            "array": list,
            "string": str,
            "boolean": bool,
            "integer": int,
            "number": (int, float),
            "null": type(None),
        }
        expected_python_type = mapping.get(str(expected_type))
        if expected_python_type is None:
            return True
        if expected_type == "integer" and isinstance(value, bool):
            return False
        if expected_type == "number" and isinstance(value, bool):
            return False
        return isinstance(value, expected_python_type)
