#!/usr/bin/env python3
"""
ingest_suite.py — map the ingestion weak spots.

Generates a battery of messy real-world files (encodings, delimiters, embedded
newlines/commas, ragged rows, header-only, offset-header workbooks, decorative
sheets, …), runs each through the REAL upload path (DuckDBConnector.register_file
/ _ingest_xlsx), and prints a pass/fail table with the actual row counts.

Run it inside the app container so it exercises the shipped connector + duckdb:
    docker compose -f docker-compose.prod.yml exec -T app python3 - < scripts/ingest_suite.py

Each case declares an expectation:
  load  — must become a queryable table with >0 rows (optionally an exact count)
  fail  — must be honestly rejected (register_file -> None; no silent 0-row success)
A BUG is any case whose actual outcome differs from its expectation.
"""
from __future__ import annotations

import os
import tempfile

from connectors.duckdb_conn import DuckDBConnector

CASES = []  # (name, description, filename, bytes_or_builder, expect, want_rows)


def csv(name, desc, data, encoding, expect, want_rows=None):
    CASES.append((name, desc, f"{name}.csv",
                  data.encode(encoding) if isinstance(data, str) else data,
                  expect, want_rows))


# --- CSV cases -------------------------------------------------------------
csv("clean_utf8", "plain clean CSV", "a,b,c\n1,2,3\n4,5,6\n", "utf-8", "load", 2)
csv("cp1252_accents", "cp1252 accents (the tweet bug)",
    "city,country,n\nNiterói,Brasil,1\nMünchen,Deutschland,2\nMálaga,España,3\n", "cp1252", "load", 3)
csv("latin1_pure", "pure latin-1", "name,val\nRené,1\nBjörk,2\nÅsa,3\n", "latin-1", "load", 3)
csv("utf8_emoji", "utf-8 emoji in text", "id,txt\n1,go team 🏀🔥\n2,nice ✅\n", "utf-8", "load", 2)
csv("utf8_bom", "utf-8 with BOM", "﻿a,b\n1,x\n2,y\n", "utf-8", "load", 2)
csv("multiline_quoted", "embedded newlines in quoted field",
    'id,txt\n1,"line one\nline two\nline three",\n2,"ok",\n', "utf-8", "load", 2)
csv("embedded_commas", "commas inside quoted field",
    'id,txt\n1,"a, b, c"\n2,"d, e"\n', "utf-8", "load", 2)
csv("escaped_quotes", 'doubled "" quotes inside field',
    'id,html\n1,"<a href=""x"">link</a>"\n2,"plain"\n', "utf-8", "load", 2)
csv("semicolon_delim", "semicolon-delimited despite .csv", "a;b;c\n1;2;3\n4;5;6\n", "utf-8", "load", 2)
csv("tab_delim", "tab-delimited despite .csv", "a\tb\tc\n1\t2\t3\n4\t5\t6\n", "utf-8", "load", 2)
csv("crlf", "windows CRLF line endings", "a,b\r\n1,2\r\n3,4\r\n", "utf-8", "load", 2)
csv("ragged_unquoted", "inconsistent column counts (ragged)",
    "a,b,c\n1,2,3\n4,5\n6,7,8,9\n10,11,12\n", "utf-8", "load")   # loads; some rows may be skipped
csv("dup_columns", "duplicate column names", "id,id,name\n1,2,x\n3,4,y\n", "utf-8", "load", 2)
csv("single_column", "one column", "only\n1\n2\n3\n", "utf-8", "load", 3)
csv("quoted_numbers", "numbers quoted as text", 'id,code\n"1","007"\n"2","042"\n', "utf-8", "load", 2)
csv("mixed_type_col", "mixed numeric/text in a column", "id,v\n1,10\n2,hello\n3,30\n", "utf-8", "load", 3)
csv("trailing_blanks", "trailing blank lines", "a,b\n1,2\n3,4\n\n\n", "utf-8", "load", 2)
csv("title_rows", "junk/title rows above the real header",
    "Sales Report 2024\n\na,b,c\n1,2,3\n4,5,6\n", "utf-8", "load")   # weak spot — see actual
csv("header_only", "header row, no data (honest fail)", "a,b,c\n", "utf-8", "fail")
csv("empty_file", "completely empty (honest fail)", "", "utf-8", "fail")


def build_xlsx(sheets):
    """sheets: list of (title, rows). Returns bytes."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        ws = wb.create_sheet(title[:31])
        for r in rows:
            ws.append(list(r))
    import io
    b = io.BytesIO(); wb.save(b); return b.getvalue()


XLSX = [
    ("xlsx_clean", "clean 1-sheet workbook",
     [("data", [["a", "b"], [1, 2], [3, 4], [5, 6]])], "load"),
    ("xlsx_2sheets", "two data sheets -> two tables",
     [("sales", [["region", "rev"], ["N", 1], ["S", 2], ["E", 3]]),
      ("staff", [["team", "n"], ["Eng", 4], ["Ops", 5], ["Sale", 6]])], "load2"),
    ("xlsx_offset_header", "title rows above the header (offset)",
     [("rep", [["Q1 Report"], [], ["region", "rev"], ["N", 1], ["S", 2], ["E", 3]])], "load"),
    ("xlsx_decorative", "one good sheet + one tiny decorative sheet",
     [("good", [["a", "b"], [1, 2], [3, 4], [5, 6]]),
      ("logo", [["©brand"], ["x"]])], "load"),
]


def run():
    rows = []
    with tempfile.TemporaryDirectory() as d:
        # CSV cases
        for name, desc, fn, data, expect, want in CASES:
            p = os.path.join(d, fn)
            open(p, "wb").write(data)
            c = DuckDBConnector()
            try:
                view = c.register_file(p)
            except Exception as e:
                view = None
                desc += f" [EXC {type(e).__name__}]"
            li = (getattr(c, "last_ingest", None) or [{}])[0]
            got_rows = li.get("rows") if view else None
            skipped = li.get("skipped")
            outcome = "load" if view and (got_rows or 0) > 0 else "fail"
            ok = (outcome == expect) and (want is None or got_rows == want)
            rows.append((name, desc, expect, outcome, got_rows, skipped, want, ok))
        # XLSX cases
        for name, desc, sheets, expect in XLSX:
            p = os.path.join(d, name + ".xlsx")
            open(p, "wb").write(build_xlsx(sheets))
            c = DuckDBConnector()
            try:
                view = c.register_file(p)
            except Exception as e:
                view = None
                desc += f" [EXC {type(e).__name__}]"
            li = getattr(c, "last_ingest", None) or []
            ntabs = len([t for t in li if (t.get("rows") or 0) > 0])
            got_rows = (li[0].get("rows") if li else None)
            if expect == "load2":
                outcome = "load2" if ntabs == 2 else ("load" if ntabs == 1 else "fail")
            else:
                outcome = "load" if view and ntabs >= 1 else "fail"
            ok = outcome == expect
            rows.append((name, desc, expect, outcome + (f"({ntabs}t)" if ntabs else ""),
                         got_rows, None, None, ok))

    print(f"\n{'CASE':<20} {'EXPECT':<7} {'GOT':<9} {'ROWS':>6} {'SKIP':>5}  VERDICT  DESCRIPTION")
    print("-" * 100)
    bugs = 0
    for name, desc, expect, outcome, got_rows, skipped, want, ok in rows:
        if not ok:
            bugs += 1
        verdict = "\033[32mOK\033[0m  " if ok else "\033[31mBUG\033[0m "
        rr = "" if got_rows is None else str(got_rows)
        sk = "" if skipped is None else str(skipped)
        wantnote = f" (want {want})" if (want is not None and got_rows != want) else ""
        print(f"{name:<20} {expect:<7} {outcome:<9} {rr:>6} {sk:>5}  {verdict}  {desc}{wantnote}")
    print("-" * 100)
    print(f"{len(rows)} cases · {len(rows)-bugs} OK · {bugs} BUG")


run()
