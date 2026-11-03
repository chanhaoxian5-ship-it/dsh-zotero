"""DSH safeguards around the unmodified upstream helper (stdlib only)."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.parse
import uuid

import zotero as upstream


class GuardError(Exception):
    pass


def normalize_doi(value):
    value = str(value or "").strip()
    if re.match(r"^https?://(?:dx\.)?doi\.org/", value, flags=re.I):
        value = urllib.parse.urlsplit(value).path.lstrip("/")
    value = urllib.parse.unquote(value).strip()
    value = re.sub(r"^doi\s*:\s*", "", value, flags=re.I)
    value = value.strip().casefold()
    return value if re.fullmatch(r"10\.\d{4,9}/\S+", value) else ""


def normalize_title(value):
    return "".join(c for c in unicodedata.normalize("NFKC", str(value or "")).casefold()
                   if c.isalnum())


def data_of(item):
    return item.get("data", item)


def summary(item):
    data = data_of(item)
    return {**upstream.summarize_item(item), "DOI": data.get("DOI", ""),
            "url": data.get("url", ""), "collections": data.get("collections", [])}


def get_json(path):
    response = upstream.request("/api" + path)
    if not response.ok:
        raise GuardError(f"Read failed: {path}: {response.status}: {response.error or response.text[:200]}")
    return response, upstream.parse_body(response)


def all_items(library="users/0", include_children=False):
    if not re.fullmatch(r"(?:users/0|groups/[1-9]\d*)", library):
        raise GuardError("Invalid --library; use users/0 or groups/NUMERIC_GROUP_ID")
    endpoint = f"/{library}/items" + ("" if include_children else "/top")
    # A failed/incomplete/changing scan must never be treated as an empty library.
    rows, seen, expected, version = [], set(), None, None
    while True:
        response, page = get_json(endpoint + "?" + upstream.query({
            "start": len(rows), "limit": 100, "sort": "dateAdded", "direction": "asc"}))
        headers = {k.casefold(): v for k, v in response.headers.items()}
        try:
            total = int(headers["total-results"])
        except (KeyError, TypeError, ValueError):
            raise GuardError("Cannot establish complete scan: missing/invalid Total-Results")
        current = headers.get("last-modified-version")
        if current is None:
            raise GuardError("Cannot establish stable scan: missing Last-Modified-Version")
        if expected is None:
            expected, version = total, current
        if total != expected or current != version:
            raise GuardError("Library changed during pagination; retry the read before importing")
        if not isinstance(page, list) or (not page and len(rows) < total):
            raise GuardError("Incomplete or invalid library page; import blocked")
        for item in page:
            if not isinstance(item, dict) or not isinstance(data_of(item), dict):
                raise GuardError("Invalid library item; import blocked")
            key = item.get("key") or data_of(item).get("key")
            if not key or key in seen:
                raise GuardError("Repeated/missing item key during pagination; import blocked")
            seen.add(key)
        rows.extend(page)
        if len(rows) == total:
            return [r for r in rows if not data_of(r).get("deleted")]
        if len(rows) > total:
            raise GuardError("Inconsistent library total; import blocked")


def selected_target():
    response = upstream.connector_post("/connector/getSelectedCollection", {})
    if not response.ok:
        raise GuardError(f"Cannot read Zotero selected target: {response.status}: {response.error}")
    body = upstream.parse_body(response)
    if not isinstance(body, dict) or not isinstance(body.get("libraryID"), int):
        raise GuardError("Invalid selected-target response")
    return {k: body.get(k) for k in ("libraryID", "libraryName", "libraryEditable",
                                    "collectionID", "collectionName")}


def target_identity(target):
    return target["libraryID"], target.get("collectionID")


def checked_target(args):
    target = selected_target()
    # Connector uses an internal library ID; do not guess its mapping to a group ID.
    if target["libraryID"] != 1:
        raise GuardError("Guarded import currently supports My Library only; group imports require Zotero's native UI")
    if target.get("libraryEditable") is not True:
        raise GuardError("Selected library is not editable")
    expected = getattr(args, "expect_collection_id", None)
    if expected is not None and target.get("collectionID") != (None if expected == "root" else int(expected)):
        raise GuardError("Selected collection differs from --expect-collection-id; nothing imported")
    return target


def record(raw, fields):
    title = fields.get("title", "").strip()
    doi_raw = fields.get("doi", "").strip()
    doi = normalize_doi(doi_raw)
    if doi_raw and not doi:
        raise GuardError("Invalid DOI in input; fix metadata before importing")
    if not doi and len(normalize_title(title)) < 8:
        raise GuardError("Each record needs a DOI or an informative title for deduplication")
    return {"raw": raw, "title": title, "doi": doi}


def parse_ris(text):
    records, lines, fields, current = [], None, {}, None
    for line in text.lstrip("\ufeff").splitlines():
        match = re.match(r"^([A-Z0-9]{2})  -\s?(.*)$", line)
        if match and match[1] == "TY":
            if lines is not None:
                raise GuardError("Unterminated RIS record")
            lines, fields, current = [line], {}, None
            continue
        if lines is None:
            if line.strip():
                raise GuardError("Unexpected text outside RIS TY/ER records")
            continue
        lines.append(line)
        if match and match[1] == "ER":
            if fields.get("TI") and fields.get("T1") and normalize_title(fields["TI"]) != normalize_title(fields["T1"]):
                raise GuardError("Conflicting RIS TI/T1 titles")
            records.append(record("\n".join(lines) + "\n", {
                "title": fields.get("TI") or fields.get("T1", ""), "doi": fields.get("DO", "")}))
            lines = None
        elif match:
            current = match[1]
            if current in ("TI", "T1", "DO") and current in fields:
                raise GuardError("Repeated RIS identity field; use unambiguous metadata")
            fields[current] = match[2]
        elif line.strip() and current:
            fields[current] += " " + line.strip()
    if lines is not None or not records:
        raise GuardError("RIS must contain complete TY/ER records")
    return records


def parse_bibtex(text):
    # Parse literal values, nested braces and quoted strings. Refuse macros and
    # concatenation instead of guessing identities that differ from the translator.
    text, pos, records = text.lstrip("\ufeff"), 0, []

    def space():
        nonlocal pos
        while pos < len(text):
            if text[pos].isspace():
                pos += 1
            elif text[pos] == "%":
                end = text.find("\n", pos)
                pos = len(text) if end < 0 else end + 1
            else:
                break

    def literal():
        nonlocal pos
        space()
        if pos == len(text):
            raise GuardError("Incomplete BibTeX value")
        start = pos
        opener = text[pos]
        if opener not in '{"':
            value = re.match(r"\d+", text[pos:])
            if not value:
                raise GuardError("BibTeX macros/concatenation are unsupported; export literal values or RIS")
            pos += len(value[0])
            return value[0]
        pos += 1
        value_start, depth = pos, 1
        while pos < len(text):
            char = text[pos]
            if char == "\\":
                pos += 2
                continue
            if opener == "{":
                if char == "{": depth += 1
                if char == "}": depth -= 1
                done = depth == 0
            else:
                done = char == '"'
            if done:
                value = text[value_start:pos]
                pos += 1
                return value
            pos += 1
        raise GuardError(f"Unterminated BibTeX value at {start}")

    while True:
        space()
        if pos == len(text): break
        start = pos
        entry = re.match(r"@([a-zA-Z]+)\s*([({])", text[pos:])
        if not entry or entry[1].casefold() in ("string", "preamble", "comment"):
            raise GuardError("Use BibTeX records with literal fields; directives/free text are unsupported")
        close = "}" if entry[2] == "{" else ")"
        pos += len(entry[0])
        key = re.match(r"\s*[^\s,{}()]+\s*,", text[pos:])
        if not key: raise GuardError("Invalid BibTeX citation key")
        pos += len(key[0])
        fields = {}
        while True:
            space()
            if pos < len(text) and text[pos] == close:
                pos += 1
                break
            field = re.match(r"([a-zA-Z][\w-]*)\s*=", text[pos:])
            if not field: raise GuardError("Invalid BibTeX field")
            name = field[1].casefold()
            if name in fields: raise GuardError("Repeated BibTeX field")
            pos += len(field[0])
            fields[name] = literal()
            space()
            if pos < len(text) and text[pos] == ",": pos += 1
            elif pos >= len(text) or text[pos] != close:
                raise GuardError("Unsupported BibTeX concatenation or missing field separator")
        # Strip formatting braces only for title comparison, not from imported text.
        if "title" in fields:
            if "\\" in fields["title"]:
                raise GuardError("BibTeX title contains TeX commands; use plain-title BibTeX or RIS for reliable matching")
            fields["title"] = re.sub(r"[{}]", "", fields["title"])
        records.append(record(text[start:pos], fields))
    if not records: raise GuardError("No BibTeX records found")
    return records


def read_records(args):
    text = Path(args.file).expanduser().read_text(encoding="utf-8-sig") if args.file else args.text
    if not text: raise GuardError("Empty import input")
    kind = getattr(args, "format", None) or ("ris" if args.command == "import-ris" else "bibtex")
    return (parse_ris if kind == "ris" else parse_bibtex)(text)


def matches(rec, items):
    doi, title = rec["doi"], normalize_title(rec["title"])
    exact, possible = [], []
    for item in items:
        data = data_of(item)
        if data.get("itemType") in ("attachment", "note", "annotation"): continue
        item_doi = normalize_doi(data.get("DOI"))
        if doi and item_doi == doi:
            exact.append(item)
        elif title and normalize_title(data.get("title")) == title:
            possible.append(item)
    return exact, possible


def make_plan(records, items):
    plan, seen = [], set()
    for index, rec in enumerate(records):
        exact, possible = matches(rec, items)
        identity = rec["doi"] or "title:" + normalize_title(rec["title"])
        if identity in seen:
            decision = "duplicate-in-input"
        elif exact:
            decision = "existing"
        elif possible:
            decision = "ambiguous"
        else:
            decision = "new"
        # Same-title records without the same DOI are not silently merged.
        if decision == "new" and any(normalize_title(r["title"]) == normalize_title(rec["title"])
                                     for r in records[:index] if r["title"] and rec["title"]):
            decision = "ambiguous"
        seen.add(identity)
        plan.append({"index": index, "title": rec["title"], "doi": rec["doi"],
                     "decision": decision, "matches": [summary(i) for i in (exact or possible)]})
    return plan


def state_path():
    root = Path(os.environ.get("ZOTERO_DSH_STATE_DIR") or
                (Path(os.environ.get("DSH_HOME") or Path.home() / ".dsh") / "state" / "dsh-zotero"))
    root.mkdir(parents=True, exist_ok=True)
    endpoint = hashlib.sha256(upstream.DEFAULT_BASE_URL.rstrip("/").encode()).hexdigest()[:24]
    return root / (endpoint + "-personal.json")


@contextmanager
def import_lock(path):
    with path.with_suffix(".lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise GuardError("Another DSH Zotero import is running; no request sent")
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt": msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save_state(path, value):
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def verify(records, items, before):
    result = []
    for rec in records:
        exact, possible = matches(rec, items)
        found = exact if rec["doi"] else possible
        found = [r for r in found if (r.get("key") or data_of(r).get("key")) not in before]
        if len(found) != 1:
            return None
        result.append(summary(found[0]))
    return result


def load_state(path):
    if not path.exists(): return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict): raise ValueError()
        if value and (value.get("status") not in ("pending", "verified")
                      or not isinstance(value.get("records"), list)
                      or not value["records"] or not isinstance(value.get("before"), list)
                      or not all(isinstance(r, dict) and isinstance(r.get("title"), str)
                                 and isinstance(r.get("doi"), str) for r in value["records"])):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise GuardError(f"Unreadable import journal; no write allowed: {path}")


def reconcile(path, state, items):
    if state.get("status") != "pending": return None
    found = verify(state["records"], items, state["before"])
    if found is None:
        raise GuardError(f"Previous import is unresolved; do not retry or change session. Inspect Zotero and import-status. Journal: {path}")
    state.update(status="verified", imported=found)
    save_state(path, state)
    return found


def guarded_import(args):
    if not args.yes:
        raise GuardError("Import requires --yes; use plan-import for read-only preview")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise GuardError("--timeout must be a positive finite number")
    records = read_records(args)
    path = state_path()
    with import_lock(path):
        target = checked_target(args)
        items = all_items()
        reconcile(path, load_state(path), items)
        plan = make_plan(records, items)
        if any(r["decision"] == "ambiguous" for r in plan):
            upstream.dump_json({"status": "blocked", "reason": "ambiguous-identity", "target": target, "records": plan})
            return 2
        fresh = [records[p["index"]] for p in plan if p["decision"] == "new"]
        if not fresh:
            upstream.dump_json({"status": "existing", "target": target, "records": plan,
                                "note": "Reused library matches; collection memberships were not changed"})
            return 0
        # Connector chooses its current UI target; check again just before POST.
        if target_identity(checked_target(args)) != target_identity(target):
            raise GuardError("Zotero target changed during preflight; nothing imported")
        state = {"status": "pending", "session": args.session or "dsh-" + uuid.uuid4().hex,
                 "created": time.time(), "target": target,
                 "records": [{k: r[k] for k in ("title", "doi")} for r in fresh],
                 "before": [r.get("key") or data_of(r).get("key") for r in items]}
        save_state(path, state)  # Persist before any possible server write.
        response = upstream.request("/connector/import?" + upstream.query({"session": state["session"]}),
                                    method="POST", data="\n".join(r["raw"] for r in fresh),
                                    headers={"Content-Type": "text/plain"}, timeout=args.timeout)
        # Even HTTP 201 is not proof that all intended records are readable.
        found = None
        for attempt in range(3):
            try: found = verify(state["records"], all_items(), state["before"])
            except GuardError: pass
            if found is not None: break
            if attempt < 2: time.sleep(0.2)
        if found is None:
            raise GuardError(f"Import outcome unknown (HTTP {response.status}); automatic resubmission blocked. Run import-status. Journal: {path}")
        after = selected_target()
        changed = target_identity(after) != target_identity(target)
        state.update(status="verified", imported=found, targetChanged=changed, observedTarget=after)
        save_state(path, state)
        upstream.dump_json({"status": "verified-target-changed" if changed else "imported" if response.ok else "recovered", "target": target,
                            "targetChanged": changed,
                            "session": state["session"], "imported": found, "records": plan})
        return 2 if changed else 0


def cmd_search(args):
    items = all_items(args.library)
    doi = normalize_doi(args.query)
    if doi:
        items = [r for r in items if normalize_doi(data_of(r).get("DOI")) == doi]
    else:
        terms = [normalize_title(t) for t in args.query.split() if normalize_title(t)]
        items = [r for r in items if all(t in normalize_title(json.dumps(data_of(r), ensure_ascii=False)) for t in terms)]
    rows = [summary(r) for r in items]
    if args.with_bibtex_keys:
        if args.library != "users/0": raise GuardError("BibTeX key lookup currently supports users/0 only")
        for row in rows:
            keys = upstream.extract_bibtex_keys(upstream.export_bibtex(row["key"]))
            row["bibtexKey"] = keys[0] if keys else None
    upstream.dump_json(rows) if args.json else upstream.print_items(rows)


def duplicates(args):
    items = all_items(args.library)
    groups = {}
    for item in items:
        d = data_of(item)
        if d.get("itemType") in ("attachment", "note", "annotation"): continue
        for method, identity in (("doi", normalize_doi(d.get("DOI"))), ("title", normalize_title(d.get("title")))):
            if identity: groups.setdefault((method, identity), []).append(summary(item))
    upstream.dump_json({"library": args.library, "readOnly": True,
                        "groups": [{"method": k[0], "identity": k[1], "items": v}
                                   for k, v in groups.items() if len(v) > 1]})


def build_parser():
    parser = upstream.build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices
    for name in ("search", "inventory"):
        commands[name].add_argument("--library", default="users/0")
    commands["search"].set_defaults(func=cmd_search)
    commands["inventory"].set_defaults(func=lambda a: upstream.dump_json(
        [summary(r) for r in all_items(a.library, a.include_children)]) if a.json else upstream.print_items(
        [summary(r) for r in all_items(a.library, a.include_children)]))
    commands["selected-target"].set_defaults(func=lambda a: upstream.dump_json(selected_target()))
    for name in ("import-ris", "import-bibtex"):
        commands[name].add_argument("--timeout", type=float, default=30)
        commands[name].add_argument("--expect-collection-id", help="Internal numeric collection ID or root")
        commands[name].set_defaults(func=guarded_import)
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    plan = subs.add_parser("plan-import", help="Read-only deduplication and target preview")
    plan.add_argument("--format", choices=("ris", "bibtex"), required=True)
    source = plan.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--text")
    plan.add_argument("--expect-collection-id")
    plan.set_defaults(func=lambda a: upstream.dump_json({"readOnly": True, "target": checked_target(a),
                     "records": make_plan(read_records(a), all_items())}))
    audit = subs.add_parser("duplicates", help="Read-only exact DOI/title duplicate candidates")
    audit.add_argument("--library", default="users/0")
    audit.set_defaults(func=duplicates)
    status = subs.add_parser("import-status", help="Reconcile journal with current library; never submit imports")
    def import_status(a):
        path = state_path()
        with import_lock(path):
            state = load_state(path)
            visible = {k: v for k, v in state.items() if k != "before"}
            try:
                reconcile(path, state, all_items())
            except GuardError as exc:
                upstream.dump_json({"journal": str(path), **visible, "verificationError": str(exc)})
                return 2
            upstream.dump_json({"journal": str(path), **{k: v for k, v in state.items() if k != "before"}})
    status.set_defaults(func=import_status)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
        return result if isinstance(result, int) else 0
    except (GuardError, OSError, ValueError) as exc:
        upstream.dump_json({"status": "blocked", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
