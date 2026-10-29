"""DuckDB helpers: one connection with every Parquet table registered as a view."""

from __future__ import annotations

from pathlib import Path

import duckdb

from wao import config


def connect(read_only: bool = False, path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = config.DUCKDB_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    con.execute("SET preserve_insertion_order = false")
    return con


def register_parquet(con: duckdb.DuckDBPyConnection, parquet_dir: Path | None = None) -> list[str]:
    """Create a view per Parquet dataset (file or hive-partitioned directory) in `parquet_dir`."""
    parquet_dir = config.PARQUET_DIR if parquet_dir is None else parquet_dir
    names: list[str] = []
    if not parquet_dir.is_dir():
        return names
    for p in sorted(parquet_dir.iterdir()):
        if p.suffix == ".parquet":
            src, name = str(p), p.stem
        elif p.is_dir():
            src, name = str(p / "**" / "*.parquet"), p.name
        else:
            continue
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{src}', hive_partitioning = true)"
        )
        names.append(name)
    return names
