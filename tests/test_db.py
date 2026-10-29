import pyarrow as pa
import pyarrow.parquet as pq

from wao import db


def test_register_parquet_file_and_partitioned_dir(tmp_path):
    pq.write_table(pa.table({"x": [1, 2, 3]}), tmp_path / "flat.parquet")
    part = tmp_path / "parts" / "lang=en"
    part.mkdir(parents=True)
    pq.write_table(pa.table({"n": [5, 7]}), part / "a.parquet")

    con = db.connect(path=tmp_path / "t.duckdb")
    names = db.register_parquet(con, tmp_path)
    assert names == ["flat", "parts"]
    assert con.execute("SELECT sum(x) FROM flat").fetchone()[0] == 6
    assert con.execute("SELECT lang, sum(n) FROM parts GROUP BY lang").fetchall() == [("en", 12)]
