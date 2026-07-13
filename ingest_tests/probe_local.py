"""Local pre-check: what does DuckDB's read_csv_auto make of each file?
Approximates the connector's ingest so you can see failures before uploading.
Run: python3 probe_local.py"""
import duckdb, os, glob
con=duckdb.connect()
print(f"{'file':<38} {'result'}")
print("-"*70)
for f in sorted(glob.glob("*.csv")+glob.glob("*.parquet")+glob.glob("*.xlsx")):
    try:
        if f.endswith(".csv"):
            r=con.execute(f"SELECT COUNT(*) c, COUNT(*) FILTER(WHERE 1=1) FROM read_csv_auto('{f}')").fetchone()
            cols=con.execute(f"SELECT * FROM read_csv_auto('{f}') LIMIT 0").description
            print(f"{f:<38} OK  rows={r[0]:<5} cols={len(cols)}")
        elif f.endswith(".parquet"):
            r=con.execute(f"SELECT COUNT(*) FROM read_parquet('{f}')").fetchone()
            print(f"{f:<38} OK  rows={r[0]}")
        elif f.endswith(".xlsx"):
            # DuckDB needs the excel/spatial extension; may not be loaded here
            try:
                con.execute("INSTALL excel; LOAD excel;")
                r=con.execute(f"SELECT COUNT(*) FROM read_xlsx('{f}')").fetchone()
                print(f"{f:<38} OK  rows={r[0]}")
            except Exception as e:
                print(f"{f:<38} (xlsx needs extension) {str(e)[:30]}")
    except Exception as e:
        print(f"{f:<38} ✗ FAIL: {str(e)[:45]}")
