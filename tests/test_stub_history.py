"""P08/P09: line scanner for stub-meta-history dumps."""

from __future__ import annotations

from wao.ingest.stub_history import editor_hash, parse

STUB = b"""<mediawiki>
  <page>
    <title>Talk:Paris</title>
    <ns>1</ns>
    <id>10</id>
    <revision>
      <id>1</id>
      <timestamp>2001-01-01T00:00:00Z</timestamp>
      <contributor>
        <username>A</username>
        <id>5</id>
      </contributor>
      <text bytes="10" id="1" />
    </revision>
  </page>
  <page>
    <title>Paris</title>
    <ns>0</ns>
    <id>11</id>
    <revision>
      <id>100</id>
      <timestamp>2002-02-02T00:00:00Z</timestamp>
      <contributor>
        <username>Alice</username>
        <id>7</id>
      </contributor>
      <minor />
      <comment>x</comment>
      <text bytes="1234" sha1="abc" location="tt:1" id="1" />
    </revision>
    <revision>
      <id>101</id>
      <parentid>100</parentid>
      <timestamp>2023-12-31T23:00:00Z</timestamp>
      <contributor>
        <ip>192.0.2.1</ip>
      </contributor>
      <text bytes="1300" id="2" />
    </revision>
    <revision>
      <id>102</id>
      <parentid>101</parentid>
      <timestamp>2025-06-01T00:00:00Z</timestamp>
      <contributor>
        <username>~2025-12345-6</username>
        <id>99</id>
      </contributor>
      <text bytes="1310" id="3" />
    </revision>
    <revision>
      <id>103</id>
      <timestamp>2025-07-01T00:00:00Z</timestamp>
      <contributor deleted="deleted" />
      <text deleted="deleted" />
    </revision>
  </page>
  <page>
    <title>London</title>
    <ns>0</ns>
    <id>12</id>
    <revision>
      <id>200</id>
      <timestamp>2003-01-01T00:00:00Z</timestamp>
      <contributor><ip>192.0.2.2</ip></contributor>
    </revision>
  </page>
</mediawiki>
"""


def test_parse_keeps_sample_ns0_pages_only():
    rows = list(parse(STUB.splitlines(keepends=True), {10, 11}))
    assert [r[:3] for r in rows] == [
        (11, 100, "2002-02-02T00:00:00Z"),
        (11, 101, "2023-12-31T23:00:00Z"),
        (11, 102, "2025-06-01T00:00:00Z"),
        (11, 103, "2025-07-01T00:00:00Z"),
    ]
    _, _, _, ed, reg, minor, size = rows[0]
    assert (ed, reg, minor, size) == (editor_hash(b"u7"), True, True, 1234)
    assert rows[1][3:] == (editor_hash(b"a192.0.2.1"), False, False, 1300)
    assert rows[2][4] is False  # temporary account counts as logged-out
    assert rows[3][3] is None and rows[3][6] is None  # suppressed contributor and text
