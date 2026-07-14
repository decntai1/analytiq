r"""
Deterministic aggregate-before-join rewrite (SQL-shaping scaffold).

The reasoning ladder exposes a defect no model scale reliably clears: the join
fan-out. When a question combines a "one" table with a "many" table (a sale has
several returns), a model that JOINs them row-wise and then aggregates a column of
the ONE side DOUBLE-COUNTS it — each one-row is repeated once per matching many-row.
The query RUNS and returns a plausible-but-wrong number (L2b net revenue, L5b
return-rate-by-product). The correct shape is to aggregate each table on its own
grain FIRST, then join the pre-aggregated results ("aggregate before join").

This scaffold applies that fix deterministically, one layer below glossary_pin:
  - It is a PURE function of (emitted SQL, schema relationships) — it never sees the
    LLM, so like every other scaffold the correction is model-independent BY
    CONSTRUCTION. The model still writes all the semantics (which tables, columns,
    filters, the division); the scaffold repairs only the join-cardinality defect.
  - Relationships are read from the schema, not guessed: a single-column PK `k` on
    table T makes any OTHER table B carrying a column `k` (that is not B's own PK) a
    "many" side of T on key `k`. No FK declarations are required (the demo schema has
    none); no naming heuristics beyond "same column name as a foreign PK".

Determinism boundary (documented on purpose, so it can't be called fuzzy):
  1. RELATIONSHIP derivation — pure function of (primary keys, columns): see
     `derive_relationships`. Only single-column PKs; only exact column-name matches.
  2. DETECTION — the rewrite fires on exactly one recognised anti-pattern: a SELECT
     scope whose FROM equi-joins two BASE tables on a key that a derived relationship
     marks 1-to-many, AND which applies a fan-out-sensitive aggregate (SUM/COUNT/AVG/
     TOTAL) to a column of the ONE side in that same scope. Every SELECT scope in the
     statement is examined (so a fan-out nested inside a CTE/subquery is caught too);
     nothing else fires.
  3. REWRITE — each contributing base table is pre-aggregated on the query's GROUP BY
     keys (the "many" side reaching those keys through a many->one join, which cannot
     fan out) into a derived table, and the original projection/order is re-pointed at
     the pre-aggregated subqueries. Scopes outside the recognised family (already
     pre-aggregated, chains of 3+ tables, non-equi joins) are left UNCHANGED — a safe
     no-op, the honest-refusal boundary the other scaffolds keep.

Requires `sqlglot` (pure-Python, no native deps). If it is unavailable, or the SQL
does not parse, `rewrite` is a no-op and returns the input untouched.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    import sqlglot
    from sqlglot import exp
    _HAVE_SQLGLOT = True
except Exception:  # pragma: no cover - import guard
    _HAVE_SQLGLOT = False

# Aggregates whose value is inflated by a 1-to-many join fan-out. MIN/MAX are
# idempotent under row duplication, so they are deliberately excluded.
_FANOUT_AGG = ("sum", "count", "avg", "total")


@dataclass(frozen=True)
class Relationship:
    one_table: str      # the table whose PRIMARY KEY the join key is (the "one")
    many_table: str     # the table carrying the key as a non-PK column (the "many")
    key: str            # the shared column


def derive_relationships(
    pk_by_table: dict[str, list[str]],
    cols_by_table: dict[str, list[str]],
) -> list[Relationship]:
    """Pure function of the schema. Table T with a single-column PK named like a
    cross-table reference (`<entity>_id`, e.g. `sale_id`) ⇒ every OTHER table B that
    carries that exact column (and does not use it as its own single-column PK) is a
    many-side of T on that key.

    The `<entity>_id` requirement is deliberate: a bare `id` surrogate is a table's own
    local identity, NOT a foreign reference, so tables that merely share a generic `id`
    column must not be linked (that would manufacture spurious 1-to-many edges across
    unrelated tables). This keeps the rule to a single checkable convention, no fuzzy
    name-matching."""
    rels: list[Relationship] = []
    norm_cols = {t: {c.lower() for c in cols} for t, cols in cols_by_table.items()}
    for one, pks in pk_by_table.items():
        if len(pks) != 1:
            continue
        key = pks[0]
        kl = key.lower()
        if not kl.endswith("_id"):
            continue  # a bare `id` surrogate is not a cross-table foreign key
        for many, cols in norm_cols.items():
            if many == one or kl not in cols:
                continue
            many_pk = pk_by_table.get(many, [])
            if len(many_pk) == 1 and many_pk[0].lower() == kl:
                continue  # key is ALSO the many table's PK -> 1-to-1, not a fan-out
            rels.append(Relationship(one, many, key))
    return rels


def rewrite(sql: str, relationships: list[Relationship],
            cols_by_table: dict[str, list[str]], dialect: str = "sqlite") -> tuple[str, bool, str]:
    """Rewrite `sql` to aggregate-before-join wherever it matches the recognised
    fan-out anti-pattern. Returns (sql_out, fired, note). Never raises: any failure
    is a no-op that returns the input untouched."""
    if not _HAVE_SQLGLOT or not sql or not sql.strip():
        return sql, False, "sqlglot unavailable or empty"
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as e:
        return sql, False, f"parse error: {e}"
    statements = [s for s in statements if s is not None]
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return sql, False, "not a single SELECT statement"
    root = statements[0]
    cols_lower = {t: {c.lower() for c in cols} for t, cols in cols_by_table.items()}

    fired = False
    new_root = root
    # Innermost scopes first (reverse of DFS pre-order), so a fan-out nested inside a
    # CTE is rewritten before any enclosing scope is considered.
    for sel in reversed(list(root.find_all(exp.Select))):
        try:
            replacement = _rewrite_scope(sel, relationships, cols_lower, dialect)
        except Exception:
            replacement = None
        if replacement is None:
            continue
        if sel is root:            # root has no parent to replace it in — swap the handle
            new_root = replacement
        else:
            sel.replace(replacement)
        fired = True
    if not fired:
        return sql, False, "no recognised fan-out pattern"
    return new_root.sql(dialect=dialect), True, "aggregate-before-join applied"


def _resolve_table(col, alias_to_table: dict[str, str], scope_cols: dict[str, set]) -> str | None:
    """Which in-scope base table a column belongs to. Uses its qualifier if present,
    else the unique IN-SCOPE table that has a column of that name."""
    if col.table:
        return alias_to_table.get(col.table.lower())
    name = col.name.lower()
    owners = [t for t, cols in scope_cols.items() if name in cols]
    return owners[0] if len(owners) == 1 else None


def _agg_home(agg, alias_to_table, scope_cols) -> str | None:
    tables = {_resolve_table(c, alias_to_table, scope_cols) for c in agg.find_all(exp.Column)}
    tables.discard(None)
    return next(iter(tables)) if len(tables) == 1 else None


def _rewrite_scope(select, relationships, cols_lower, dialect):
    """If `select` is a base-table fan-out scope, return a replacement Select that
    pre-aggregates each table into a derived table before joining. Else return None."""
    from_ = select.args.get("from") or select.args.get("from_") or select.find(exp.From)
    if not from_ or not isinstance(from_.this, exp.Table):
        return None
    joins = select.args.get("joins") or []
    if len(joins) != 1 or not isinstance(joins[0].this, exp.Table):
        return None
    join = joins[0]

    a_name, a_alias = from_.this.name, (from_.this.alias or from_.this.name)
    b_name, b_alias = join.this.name, (join.this.alias or join.this.name)
    alias_to_table = {a_alias.lower(): a_name, b_alias.lower(): b_name}
    alias_to_table.setdefault(a_name.lower(), a_name)
    alias_to_table.setdefault(b_name.lower(), b_name)
    # column resolution is restricted to the two tables IN SCOPE (not the whole schema,
    # where a common name like `product` lives in many tables and would resolve ambiguously)
    scope_cols = {t: cols_lower.get(t, set()) for t in (a_name, b_name)}

    on = join.args.get("on")
    if not isinstance(on, exp.EQ) or not (
            isinstance(on.this, exp.Column) and isinstance(on.expression, exp.Column)):
        return None
    if on.this.name.lower() != on.expression.name.lower():
        return None
    key = on.this.name
    here = {a_name, b_name}
    rel = next((r for r in relationships
                if r.one_table in here and r.many_table in here
                and r.key.lower() == key.lower()), None)
    if rel is None:
        return None
    one_tbl, many_tbl = rel.one_table, rel.many_table

    # must aggregate a ONE-side column in this scope (the fan-out victim)
    aggs = list(select.find_all(exp.AggFunc))
    if not aggs:
        return None
    fired = False
    agg_home: dict[int, str] = {}
    for a in aggs:
        if a.key.lower() not in _FANOUT_AGG:
            continue
        home = _agg_home(a, alias_to_table, scope_cols)
        if home is None:
            return None  # can't safely resolve an aggregate -> no-op
        agg_home[id(a)] = home
        if home == one_tbl:
            fired = True
    if not fired:
        return None

    # GROUP BY keys must all resolve to ONE-side columns (corpus invariant; else bail)
    group = select.args.get("group")
    gcols = list(group.expressions) if group else []
    g_names: list[str] = []
    for g in gcols:
        if not isinstance(g, exp.Column) or _resolve_table(g, alias_to_table, scope_cols) != one_tbl:
            return None
        g_names.append(g.name)

    ONE, MANY = "__abj_one", "__abj_many"
    agg_slot: dict[str, tuple[str, str]] = {}   # normalized agg sql -> (derived, colname)
    one_defs: list = []
    many_defs: list = []

    def _slot_for(agg):
        norm = agg.sql(dialect=dialect).lower().replace(" ", "")
        if norm in agg_slot:
            return
        rebased = agg.copy()
        for c in rebased.find_all(exp.Column):
            c.set("table", None)   # strip qualifier: agg runs inside its own table's scope
        src = ONE if agg_home.get(id(agg)) == one_tbl else MANY
        idx = len([s for s in agg_slot.values() if s[0] == src])
        col = f"__a{idx}" if src == ONE else f"__b{idx}"
        (one_defs if src == ONE else many_defs).append(exp.alias_(rebased, col))
        agg_slot[norm] = (src, col)

    for a in aggs:
        if a.key.lower() in _FANOUT_AGG:
            _slot_for(a)

    # ---- pre-aggregation derived tables ----
    one_sel = exp.Select().from_(exp.to_table(one_tbl))
    one_sel.set("expressions", [exp.column(g) for g in g_names] + one_defs)
    if g_names:
        one_sel.set("group", exp.Group(expressions=[exp.column(g) for g in g_names]))

    many_sel = None
    if many_defs:
        many_sel = exp.Select()
        if g_names:
            # Start FROM the ONE side and LEFT JOIN the MANY side, grouped by the ONE-side
            # keys: every group survives (so zero-match groups yield 0/NULL, not a dropped
            # row), and each MANY row is still counted exactly once (summing a MANY column
            # over this join does not fan out — only a ONE-side column would).
            many_sel = many_sel.from_(exp.to_table(one_tbl)).join(
                exp.to_table(many_tbl),
                on=exp.condition(f"{one_tbl}.{key} = {many_tbl}.{key}"),
                join_type="left")
            many_sel.set("expressions", [exp.column(g, one_tbl) for g in g_names] + many_defs)
            many_sel.set("group", exp.Group(expressions=[exp.column(g, one_tbl) for g in g_names]))
        else:
            many_sel = many_sel.from_(exp.to_table(many_tbl))
            many_sel.set("expressions", list(many_defs))

    # ---- re-point the original projection / order at the derived tables ----
    def _inside_agg(col) -> bool:
        p = col.parent
        while p is not None:
            if isinstance(p, exp.AggFunc):
                return True
            p = p.parent
        return False

    def _repoint(node):
        node = node.copy()
        for a in list(node.find_all(exp.AggFunc)):
            slot = agg_slot.get(a.sql(dialect=dialect).lower().replace(" ", ""))
            if slot:
                a.replace(exp.column(slot[1], slot[0]))
        for c in list(node.find_all(exp.Column)):
            if c.name in g_names and not _inside_agg(c):
                c.set("table", exp.to_identifier(ONE))
        return node

    new_proj = [_repoint(e) for e in select.expressions]
    outer = exp.Select().select(*new_proj)
    outer = outer.from_(exp.Subquery(this=one_sel, alias=exp.TableAlias(this=exp.to_identifier(ONE))))
    if many_sel is not None:
        many_sub = exp.Subquery(this=many_sel, alias=exp.TableAlias(this=exp.to_identifier(MANY)))
        if g_names:
            on_expr = exp.and_(*[exp.EQ(this=exp.column(g, ONE), expression=exp.column(g, MANY))
                                 for g in g_names])
            outer = outer.join(many_sub, on=on_expr, join_type="left")
        else:
            outer = outer.join(many_sub, join_type="cross")

    order = select.args.get("order")
    if order:
        outer.set("order", _repoint(order))
    for k in ("limit", "offset"):
        if select.args.get(k):
            outer.set(k, select.args[k].copy())
    return outer
