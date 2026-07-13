# Analytiq Ingestion Stress-Test Suite

30 files probing every supported format + real-world failure modes. Upload each,
record what happens. The **Expected** column is what a *robust* ingest should do —
where the actual behavior differs, you've found a bug (or a design gap).

Supported routing (from api/ingest.py):
- **Table arm** (DuckDB): `.csv .parquet .xlsx .xls`
- **Document arm** (doc-RAG): `.pdf .txt .md`

## CSV — the tweet-CSV failure hunt (this is where TweetsNBA.csv likely died)

| File | Tests | Expected (robust behavior) |
|------|-------|----------------------------|
| 01_csv_clean.csv | baseline | ✅ table, 20 rows, 3 cols |
| 02_csv_embedded_commas.csv | commas+quotes inside text (properly quoted) | ✅ table, 3 rows — **prime suspect for tweet failures** |
| 03_csv_embedded_newlines.csv | newlines inside a quoted field | ✅ table, 2 rows — naive line-splitters produce ragged rows here |
| 04_csv_ragged_unquoted.csv | genuinely malformed: unquoted commas, wrong field counts | ⚠️ either skip-bad-rows-with-count OR honest reject — NOT a silent wrong parse |
| 05_csv_latin1.csv | non-UTF-8 (latin-1) encoding, accents | ✅ ideally (encoding detect) or honest "encoding" error |
| 06_csv_utf8_bom.csv | UTF-8 BOM (Excel exports) | ✅ table — BOM must not corrupt the first column name |
| 07_csv_semicolon.csv | semicolon delimiter named .csv | ⚠️ detect delimiter, or honest error (not one giant column) |
| 08_csv_title_row.csv | junk title + blank line before header | ⚠️ ideally skip to real header, or honest error |
| 09_csv_emoji.csv | emoji-heavy UTF-8 (real tweets) | ✅ table, 2 rows — emoji must survive |
| 10_csv_header_only.csv | header, zero data rows | ⚠️ honest "no data rows" (per the honesty invariant) |
| 11_csv_dup_columns.csv | duplicate column names | ⚠️ de-dupe (name, name_1) or honest error — must not silently drop |
| 12_csv_weird_colnames.csv | digit-leading / spaces / $ / reserved word `select` | ✅ sanitized to valid SQL identifiers (t_ prefix etc.) |

## Excel

| File | Tests | Expected |
|------|-------|----------|
| 13_xlsx_clean.xlsx | single clean sheet | ✅ 1 table, 20 rows |
| 14_xlsx_multisheet_mixed.xlsx | 1 good sheet + 1 "decorative" (<3 rows) | ✅ 1 table (roster); notes sheet dropped by quality gate |
| 15_xlsx_two_good_sheets.xlsx | both sheets valid | ✅ 2 tables (sales, headcount) |
| 16_xlsx_offset_header.xlsx | title + blanks before header | ⚠️ detect real header, or drop — must not make a garbage table |
| 17_xlsx_formulas.xlsx | formula cells (=B2*C2) | ✅ table with computed/na values, no crash |
| 18_xlsx_empty.xlsx | no data | ⚠️ honest "no data table" |
| 19_xlsx_emoji.xlsx | emoji + unicode cells | ✅ table, emoji survive |

## Parquet

| File | Tests | Expected |
|------|-------|----------|
| 20_parquet_clean.parquet | baseline | ✅ 1 table, 20 rows |
| 21_parquet_nulls_unicode.parquet | nulls + unicode + mixed types | ✅ table, nulls preserved |

## Documents (→ document arm; note: Q&A is weak under EMBEDDING_MODE=test)

| File | Tests | Expected |
|------|-------|----------|
| 22_txt_clean.txt | plain text | ✅ document, indexed |
| 23_txt_emoji.txt | emoji/unicode text | ✅ document |
| 24_txt_empty.txt | 0 bytes | ⚠️ honest "empty document" / reject |
| 25_md_clean.md | markdown | ✅ document, "1 document" (not chunk count) |
| 26_md_long.md | long → multiple chunks | ✅ document = **1 file** even though many chunks (the count fix) |
| 27_pdf_text.pdf | text PDF | ✅ document, text extracted |

## Edge cases (routing / robustness)

| File | Tests | Expected |
|------|-------|----------|
| 28_unknown.json | unsupported extension | clear "unsupported file type" message |
| 29_noext | no extension at all | clear error, no crash |
| 30_csv_empty_0bytes.csv | 0-byte CSV | honest "empty file" — must not hang or 500 |

---

### How to use
Upload each in the UI (or via the API) and record: **table / document / rejected / hung / 500**.
Any file that **hangs**, **500s**, or **silently ingests wrong** (e.g. one giant column,
dropped rows with no notice) is a bug. The honesty invariant says junk should be
*honestly rejected*, never silently mis-ingested.

Priority suspects for your TweetsNBA.csv failure: **02, 03, 04** (embedded
commas/newlines/ragged rows) — the classic real-world CSV killers.
