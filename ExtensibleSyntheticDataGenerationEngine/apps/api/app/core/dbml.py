"""
DBDiagram.io (DBML) subset importer.

Mapping:
- `Project`            -> schema name
- `Table`              -> Entity (snake_case name, optional `[as alias]`)
- column               -> Attribute (pk / not null / null / unique honoured)
- `Ref` / inline ref   -> Relationship (foreign_key attribute + fk_target)
- `enum`               -> categorical attribute with fixed choices

Unsupported constructs (indexes, table groups, schemas, notes, styliing) are
skipped and reported as warnings. Unfaithful documents (unbalanced braces,
composite primary keys, refs to missing tables/attributes) raise a
DbmlParseError carrying line-numbered diagnostics.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re


@dataclass
class DbmlDiagnostic:
    line: int
    message: str


@dataclass
class DbmlSkippedSettings:
    """Accumulates ignorable constructs so the final report is a compact
    summary instead of one warning line per occurrence."""
    indexes: List[Tuple[str, int]] = field(default_factory=list)   # (table, line)
    column_settings: List[Tuple[str, str, int, str]] = field(default_factory=list)  # (table, col, line, setting)

    def flush(self, warnings: List[str]) -> None:
        if self.indexes:
            locs = ", ".join(f"'{t}' (line {n})" for t, n in self.indexes)
            warnings.append(f"DBML indexes skipped (no generator equivalent): {locs}")
        if self.column_settings:
            parts = [
                f"'{setting}' on '{t}.{col}' (line {n})"
                for t, col, n, setting in self.column_settings
            ]
            warnings.append(f"Unsupported column settings ignored: {', '.join(parts)}")


@dataclass
class DbmlImportResult:
    name: str
    entities: List[Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)


class DbmlParseError(Exception):
    def __init__(self, diagnostics: List[DbmlDiagnostic]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(f"line {d.line}: {d.message}" for d in diagnostics))


# DBML scalar types -> (generator key, params). Parenthesized sizes are
# stripped before lookup. Integer PKs are upgraded to autoincrement later.
_SCALAR_TYPES: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "serial": ("autoincrement", {}),
    "bigserial": ("autoincrement", {}),
    "uuid": ("uuid", {}),
    "boolean": ("boolean", {}),
    "bool": ("boolean", {}),
    "timestamp": ("date_time", {}),
    "datetime": ("date_time", {}),
    "date": ("date_time", {}),
    "bigint": ("numeric_range", {}),
    "integer": ("numeric_range", {}),
    "int": ("numeric_range", {}),
    "smallint": ("numeric_range", {}),
    "decimal": ("numeric_range", {"is_float": True}),
    "numeric": ("numeric_range", {"is_float": True}),
    "float": ("numeric_range", {"is_float": True}),
    "double": ("numeric_range", {"is_float": True}),
    "real": ("numeric_range", {"is_float": True}),
    "money": ("numeric_range", {"is_float": True, "precision": 2}),
}

# Column-name heuristics for string-ish types (varchar / text / char).
_NAME_HEURISTICS: List[Tuple[str, str]] = [
    ("email", "email"),
    ("phone", "phone"),
    ("mobile", "phone"),
    ("address", "street_address"),
    ("city", "city"),
    ("country", "country"),
    ("first_name", "first_name"),
    ("last_name", "last_name"),
    ("name", "full_name"),
]


def parse_dbml(source: str, fallback_name: str = "Synthetic Dataset") -> DbmlImportResult:
    """
    Parses a DBDiagram.io DBML document into engine Schema structures.

    Raises DbmlParseError with line-numbered diagnostics when the document
    cannot be faithfully mapped.
    """
    diagnostics: List[DbmlDiagnostic] = []
    warnings: List[str] = []
    skipped = DbmlSkippedSettings()
    lines = _strip_comments(source)

    project_name: Optional[str] = None
    entities: Dict[str, Dict[str, Any]] = {}     # canonical snake name -> entity
    aliases: Dict[str, str] = {}                 # alias -> canonical table name
    global_enums: Dict[str, List[str]] = {}      # enum type name -> choices
    scoped_enums: Dict[str, Dict[str, List[str]]] = {}  # table -> enum -> choices
    refs: List[Tuple[int, str, str]] = []        # (line, child "e.a", parent "e.a")

    i = 0
    n = len(lines)
    while i < n:
        text = lines[i].strip()
        if not text:
            i += 1
            continue
        lowered = text.lower()

        if lowered.startswith("project"):
            value = _header_name(text[len("project"):])
            end = _skip_block(lines, i)
            if end == -1:
                diagnostics.append(DbmlDiagnostic(i + 1, "Unclosed Project block"))
                break
            if value:
                project_name = value
            else:
                project_name = _read_project_settings_block(lines, i) or project_name
            i = end
        elif lowered.startswith("tablegroups") or lowered.startswith("table group"):
            warnings.append(f"DBML table groups are not supported and were skipped (line {i + 1})")
            end = _skip_block(lines, i)
            if end == -1:
                diagnostics.append(DbmlDiagnostic(i + 1, "Unclosed table groups block"))
                break
            i = end
        elif lowered.startswith("enum"):
            _read_enum(lines, i, entities, global_enums, scoped_enums, diagnostics)
            end = _skip_block(lines, i)
            if end == -1:
                diagnostics.append(DbmlDiagnostic(i + 1, "Unclosed enum block"))
                break
            i = end
        elif lowered.startswith("table "):
            _read_table(lines, i, entities, aliases, refs, diagnostics, warnings, skipped)
            end = _skip_block(lines, i)
            if end == -1:
                diagnostics.append(DbmlDiagnostic(i + 1, f"Unclosed table block '{text[:40]}'"))
                break
            i = end
        elif lowered.startswith("ref"):
            _read_standalone_ref(text, i + 1, refs, diagnostics)
            i += 1
        else:
            diagnostics.append(
                DbmlDiagnostic(i + 1, f"Unsupported top-level construct: '{text[:60]}'")
            )
            i += 1

    if not entities and not diagnostics:
        raise DbmlParseError([DbmlDiagnostic(1, "No tables found in DBML source")])

    _resolve_refs(refs, entities, aliases, diagnostics)
    if diagnostics:
        raise DbmlParseError(diagnostics)

    _apply_fallbacks(entities, global_enums, scoped_enums, warnings)
    skipped.flush(warnings)

    return DbmlImportResult(
        name=(project_name or fallback_name).strip(),
        entities=list(entities.values()),
        warnings=warnings,
    )


# ======================================================================
# Block readers
# ======================================================================

def _strip_comments(source: str) -> List[str]:
    return [line[:line.find("//")] if "//" in line else line for line in source.splitlines()]


def _skip_block(lines: List[str], start: int) -> int:
    """Returns the index just past the block whose header is at `start`, or
    -1 when the block is never closed."""
    depth = lines[start].count("{") - lines[start].count("}")
    j = start
    while depth > 0 and j + 1 < len(lines):
        j += 1
        depth += lines[j].count("{") - lines[j].count("}")
    return j + 1 if depth <= 0 else -1


def _header_name(remainder: str) -> Optional[str]:
    """Extracts name from ` <name> {` / ` "name" {` / ` [as alias] name {`."""
    if "[" in remainder:
        as_idx = remainder.find("as")
        if as_idx != -1:
            return _first_quoted(remainder[as_idx + 2:]) or _first_quoted(remainder)
        return _first_quoted(remainder)
    if ":" in remainder.split("{")[0]:
        return None  # settings-style header: `Project { ... }`
    body = remainder.split("{")[0].strip()
    if not body:
        return None
    return _first_quoted(body) or _slugify(body) or None


def _read_project_settings_block(lines: List[str], start: int) -> Optional[str]:
    """Reads `name: 'X'` from the body of a settings-style Project block."""
    depth = lines[start].count("{") - lines[start].count("}")
    j = start + 1
    found: Optional[str] = None
    while depth > 0 and j < len(lines):
        text = lines[j].strip()
        depth += lines[j].count("{") - lines[j].count("}")
        if text.lower().startswith("name"):
            found = _first_quoted(text.split(":", 1)[1]) if ":" in text else None
        j += 1
    return found


def _read_enum(lines: List[str], start: int, entities, global_enums, scoped_enums, diagnostics) -> None:
    line_no = start + 1
    text = lines[start].strip()
    full_name = text.split("{")[0][len("enum"):].strip().strip('"').strip("`").strip()
    if not full_name:
        diagnostics.append(DbmlDiagnostic(line_no, "Anonymous enum declaration is unusable"))
        return
    values = _collect_inline_block_items(text)
    if not values:
        # Multi-line enum body
        depth = text.count("{") - text.count("}")
        j = start
        while depth > 0 and j + 1 < len(lines):
            j += 1
            row = lines[j].strip().rstrip(",")
            depth += lines[j].count("{") - lines[j].count("}")
            if row and row != "}":
                values.append(row.strip('"').strip("`"))
        values = [v for v in values if v]
    if not values:
        diagnostics.append(DbmlDiagnostic(line_no, f"Enum '{full_name}' declares no values"))
        return
    if "." in full_name:
        scope, _, ename = full_name.rpartition(".")
        scoped_enums.setdefault(_slugify(scope), {})[ename.strip().lower()] = values
    else:
        global_enums[full_name.lower()] = values


def _read_table(
    lines: List[str],
    header_idx: int,
    entities: Dict[str, Dict[str, Any]],
    aliases: Dict[str, str],
    refs: List[Tuple[int, str, str]],
    diagnostics: List[DbmlDiagnostic],
    warnings: List[str],
    skipped: DbmlSkippedSettings,
) -> None:
    """Parses `Table <name> [as <alias>] { ... }` including its body rows."""
    text = lines[header_idx].strip()
    line_no = header_idx + 1

    if not text.endswith("{"):
        same_line = re.match(r'^table\s+\S.*$', text, flags=re.IGNORECASE)
        if same_line and "{" in text:
            diagnostics.append(
                DbmlDiagnostic(
                    line_no,
                    "Table body must open on its own line ('{' must end the Table header line); "
                    "compact single-line tables are not supported",
                )
            )
            return

    header_match = re.match(
        r'^(?!$)table\s+(?P<pre>.*?\S)\s*(?:\[\s*as\s+(?P<balias>.*?)\s*\]\s*)?(?:\s+as\s+(?P<salias>[^\s{}]+?))?\s*\{$',
        text, flags=re.IGNORECASE,
    )
    if header_match is None:
        diagnostics.append(DbmlDiagnostic(line_no, f"Malformed table header '{text[:60]}'"))
        return
    body = header_match.group("pre").strip()
    alias_text = header_match.group("balias") or header_match.group("salias")
    anchor = (_first_quoted(alias_text) or _slugify(alias_text)) if alias_text else None

    raw_name = _first_quoted(body) or body.split("{")[0].strip().strip('"').strip("`")
    if not raw_name:
        diagnostics.append(DbmlDiagnostic(line_no, "Anonymous table declaration is unusable"))
        return
    if "." in raw_name:
        schema, _, plain = raw_name.rpartition(".")
        if schema.strip():
            warnings.append(
                f"Table '{plain}': DBML schema qualifier '{schema}' has no engine equivalent and was dropped"
            )
        raw_name = plain

    canonical = _slugify(raw_name)
    if canonical in entities:
        diagnostics.append(DbmlDiagnostic(line_no, f"Duplicate table name '{canonical}'"))
        return
    if anchor:
        aliases[_slugify(anchor)] = canonical

    body_lines = _table_body_rows(lines, header_idx)
    attributes, pk_columns, table_inline_refs = _read_column_rows(
        body_lines, raw_name, diagnostics, warnings, skipped
    )

    if len(pk_columns) > 1:
        diagnostics.append(DbmlDiagnostic(
            header_idx + 1,
            f"Composite primary key on table '{raw_name}' ({', '.join(pk_columns)}); "
            "the engine supports single-column primary keys only"
        ))

    entity: Dict[str, Any] = {
        "name": canonical,
        "record_count": 10,
        "attributes": attributes,
    }
    entities[canonical] = entity
    refs.extend(table_inline_refs)


def _table_body_rows(lines: List[str], header_idx: int) -> List[Tuple[int, str]]:
    """
    Collects the (1-based line number, stripped) rows of the Table block whose
    header is at `header_idx`, skipping spanning `indexes { ... }` sub-blocks.
    """
    rows: List[Tuple[int, str]] = []
    depth = lines[header_idx].count("{") - lines[header_idx].count("}")
    j = header_idx
    while depth > 0 and j + 1 < len(lines):
        j += 1
        text = lines[j].strip()
        row_depth = text.count("{") - text.count("}")
        lowered = text.lower()
        if lowered.startswith("indexes") and row_depth > 0:
            rows.append((j + 1, text.split("{")[0]))
            j = _skip_block(lines, j) - 1  # sub-block balanced: skip without depth delta
            continue
        depth += row_depth
        rows.append((j + 1, text))
    return rows


def _read_standalone_ref(text: str, line_no: int, refs, diagnostics) -> None:
    sides = _parse_ref_sides(text)
    if sides is None:
        diagnostics.append(DbmlDiagnostic(line_no, f"Malformed relationship '{text.strip()[:60]}'"))
        return
    child, parent = sides
    refs.append((line_no, child, parent))


# ======================================================================
# Column and reference parsing
# ======================================================================

def _read_column_rows(
    body_lines: List[Tuple[int, str]],   # (1-based line number, stripped text)
    table_name: str,
    diagnostics: List[DbmlDiagnostic],
    warnings: List[str],
    skipped: DbmlSkippedSettings,
) -> Tuple[List[Dict[str, Any]], List[str], List[Tuple[int, str, str]]]:
    """
    Parses column/relationship rows inside a Table body.
    Returns (attributes, pk_column_names, collected_inline_refs).
    """
    attributes: List[Dict[str, Any]] = []
    pk_columns: List[str] = []
    inline_refs: List[Tuple[int, str, str]] = []

    for line_no, text in body_lines:
        text = text.strip().rstrip(",")
        if not text or text == "}":
            continue
        lowered = text.lower()
        if lowered.startswith("indexes"):
            skipped.indexes.append((table_name, line_no))
            continue
        if lowered.startswith("note"):
            continue
        if lowered.startswith("schema:"):
            warnings.append(
                f"Table '{table_name}': DBML 'schema' setting has no engine equivalent (line {line_no})"
            )
            continue
        if lowered.startswith("ref:"):
            sides = _parse_ref_sides(text)
            if sides is None:
                diagnostics.append(DbmlDiagnostic(line_no, f"Malformed relationship '{text[:60]}'"))
            else:
                child, parent = sides
                inline_refs.append((line_no, child, parent))
            continue

        parsed = _parse_column_row(text, table_name, line_no, diagnostics, warnings, skipped)
        if parsed is None:
            continue
        attr, row_inline_ref = parsed
        if attr["is_primary_key"]:
            pk_columns.append(attr["name"])
        if row_inline_ref is not None:
            target_side = _column_inline_ref_target("ref: " + row_inline_ref)
            if target_side is None:
                diagnostics.append(DbmlDiagnostic(line_no, f"Malformed inline relationship on '{attr['name']}'"))
            else:
                parent = target_side
                inline_refs.append(
                    (line_no, f"{table_name}.{attr['name']}", parent)
                )
        attributes.append(attr)

    return attributes, pk_columns, inline_refs


def _parse_column_row(
    text: str,
    table_name: str,
    line_no: int,
    diagnostics: List[DbmlDiagnostic],
    warnings: List[str],
    skipped: DbmlSkippedSettings,
) -> Optional[Tuple[Dict[str, Any], Optional[str]]]:
    """Parses `name TYPE [pk, not null, note: '...', ref: > parent.col]`."""
    head, settings_clause = text, None
    if "[" in text:
        head, _, tail = text.partition("[")
        settings_clause = tail.rsplit("]", 1)[0]

    tokens = head.strip().split(None, 1)
    if len(tokens) < 2:
        diagnostics.append(DbmlDiagnostic(line_no, f"Cannot parse attribute row '{text[:60]}'"))
        return None
    col_name = _slugify(tokens[0])
    dbml_type = tokens[1].strip()
    if not col_name.isidentifier():
        diagnostics.append(DbmlDiagnostic(line_no, f"Attribute name '{tokens[0]}' is not a valid identifier"))
        return None

    flags = {"pk": False, "not_null": None}
    inline_ref: Optional[str] = None
    if settings_clause is not None:
        for chunk in _split_settings(settings_clause):
            cl = chunk.lower().strip()
            if cl == "pk" or cl == "primary key":
                flags["pk"] = True
            elif cl == "not null":
                flags["not_null"] = True
            elif cl == "null":
                flags["not_null"] = False
            elif cl == "unique":
                pass
            elif cl.startswith("ref:"):
                inline_ref = chunk.split("ref:", 1)[1].strip()
            elif cl.startswith("note:"):
                pass
            else:
                skipped.column_settings.append((table_name, col_name, line_no, chunk))

    attr = _build_attribute(col_name, dbml_type, flags)
    return attr, inline_ref


def _build_attribute(col_name: str, dbml_type: str, flags: Dict[str, bool]) -> Dict[str, Any]:
    base = dbml_type.split("(")[0].strip().strip('"').strip("`").lower()
    gen_type, gen_params = _SCALAR_TYPES.get(base, ("text", {}))
    pk = bool(flags["pk"])
    if pk:
        if base == "uuid":
            gen_type = "uuid"
        elif base in ("int", "integer", "bigint", "serial", "bigserial", "smallint"):
            gen_type = "autoincrement"
            gen_params = {}
        elif base in ("numeric", "decimal"):
            gen_type = "autoincrement"
            gen_params = {}
    nullable = False if flags["not_null"] is True else True
    return {
        "name": col_name,
        "type": gen_type,
        "is_primary_key": pk,
        "nullable": nullable,
        "null_probability": 0.0,
        "params": dict(gen_params),
        "_raw_type": base,
    }


def _column_inline_ref_target(text: str) -> Optional[str]:
    """
    Column-level inline ref: `ref: > parent.attr` or `ref: < parent.attr`
    (current column is the foreign key holder). Returns the parent side.
    """
    body = text[4:] if text.lower().startswith("ref:") else text.strip()
    body = body.strip()
    if "--" in body or not body.startswith((">", "<")):
        return None
    op, target = body[0], body[1:].strip()
    side = parse_side(target)
    if side is None:
        return None
    return f"{side[0]}.{side[1]}"


def _parse_ref_sides(text: str) -> Optional[Tuple[str, str]]:
    """
    `ref: child.attr > parent.attr` or `Ref: parent.attr < child.attr`.
    Returns (child_side, parent_side) as raw 'Entity.attr' strings.
    """
    body = text.strip()
    if body.lower().startswith("ref:"):
        body = body[4:].strip()
    if "--" in body:
        return None
    for op in (">", "<"):
        if op in body:
            left, _, right = body.partition(op)
            child, parent = (left, right) if op == ">" else (right, left)
            if parse_side(child) is None or parse_side(parent) is None:
                return None
            return child.strip(), parent.strip()
    return None


def parse_side(side: str) -> Optional[Tuple[str, str]]:
    """`Entity.attr` -> ('entity', 'attr'); None when malformed."""
    side = side.strip().strip('"')
    if side.count(".") != 1:
        return None
    entity, attr = side.split(".")
    entity, attr = _slugify(entity), _slugify(attr)
    if not entity or not attr:
        return None
    return entity, attr


def _resolve_refs(
    refs: List[Tuple[int, str, str]],
    entities: Dict[str, Dict[str, Any]],
    aliases: Dict[str, str],
    diagnostics: List[DbmlDiagnostic],
) -> None:
    """Wires collected relationships onto child attributes."""
    for line_no, child_side, parent_side in refs:
        parsed_child = parse_side(child_side)
        parsed_parent = parse_side(parent_side)
        if parsed_child is None or parsed_parent is None:
            diagnostics.append(DbmlDiagnostic(line_no, f"Malformed relationship '{child_side} -> {parent_side}'"))
            continue
        child_name, child_attr = parsed_child
        parent_name, parent_attr = parsed_parent
        child_name = aliases.get(child_name, child_name)
        parent_name = aliases.get(parent_name, parent_name)

        parent_entity = entities.get(parent_name)
        if parent_entity is None:
            diagnostics.append(DbmlDiagnostic(line_no, f"Relationship references unknown table '{parent_name}'"))
            continue
        child_entity = entities.get(child_name)
        if child_entity is None:
            diagnostics.append(DbmlDiagnostic(line_no, f"Relationship references unknown table '{child_name}'"))
            continue
        if not any(a["name"] == parent_attr for a in parent_entity["attributes"]):
            diagnostics.append(DbmlDiagnostic(line_no, f"Parent table '{parent_name}' has no attribute '{parent_attr}'"))
            continue

        target = next((a for a in child_entity["attributes"] if a["name"] == child_attr), None)
        if target is None:
            diagnostics.append(DbmlDiagnostic(line_no, f"Child table '{child_name}' has no attribute '{child_attr}'"))
            continue
        if target["is_primary_key"]:
            diagnostics.append(
                DbmlDiagnostic(line_no, f"Attribute '{child_name}.{child_attr}' is a primary key and cannot hold a foreign key")
            )
            continue

        target["type"] = "foreign_key"
        target["fk_target"] = f"{parent_name}.{parent_attr}"


def _apply_fallbacks(
    entities: Dict[str, Dict[str, Any]],
    global_enums: Dict[str, List[str]],
    scoped_enums: Dict[str, Dict[str, List[str]]],
    warnings: List[str],
) -> None:
    """Applies enum resolution, name heuristics, and key normalization."""
    for t_name, entity in entities.items():
        scoped = scoped_enums.get(t_name, {})
        for attr in entity["attributes"]:
            raw = attr.pop("_raw_type", None)
            if raw:
                if raw in global_enums:
                    attr["type"] = "categorical"
                    attr["params"] = {"choices": global_enums[raw]}
                elif raw in scoped:
                    attr["type"] = "categorical"
                    attr["params"] = {"choices": scoped[raw]}
            if attr["type"] == "text":
                for frag, gen in _NAME_HEURISTICS:
                    if frag in attr["name"]:
                        attr["type"] = gen
                        break
            if attr["type"] == "categorical" and "choices" not in attr["params"]:
                attr["params"]["choices"] = ["Option A", "Option B", "Option C"]
            if attr["type"] == "numeric_range" and "is_float" not in attr["params"]:
                attr["params"] = {"min": 1, "max": 1000}


# ======================================================================
# Small utilities
# ======================================================================

def _collect_inline_block_items(text: str) -> List[str]:
    """Values between the first '{' and the next '}' of an enum line."""
    if "{" not in text:
        return []
    inner = text.split("{", 1)[1].split("}", 1)[0]
    return [p.strip().strip('"').strip("`") for p in inner.split(",") if p.strip()]


def _split_settings(clause: str) -> List[str]:
    """Splits `[pk, not null, note: 'a,b']` on unquoted commas."""
    out: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    for ch in clause:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            piece = "".join(buf).strip()
            if piece:
                out.append(piece)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _slugify(value: str) -> str:
    value = value.strip().strip('"').strip("`").strip("'")
    return value.strip().lower().replace("-", "_").replace(" ", "_").strip("_")


def _first_quoted(text: str) -> Optional[str]:
    for quote in ('"', "'", "`"):
        i = text.find(quote)
        if i != -1:
            j = text.find(quote, i + 1)
            if j != -1:
                return text[i + 1:j]
    return None
