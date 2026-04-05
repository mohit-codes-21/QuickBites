from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Union

from .table import Table, schema_to_json


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, path)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class ForeignKey:
    table: str
    column: str
    ref_table: str
    ref_column: str


class WriteAheadLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, record: Dict[str, Any]) -> None:
        record = dict(record)
        record.setdefault("ts", time.time())

        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))

        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def sync(self) -> None:
        with self._lock:
            if not self.path.exists():
                return
            with self.path.open("a", encoding="utf-8") as f:
                f.flush()
                os.fsync(f.fileno())

    def read_records(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []

        records: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    # Ignore partial/corrupt tail lines (e.g., crash during write)
                    continue
        return records


class Transaction:
    def __init__(self, db: "DatabaseManager", txid: str):
        self._db = db
        self.txid = txid
        self._active = True
        self._ops: List[Dict[str, Any]] = []

    def _ensure_active(self) -> None:
        if not self._active:
            raise RuntimeError("Transaction is not active")

    def get(self, table_name: str, key: Any) -> Optional[Dict[str, Any]]:
        self._ensure_active()
        table = self._db.get_table(table_name)
        if table is None:
            raise KeyError(f"Unknown table: {table_name}")
        return table.get(key)

    def insert(self, table_name: str, record: Mapping[str, Any]) -> Any:
        self._ensure_active()
        table = self._db.get_table(table_name)
        if table is None:
            raise KeyError(f"Unknown table: {table_name}")

        record_dict = dict(record)
        # Validate before writing to WAL so recovery never replays invalid records.
        table.validate_record(record_dict)
        key = record_dict[table.primary_key]
        before = table.get(key)
        if before is not None:
            raise KeyError(f"Duplicate primary key: {key!r}")

        self._log_put(table_name=table_name, key=key, before=None, after=record_dict)
        table.put(key, record_dict)
        return key

    def update(self, table_name: str, key: Any, new_record: Mapping[str, Any]) -> bool:
        self._ensure_active()
        table = self._db.get_table(table_name)
        if table is None:
            raise KeyError(f"Unknown table: {table_name}")

        after_dict = dict(new_record)
        # Validate before WAL logging for replay-safety.
        table.validate_record(after_dict)
        if after_dict[table.primary_key] != key:
            raise ValueError("Primary key value must match the key argument")

        before = table.get(key)
        if before is None:
            return False

        self._log_put(table_name=table_name, key=key, before=before, after=after_dict)
        table.put(key, after_dict)
        return True

    def delete(self, table_name: str, key: Any) -> bool:
        self._ensure_active()
        table = self._db.get_table(table_name)
        if table is None:
            raise KeyError(f"Unknown table: {table_name}")

        before = table.get(key)
        if before is None:
            return False

        self._log_delete(table_name=table_name, key=key, before=before)
        table.delete(key)
        return True

    def commit(self) -> None:
        self._ensure_active()
        self._db._commit(self)
        self._active = False

    def rollback(self) -> None:
        if not self._active:
            return
        self._db._rollback(self)
        self._active = False

    def _log_put(self, table_name: str, key: Any, before: Any, after: Any) -> None:
        entry = {
            "type": "PUT",
            "txid": self.txid,
            "table": table_name,
            "key": key,
            "before": before,
            "after": after,
        }
        self._db._wal.append(entry)
        self._ops.append(entry)

    def _log_delete(self, table_name: str, key: Any, before: Any) -> None:
        entry = {
            "type": "DELETE",
            "txid": self.txid,
            "table": table_name,
            "key": key,
            "before": before,
            "after": None,
        }
        self._db._wal.append(entry)
        self._ops.append(entry)


class DatabaseManager:
    """Transactional database manager with WAL + crash recovery.

    - Each table is stored in its own B+Tree (value = full record).
    - Transactions support BEGIN/COMMIT/ROLLBACK.
    - WAL supports redo/undo recovery across restarts.
    - Basic isolation is provided via serialized transaction execution (global lock).
    """

    def __init__(self, data_dir: Optional[Union[str, os.PathLike]] = None, recover: bool = True):
        base_dir = Path(data_dir) if data_dir is not None else Path(__file__).resolve().parent.parent / "storage"
        self.data_dir = base_dir
        self.tables_dir = self.data_dir / "tables"
        self.catalog_path = self.data_dir / "catalog.json"
        self.wal_path = self.data_dir / "wal.jsonl"

        self._tx_lock = threading.RLock()
        self._active_tx: Optional[Transaction] = None

        self.tables: Dict[str, Table] = {}
        self.foreign_keys: List[ForeignKey] = []

        self._wal = WriteAheadLog(self.wal_path)

        self._load_catalog()
        self._load_tables()

        if recover:
            self.recover()

    # -----------------
    # Catalog / schema
    # -----------------

    def create_table(
        self,
        table_name: str,
        schema: Mapping[str, Any],
        order: int = 4,
        search_key: Optional[str] = None,
        index_type: str = "bplustree",
    ) -> bool:
        with self._tx_lock:
            if index_type != "bplustree":
                raise ValueError("Module A requires index_type='bplustree'")
            if table_name in self.tables:
                return False

            table = Table(
                name=table_name,
                schema=schema,
                order=order,
                search_key=search_key,
                index_type=index_type,
            )
            self.tables[table_name] = table
            self._persist_catalog()
            self._persist_tables([table_name])
            return True

    def get_table(self, table_name: str) -> Optional[Table]:
        return self.tables.get(table_name)

    def drop_table(self, table_name: str) -> bool:
        with self._tx_lock:
            if table_name not in self.tables:
                return False

            # Remove foreign keys referencing this table (simplest behavior for assignment use).
            self.foreign_keys = [
                fk
                for fk in self.foreign_keys
                if fk.table != table_name and fk.ref_table != table_name
            ]

            del self.tables[table_name]
            table_path = self.tables_dir / f"{table_name}.json"
            if table_path.exists():
                table_path.unlink()

            self._persist_catalog()
            return True

    def add_foreign_key(
        self,
        table: str,
        column: str,
        ref_table: str,
        ref_column: str,
    ) -> None:
        with self._tx_lock:
            if table not in self.tables:
                raise KeyError(f"Unknown table: {table}")
            if ref_table not in self.tables:
                raise KeyError(f"Unknown reference table: {ref_table}")

            if column not in self.tables[table].schema:
                raise KeyError(f"Unknown column '{column}' on table '{table}'")
            if ref_column not in self.tables[ref_table].schema:
                raise KeyError(f"Unknown column '{ref_column}' on table '{ref_table}'")

            fk = ForeignKey(table=table, column=column, ref_table=ref_table, ref_column=ref_column)
            if fk not in self.foreign_keys:
                self.foreign_keys.append(fk)
                self._persist_catalog()

    # -----------------
    # Transactions
    # -----------------

    def begin(self) -> Transaction:
        self._tx_lock.acquire()
        try:
            if self._active_tx is not None:
                raise RuntimeError("Nested/parallel transactions are not supported")

            txid = uuid.uuid4().hex
            tx = Transaction(self, txid)
            self._active_tx = tx
            self._wal.append({"type": "BEGIN", "txid": txid})
            return tx
        except Exception:
            self._tx_lock.release()
            raise

    @contextlib.contextmanager
    def transaction(self) -> Iterator[Transaction]:
        tx = self.begin()
        try:
            yield tx
            tx.commit()
        except Exception:
            tx.rollback()
            raise

    # Convenience auto-commit helpers
    def insert(self, table_name: str, record: Mapping[str, Any]) -> Any:
        with self.transaction() as tx:
            return tx.insert(table_name, record)

    def update(self, table_name: str, key: Any, new_record: Mapping[str, Any]) -> bool:
        with self.transaction() as tx:
            return tx.update(table_name, key, new_record)

    def delete(self, table_name: str, key: Any) -> bool:
        with self.transaction() as tx:
            return tx.delete(table_name, key)

    def get(self, table_name: str, key: Any) -> Optional[Dict[str, Any]]:
        with self._tx_lock:
            table = self.get_table(table_name)
            if table is None:
                raise KeyError(f"Unknown table: {table_name}")
            return table.get(key)

    def flush(self) -> None:
        """Force WAL to disk and persist current table state.

        This can be used to simulate a "steal" buffer policy for crash testing:
        - flush WAL first (WAL rule)
        - then write table snapshots
        """
        with self._tx_lock:
            self._wal.sync()
            self._persist_catalog()
            self._persist_tables(list(self.tables.keys()))

    def _commit(self, tx: Transaction) -> None:
        # Validate consistency before making the commit durable.
        self.validate()

        # Ensure operation log records are durable *before* persisting table snapshots (WAL rule).
        self._wal.sync()

        self._persist_catalog()
        self._persist_tables(list(self.tables.keys()))

        # Mark commit durable only after data is forced.
        self._wal.append({"type": "COMMIT", "txid": tx.txid})
        self._wal.sync()

        self._active_tx = None
        self._tx_lock.release()

    def _rollback(self, tx: Transaction) -> None:
        # Undo in reverse order using before-images.
        for entry in reversed(tx._ops):
            table = self.get_table(entry["table"])
            if table is None:
                continue

            key = entry["key"]
            if entry["type"] == "PUT":
                before = entry.get("before")
                if before is None:
                    table.delete(key)
                else:
                    table.put(key, before)
            elif entry["type"] == "DELETE":
                before = entry.get("before")
                if before is not None:
                    table.put(key, before)

        # Ensure the undoable operation log is durable before persisting the rolled-back state.
        self._wal.sync()

        self._persist_catalog()
        self._persist_tables(list(self.tables.keys()))

        # Mark abort durable after forcing data.
        self._wal.append({"type": "ABORT", "txid": tx.txid})
        self._wal.sync()

        self._active_tx = None
        self._tx_lock.release()

    # -----------------
    # Recovery
    # -----------------

    def recover(self) -> None:
        with self._tx_lock:
            records = self._wal.read_records()
            if not records:
                return

            # Determine winners/losers.
            committed: set[str] = set()
            seen_tx: set[str] = set()

            for r in records:
                txid = r.get("txid")
                if txid:
                    seen_tx.add(txid)
                if r.get("type") == "COMMIT" and txid:
                    committed.add(txid)

            losers = {txid for txid in seen_tx if txid not in committed}

            # REDO: apply all operations in log order (idempotent).
            for r in records:
                rtype = r.get("type")
                if rtype not in ("PUT", "DELETE"):
                    continue

                table = self.get_table(r.get("table", ""))
                if table is None:
                    continue

                key = r.get("key")
                if rtype == "PUT":
                    after = r.get("after")
                    if after is not None:
                        table.put(key, after)
                else:  # DELETE
                    table.delete(key)

            # UNDO: roll back losers using before-images (reverse log order).
            for r in reversed(records):
                txid = r.get("txid")
                if txid not in losers:
                    continue

                rtype = r.get("type")
                if rtype not in ("PUT", "DELETE"):
                    continue

                table = self.get_table(r.get("table", ""))
                if table is None:
                    continue

                key = r.get("key")
                before = r.get("before")

                if rtype == "PUT":
                    if before is None:
                        table.delete(key)
                    else:
                        table.put(key, before)
                else:  # DELETE
                    if before is not None:
                        table.put(key, before)

            # Persist recovered state.
            self._persist_catalog()
            self._persist_tables(list(self.tables.keys()))

            # Ensure post-recovery state is consistent.
            self.validate()

    # -----------------
    # Consistency checks
    # -----------------

    def validate(self) -> None:
        """Validate that all relations remain consistent after a transaction."""

        # Per-table schema + check constraints.
        for table in self.tables.values():
            for record in table.get_all():
                table.validate_record(record)

        # Foreign key integrity.
        for fk in self.foreign_keys:
            child = self.tables.get(fk.table)
            parent = self.tables.get(fk.ref_table)
            if child is None or parent is None:
                continue

            for record in child.get_all():
                value = record.get(fk.column)
                if value is None:
                    # Nullable FK is allowed.
                    continue

                # Fast path: referenced column is the parent's primary key.
                if fk.ref_column == parent.primary_key:
                    if parent.get(value) is None:
                        raise ValueError(
                            f"Foreign key violation: {fk.table}.{fk.column}={value!r} references missing {fk.ref_table}.{fk.ref_column}"
                        )
                else:
                    # Fallback: scan parent table.
                    found = any(parent_rec.get(fk.ref_column) == value for parent_rec in parent.get_all())
                    if not found:
                        raise ValueError(
                            f"Foreign key violation: {fk.table}.{fk.column}={value!r} references missing {fk.ref_table}.{fk.ref_column}"
                        )

    # -----------------
    # Internal I/O
    # -----------------

    def _load_catalog(self) -> None:
        catalog = _read_json(self.catalog_path, default=None)
        if not catalog:
            return

        tables = catalog.get("tables", {})
        for name, spec in tables.items():
            schema = spec.get("schema", {})
            order = int(spec.get("order", 4))
            primary_key = spec.get("primary_key")
            index_type = spec.get("index_type", "bplustree")

            self.tables[name] = Table(
                name=name,
                schema=schema,
                order=order,
                search_key=primary_key,
                index_type=index_type,
            )

        self.foreign_keys = [ForeignKey(**fk) for fk in catalog.get("foreign_keys", [])]

    def _load_tables(self) -> None:
        for name, table in self.tables.items():
            path = self.tables_dir / f"{name}.json"
            payload = _read_json(path, default=[])
            if not isinstance(payload, list):
                payload = []
            table.load_records(payload)

    def _persist_catalog(self) -> None:
        catalog = {
            "tables": {
                name: {
                    "schema": schema_to_json(table.schema),
                    "order": table.order,
                    "primary_key": table.primary_key,
                    "index_type": table.index_type,
                }
                for name, table in sorted(self.tables.items(), key=lambda kv: kv[0])
            },
            "foreign_keys": [asdict(fk) for fk in self.foreign_keys],
        }

        _atomic_write_json(self.catalog_path, catalog)

    def _persist_tables(self, table_names: List[str]) -> None:
        self.tables_dir.mkdir(parents=True, exist_ok=True)

        for name in table_names:
            table = self.tables.get(name)
            if table is None:
                continue

            path = self.tables_dir / f"{name}.json"
            _atomic_write_json(path, table.dump_records())
