from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from .bplustree import BPlusTree


_TYPE_STR_TO_TYPE = {
    "int": int,
    "str": str,
    "float": float,
    "bool": bool,
}

_TYPE_TO_TYPE_STR = {v: k for k, v in _TYPE_STR_TO_TYPE.items()}


@dataclass(frozen=True)
class ColumnSpec:
    py_type: type
    nullable: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None


def _parse_type(type_spec: Any) -> type:
    if isinstance(type_spec, type):
        return type_spec

    if isinstance(type_spec, str):
        normalized = type_spec.strip().lower()
        if normalized in _TYPE_STR_TO_TYPE:
            return _TYPE_STR_TO_TYPE[normalized]

    raise ValueError(f"Unsupported column type: {type_spec!r}")


def normalize_schema(schema: Mapping[str, Any]) -> Dict[str, ColumnSpec]:
    normalized: Dict[str, ColumnSpec] = {}

    for column, spec in schema.items():
        if isinstance(spec, dict):
            py_type = _parse_type(spec.get("type"))
            nullable = bool(spec.get("nullable", False))
            min_value = spec.get("min", spec.get("min_value"))
            max_value = spec.get("max", spec.get("max_value"))
            normalized[column] = ColumnSpec(
                py_type=py_type,
                nullable=nullable,
                min_value=min_value,
                max_value=max_value,
            )
        else:
            normalized[column] = ColumnSpec(py_type=_parse_type(spec))

    return normalized


def schema_to_json(schema: Mapping[str, ColumnSpec]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for column, spec in schema.items():
        out[column] = {
            "type": _TYPE_TO_TYPE_STR.get(spec.py_type, spec.py_type.__name__),
            "nullable": spec.nullable,
            "min": spec.min_value,
            "max": spec.max_value,
        }
    return out


class Table:
    """A single relation stored directly in its own B+Tree.

    Module A requirement: the B+Tree is the *only* storage for records.
    The B+Tree key is the primary key, and the value is the full record.
    """

    def __init__(
        self,
        name: str,
        schema: Mapping[str, Any],
        order: int = 8,
        search_key: Optional[str] = None,
        index_type: str = "bplustree",
    ):
        self.name = name
        self.order = order
        self.primary_key = search_key
        self.index_type = index_type

        self.schema: Dict[str, ColumnSpec] = normalize_schema(schema)

        if self.primary_key is None:
            raise ValueError("search_key (primary key) must be set")
        if self.primary_key not in self.schema:
            raise ValueError("search_key must be one of the columns in schema")

        # Module A requirement: each relation must be stored using a B+Tree.
        if self.index_type != "bplustree":
            raise ValueError("Module A requires index_type='bplustree'")
        self.data = BPlusTree(order=order)

    def validate_record(self, record: Mapping[str, Any]) -> None:
        if not isinstance(record, dict):
            raise ValueError("Record must be a dict")

        if set(record.keys()) != set(self.schema.keys()):
            raise ValueError("Record schema mismatch")

        for column, spec in self.schema.items():
            value = record[column]

            if value is None:
                if spec.nullable:
                    continue
                raise ValueError(f"Column '{column}' cannot be null")

            if spec.py_type is int and isinstance(value, bool):
                raise ValueError(f"Column '{column}' must be int (not bool)")

            if not isinstance(value, spec.py_type):
                raise ValueError(
                    f"Column '{column}' expected {spec.py_type.__name__}, got {type(value).__name__}"
                )

            if spec.min_value is not None and value < spec.min_value:
                raise ValueError(f"Column '{column}' must be >= {spec.min_value}")

            if spec.max_value is not None and value > spec.max_value:
                raise ValueError(f"Column '{column}' must be <= {spec.max_value}")

        # Primary key must be present and non-null
        pk_value = record[self.primary_key]
        if pk_value is None:
            raise ValueError("Primary key cannot be null")

    def exists(self, key: Any) -> bool:
        return self.data.search(key) is not None

    def get(self, key: Any) -> Optional[Dict[str, Any]]:
        record = self.data.search(key)
        if record is None:
            return None
        return dict(record)

    def put(self, key: Any, record: Mapping[str, Any]) -> None:
        record_dict = dict(record)
        self.validate_record(record_dict)

        if record_dict[self.primary_key] != key:
            raise ValueError("Primary key value must match the key argument")

        # Upsert semantics (safe for recovery/redo)
        self.data.insert(key, record_dict)

    def insert(self, record: Mapping[str, Any]) -> Any:
        record_dict = dict(record)
        self.validate_record(record_dict)

        key = record_dict[self.primary_key]
        if self.exists(key):
            raise KeyError(f"Duplicate primary key: {key!r}")

        self.data.insert(key, record_dict)
        return key

    def update(self, key: Any, new_record: Mapping[str, Any]) -> bool:
        if not self.exists(key):
            return False

        self.put(key, new_record)
        return True

    def delete(self, key: Any) -> bool:
        return bool(self.data.delete(key))

    def range_query(self, start_key: Any, end_key: Any) -> list[Dict[str, Any]]:
        items: list[Tuple[Any, Any]] = self.data.range_query(start_key, end_key)
        return [dict(record) for _, record in items]

    def get_all(self) -> list[Dict[str, Any]]:
        items: list[Tuple[Any, Any]] = self.data.get_all()
        return [dict(record) for _, record in items]

    def dump_records(self) -> list[Dict[str, Any]]:
        # Persist as list of full records.
        return self.get_all()

    def load_records(self, records: list[Mapping[str, Any]]) -> None:
        # Reset the underlying store.
        self.data = BPlusTree(order=self.order)

        for record in records:
            record_dict = dict(record)
            self.validate_record(record_dict)
            key = record_dict[self.primary_key]
            self.data.insert(key, record_dict)
