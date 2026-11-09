"""Versioned historical mission records. This module cannot dispatch execution."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import types
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from ced_one.mission_control.policy import PolicyDecision
from ced_one.mission_control.types import (
    ApprovalRequirement, ApprovalState, AuthorityValidationResult,
    DivisionResolutionResult, MissionRequest, MissionResult,
    RequestClassification, RequestStatus,
)

VERSION = 1
APPLICATION_ID = 0x43454431
MAX_DEPTH = 100
MAX_RECORD_BYTES = 64 * 1024 * 1024
_DATACLASSES = {t.__name__: t for t in (
    MissionRequest, MissionResult, RequestClassification, DivisionResolutionResult,
    ApprovalRequirement, AuthorityValidationResult,
)}
_ENUMS = {t.__name__: t for t in (RequestStatus, ApprovalState, PolicyDecision)}
_SECRET_KEYS = frozenset((
    "password", "passwd", "secret", "token", "apikey", "apitoken", "authorization",
    "credentials", "credential", "accesstoken", "refreshtoken", "accesskey",
    "secretkey", "privatekey", "clientsecret", "cookie", "setcookie",
    "apisecret", "secretaccesskey", "awssecretaccesskey", "awsaccesskeyid",
    "bearertoken", "sessiontoken", "awssessiontoken", "idtoken",
))
_CREATE = """CREATE TABLE missions (
    mission_id TEXT PRIMARY KEY NOT NULL,
    version INTEGER NOT NULL,
    record_json TEXT NOT NULL,
    record_sha256 TEXT NOT NULL
)"""


class ArchiveError(Exception):
    code = "ARCHIVE_ERROR"

    def __init__(self):
        super().__init__(self.code)


class ArchiveIOError(ArchiveError):
    code = "STORAGE_ERROR"


class ArchiveSchemaError(ArchiveError):
    code = "SCHEMA_ERROR"


class ArchiveVersionError(ArchiveError):
    code = "UNSUPPORTED_VERSION"


class ArchiveIntegrityError(ArchiveError):
    code = "INTEGRITY_ERROR"


class ArchiveDataError(ArchiveError):
    code = "UNSUPPORTED_DATA"


class ArchiveSensitiveDataError(ArchiveError):
    code = "SENSITIVE_DATA"


class MissionConflictError(ArchiveError):
    code = "IDENTITY_CONFLICT"


class MissionNotFoundError(ArchiveError):
    code = "MISSION_NOT_FOUND"


class ArchiveNotConfiguredError(ArchiveError):
    code = "ARCHIVE_NOT_CONFIGURED"


@dataclass(frozen=True)
class ArchivedMission:
    mission_id: str
    request: MissionRequest
    result: MissionResult
    policy: dict[str, Any]
    record_sha256: str
    temporal_scope: str = "HISTORICAL_RECORD_ONLY"


@lru_cache(maxsize=None)
def _annotations(cls):
    return get_type_hints(cls)


def _matches(value, annotation):
    if annotation is Any:
        return True
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        return any(_matches(value, a) for a in args)
    if origin is Literal:
        return any(type(value) is type(a) and value == a for a in args)
    if origin is list:
        return type(value) is list and all(_matches(v, args[0]) for v in value)
    if origin is dict:
        return type(value) is dict and all(
            _matches(k, args[0]) and _matches(v, args[1]) for k, v in value.items())
    return type(value) is annotation


def _check_dataclass(value):
    if any(not _matches(getattr(value, f.name), _annotations(type(value))[f.name])
           for f in fields(value)):
        raise ArchiveDataError()


def _encode(value, depth=0):
    if depth > MAX_DEPTH:
        raise ArchiveDataError()
    child = lambda v: _encode(v, depth + 1)
    if value is None:
        return ["null"]
    if type(value) in _ENUMS.values():
        return ["enum", type(value).__name__, value.name]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is str:
        return ["str", value]
    if type(value) is int:
        return ["int", format(value, "x")]
    if type(value) is float and math.isfinite(value):
        return ["float", value.hex()]
    if type(value) is datetime and type(value.tzinfo) is timezone:
        return ["datetime", value.isoformat(timespec="microseconds"), value.fold, value.tzname()]
    if type(value) is list:
        return ["list", [child(v) for v in value]]
    if type(value) is dict and all(type(k) is str for k in value):
        for key in value:
            if "".join(c for c in key.lower() if c.isalnum()) in _SECRET_KEYS:
                raise ArchiveSensitiveDataError()
        # Native source identities include original OHLC dictionary order.
        return ["dict", [[k, child(v)] for k, v in value.items()]]
    if type(value) in _DATACLASSES.values():
        _check_dataclass(value)
        return ["dataclass", type(value).__name__,
                [[f.name, child(getattr(value, f.name))] for f in fields(value)]]
    raise ArchiveDataError()


def _decode(node, depth=0):
    if depth > MAX_DEPTH or type(node) is not list or not node or type(node[0]) is not str:
        raise ArchiveIntegrityError()
    tag = node[0]
    if tag == "null" and len(node) == 1:
        return None
    if tag in ("bool", "str") and len(node) == 2 and type(node[1]) is {"bool": bool, "str": str}[tag]:
        return node[1]
    if tag == "int" and len(node) == 2 and type(node[1]) is str:
        return int(node[1], 16)
    if tag == "float" and len(node) == 2 and type(node[1]) is str:
        return float.fromhex(node[1])
    if tag == "enum" and len(node) == 3 and type(node[1]) is str and type(node[2]) is str:
        return _ENUMS[node[1]][node[2]]
    if tag == "datetime" and len(node) == 4:
        if type(node[1]) is not str or type(node[2]) is not int or node[2] not in (0, 1) or type(node[3]) is not str:
            raise ArchiveIntegrityError()
        value = datetime.fromisoformat(node[1])
        if value.utcoffset() is None:
            raise ArchiveIntegrityError()
        return value.replace(tzinfo=timezone(value.utcoffset(), node[3]), fold=node[2])
    if tag == "list" and len(node) == 2 and type(node[1]) is list:
        return [_decode(v, depth + 1) for v in node[1]]
    if tag in ("dict", "dataclass") and len(node) == (2 if tag == "dict" else 3):
        rows = node[-1]
        if type(rows) is not list or any(type(r) is not list or len(r) != 2 or type(r[0]) is not str for r in rows):
            raise ArchiveIntegrityError()
        names = [r[0] for r in rows]
        if len(set(names)) != len(names):
            raise ArchiveIntegrityError()
        values = {k: _decode(v, depth + 1) for k, v in rows}
        if tag == "dict":
            return values
        cls = _DATACLASSES[node[1]]
        if names != [f.name for f in fields(cls)]:
            raise ArchiveIntegrityError()
        instance = cls(**values)
        _check_dataclass(instance)
        return instance
    raise ArchiveIntegrityError()


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_record(record):
    if type(record) is not dict or set(record) != {"version", "mission_id", "request", "result", "policy"}:
        raise ArchiveIntegrityError()
    if type(record["version"]) is not int or record["version"] != VERSION:
        raise ArchiveVersionError()
    mission_id, request, result, policy = (record[k] for k in ("mission_id", "request", "result", "policy"))
    if type(mission_id) is not str or not mission_id or type(request) is not MissionRequest or type(result) is not MissionResult:
        raise ArchiveIntegrityError()
    if request.request_id != mission_id or result.request_id != mission_id:
        raise MissionConflictError()
    if type(policy) is not dict or set(policy) != {"policy_id", "policy_version", "default_decision"}:
        raise ArchiveIntegrityError()
    if type(policy["policy_id"]) is not str or type(policy["policy_version"]) is not int or type(policy["default_decision"]) is not PolicyDecision:
        raise ArchiveIntegrityError()


def serialize_mission(request: MissionRequest, result: MissionResult, policy: dict) -> str:
    """Closed v1 encoding; never stringify unsupported objects or redact evidence."""
    if type(request) is not MissionRequest or type(result) is not MissionResult:
        raise ArchiveDataError()
    record = dict(version=VERSION, mission_id=request.request_id, request=request, result=result, policy=policy)
    _validate_record(record)
    try:
        text = _json({**record, "request": _encode(request), "result": _encode(result), "policy": _encode(policy)})
        if len(text.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ArchiveDataError()
        return text
    except (RecursionError, ValueError, TypeError):
        raise ArchiveDataError() from None


def deserialize_mission(text: str, digest: str, mission_id: str) -> ArchivedMission:
    """Validate checksum, grammar and exact round trip before exposing typed data."""
    try:
        if type(text) is not str or len(text.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ArchiveIntegrityError()
        if type(digest) is not str or hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            raise ArchiveIntegrityError()
        # Canonical re-encoding below rejects duplicate JSON keys and alternate forms.
        raw = json.loads(text)
        if type(raw) is not dict or set(raw) != {"version", "mission_id", "request", "result", "policy"}:
            raise ArchiveIntegrityError()
        if type(raw["version"]) is not int or raw["version"] != VERSION:
            raise ArchiveVersionError()
        record = {**raw, **{k: _decode(raw[k]) for k in ("request", "result", "policy")}}
        _validate_record(record)
        if record["mission_id"] != mission_id:
            raise MissionConflictError()
        if serialize_mission(record["request"], record["result"], record["policy"]) != text:
            raise ArchiveIntegrityError()
        return ArchivedMission(mission_id, record["request"], record["result"], record["policy"], digest)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, ArchiveDataError):
        raise ArchiveIntegrityError() from None


class SQLiteMissionArchive:
    """Explicit host-selected local archive. Reading never creates a database."""

    def __init__(self, path):
        self.path = Path(path).absolute()

    @staticmethod
    def _check_schema(connection):
        if connection.execute("PRAGMA user_version").fetchone()[0] != VERSION:
            raise ArchiveVersionError()
        if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise ArchiveSchemaError()
        columns = [(r[1], r[2], r[3], r[4], r[5]) for r in connection.execute("PRAGMA table_info(missions)")]
        expected = [("mission_id", "TEXT", 1, None, 1), ("version", "INTEGER", 1, None, 0),
                    ("record_json", "TEXT", 1, None, 0), ("record_sha256", "TEXT", 1, None, 0)]
        objects = connection.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        if columns != expected or objects != [("table", "missions")]:
            raise ArchiveSchemaError()

    @staticmethod
    def _read_row(row, mission_id):
        if row is None:
            raise MissionNotFoundError()
        if type(row[0]) is not int or row[0] != VERSION:
            raise ArchiveVersionError()
        return deserialize_mission(row[1], row[2], mission_id)

    def _connect(self, mode):
        # Both modes require an existing file; recovery must never create one.
        return sqlite3.connect(self.path.as_uri() + f"?mode={mode}", uri=True, timeout=5)

    def _publish_database(self):
        if self.path.exists():
            return
        fd, name = tempfile.mkstemp(prefix=f".{self.path.name}.init-", dir=self.path.parent)
        os.close(fd)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary.as_uri() + "?mode=rw", uri=True, timeout=5)) as connection:
                connection.execute("PRAGMA synchronous=FULL")
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(_CREATE)
                    connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    connection.execute(f"PRAGMA user_version={VERSION}")
                    self._check_schema(connection)
            with temporary.open("rb") as completed:
                os.fsync(completed.fileno())
            try:
                # Publish a complete, closed database atomically without overwrite.
                os.link(temporary, self.path)
            except FileExistsError:
                # Another first writer won; save() validates that file normally.
                return
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink()

    def _get_existing(self, mission_id, *, recover=False):
        with closing(self._connect("rw" if recover else "ro")) as connection:
            # SQLite may repair its journal, but application SQL may only read.
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            self._check_schema(connection)
            if recover and connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ArchiveIntegrityError()
            row = connection.execute("SELECT version, record_json, record_sha256 FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
            return self._read_row(row, mission_id)

    def save(self, request: MissionRequest, result: MissionResult, policy: dict) -> str:
        text = serialize_mission(request, result, policy)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:
            if self.path.is_symlink():
                raise ArchiveIOError()
            self._publish_database()
            with closing(self._connect("rw")) as connection:
                connection.execute("PRAGMA synchronous=FULL")
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._check_schema(connection)
                    old = connection.execute("SELECT version, record_json, record_sha256 FROM missions WHERE mission_id=?", (request.request_id,)).fetchone()
                    if old is not None:
                        self._read_row(old, request.request_id)
                        if old != (VERSION, text, digest):
                            raise MissionConflictError()
                    else:
                        connection.execute("INSERT INTO missions VALUES (?, ?, ?, ?)", (request.request_id, VERSION, text, digest))
            return digest
        except (sqlite3.Error, OSError, ValueError):
            raise ArchiveIOError() from None

    def get(self, mission_id: str) -> ArchivedMission:
        if type(mission_id) is not str or not mission_id:
            raise ArchiveDataError()
        try:
            if self.path.is_symlink():
                raise ArchiveIOError()
            try:
                return self._get_existing(mission_id)
            except sqlite3.Error as exc:
                if getattr(exc, "sqlite_errorcode", None) != sqlite3.SQLITE_READONLY_ROLLBACK:
                    raise
                return self._get_existing(mission_id, recover=True)
        except (sqlite3.Error, OSError, ValueError):
            raise ArchiveIOError() from None
