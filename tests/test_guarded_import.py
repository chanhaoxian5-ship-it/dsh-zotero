"""Black-box HTTP/CLI regression tests. Never access a real Zotero library."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "skills/zotero/scripts/zotero_dsh.py"


def item(key, title="A synthetic genome editing paper", doi="10.1234/synthetic", collections=None):
    return {"key": key, "data": {"itemType": "journalArticle", "title": title, "DOI": doi,
                                "date": "2026", "collections": collections or []}}


def ris(title="A synthetic genome editing paper", doi="10.1234/synthetic"):
    return f"TY  - JOUR\nTI  - {title}\nDO  - {doi}\nER  -\n"


class Scenario:
    def __init__(self):
        self.items = []
        self.posts = []
        self.target = {"libraryID": 1, "libraryName": "Synthetic library", "libraryEditable": True,
                       "collectionID": 7, "collectionName": "Synthetic collection"}
        self.target_reads = 0
        self.mode = "normal"
        self.page_mode = "normal"
        self.started = threading.Event()
        self.release = threading.Event()
        self.paths = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def reply(self, value, status=200, headers=None):
        data = json.dumps(value).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items(): self.send_header(k, str(v))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):
        state = self.server.scenario
        url = urlsplit(self.path)
        state.paths.append(url.path)
        if not url.path.endswith(("/items/top", "/items")):
            return self.reply({}, 404)
        if state.page_mode == "unauthorized": return self.reply({}, 401)
        args = parse_qs(url.query)
        start = int(args.get("start", [0])[0])
        page = state.items[start:start + 100]
        headers = {"Total-Results": len(state.items), "Last-Modified-Version": "1"}
        if state.page_mode == "missing-total": headers.pop("Total-Results")
        if state.page_mode == "changing" and start: headers["Last-Modified-Version"] = "2"
        if state.page_mode == "truncated" and start: page = []
        return self.reply(page, headers=headers)

    def do_POST(self):
        state = self.server.scenario
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        if self.path == "/connector/getSelectedCollection":
            state.target_reads += 1
            if state.mode == "switch-before" and state.target_reads == 2:
                state.target["collectionID"] = 8
            return self.reply({**state.target, "tags": {"DO_NOT_LEAK": ["huge synthetic list"]}})
        if not self.path.startswith("/connector/import?"): return self.reply({}, 404)
        state.posts.append({"body": body, "path": self.path})
        state.started.set()
        if state.mode == "hold": state.release.wait(10)
        if state.mode not in ("drop-before", "empty-success"):
            titles = re.findall(r"^TI  - (.*)$", body, re.M)
            dois = re.findall(r"^DO  - (.*)$", body, re.M)
            if not titles:
                titles = re.findall(r"title\s*=\s*\{([^}]+)\}", body, re.I)
                dois = re.findall(r"doi\s*=\s*\{([^}]+)\}", body, re.I)
            if state.mode == "partial": titles = titles[:1]
            for i, title in enumerate(titles):
                state.items.append(item(f"NEW{len(state.items):05}", title, dois[i] if i < len(dois) else ""))
        if state.mode == "switch-after": state.target["collectionID"] = 9
        if state.mode in ("drop-after", "drop-before"):
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        self.reply([], 201)


class GuardedImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Scenario()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.scenario = self.state
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env = {**os.environ, "ZOTERO_LOCAL_BASE_URL": f"http://127.0.0.1:{self.server.server_port}",
                    "ZOTERO_DSH_STATE_DIR": self.tmp.name, "PYTHONDONTWRITEBYTECODE": "1"}

    def tearDown(self):
        self.state.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.tmp.cleanup()

    def command(self, *args):
        return [sys.executable, "-X", "utf8", str(SCRIPT), *args]

    def run_cli(self, *args):
        result = subprocess.run(self.command(*args), env=self.env, capture_output=True, text=True,
                                encoding="utf-8", timeout=15)
        self.assertFalse(result.stderr, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def import_ris(self, text=None, *extra):
        return self.run_cli("import-ris", "--text", text or ris(), "--yes", *extra)

    def test_doi_url_case_and_full_pagination(self):
        self.state.items = [item(f"K{i:07}", f"Unrelated title {i}", f"10.9999/{i}") for i in range(100)]
        self.state.items += [item("MATCH001", doi="DOI:10.1234/Synthetic")]
        code, rows = self.run_cli("search", "https://doi.org/10.1234%2FSYNTHETIC", "--json")
        self.assertEqual(code, 0)
        self.assertEqual([r["key"] for r in rows], ["MATCH001"])
        self.assertEqual(rows[0]["DOI"], "DOI:10.1234/Synthetic")

    def test_doi_url_tracking_query_is_not_part_of_identity(self):
        self.state.items = [item('TRACK001')]
        code, rows = self.run_cli('search', 'https://doi.org/10.1234/synthetic?utm_source=example#abstract', '--json')
        self.assertEqual(code, 0)
        self.assertEqual([r['key'] for r in rows], ['TRACK001'])

    def test_existing_in_other_collection_is_not_imported(self):
        self.state.items = [item("EXIST001", collections=["OTHER001"])]
        code, out = self.import_ris()
        self.assertEqual((code, out["status"]), (0, "existing"))
        self.assertEqual(out["records"][0]["matches"][0]["collections"], ["OTHER001"])
        self.assertEqual(self.state.posts, [])

    def test_missing_total_blocks_write(self):
        self.state.page_mode = "missing-total"
        code, out = self.import_ris()
        self.assertEqual(code, 2)
        self.assertIn("Total-Results", out["error"])
        self.assertEqual(self.state.posts, [])

    def test_changed_library_version_blocks_write(self):
        self.state.items = [item(f"K{i:07}", f"Other {i}", f"10.9999/{i}") for i in range(101)]
        self.state.page_mode = "changing"
        code, out = self.import_ris()
        self.assertEqual(code, 2)
        self.assertIn("changed", out["error"])
        self.assertEqual(self.state.posts, [])

    def test_truncated_pagination_blocks_write(self):
        self.state.items = [item(f"K{i:07}", f"Other {i}", f"10.9999/{i}") for i in range(101)]
        self.state.page_mode = "truncated"
        code, _ = self.import_ris()
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_failed_read_is_not_an_empty_library(self):
        self.state.page_mode = "unauthorized"
        code, _ = self.import_ris()
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_batch_skips_existing_and_duplicates_in_input(self):
        self.state.items = [item("EXIST001")]
        new = ris("An entirely new synthetic paper", "10.2345/new")
        code, out = self.import_ris(ris() + new + new)
        self.assertEqual((code, out["status"]), (0, "imported"))
        self.assertEqual([r["decision"] for r in out["records"]], ["existing", "new", "duplicate-in-input"])
        self.assertEqual(len(self.state.posts), 1)
        self.assertEqual(self.state.posts[0]["body"].count("TY  -"), 1)
        self.assertEqual(len(out["imported"]), 1)

    def test_different_doi_same_title_requires_resolution(self):
        self.state.items = [item("PREPRINT", doi="10.2345/preprint")]
        code, out = self.import_ris()
        self.assertEqual((code, out["reason"]), (2, "ambiguous-identity"))
        self.assertEqual(self.state.posts, [])

    def test_title_only_candidate_does_not_silently_merge(self):
        self.state.items = [item("OLD00001", doi="")]
        code, out = self.import_ris()
        self.assertEqual(code, 2)
        self.assertEqual(out["records"][0]["matches"][0]["key"], "OLD00001")
        self.assertEqual(self.state.posts, [])

    def test_malformed_ris_blocks_entire_batch(self):
        code, _ = self.import_ris(ris() + "TY  - JOUR\nTI  - Incomplete record\n")
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_bibtex_nested_literal_preview(self):
        code, out = self.run_cli("plan-import", "--format", "bibtex", "--text",
                                 '@article{test, title={A {nested} synthetic title}, doi="10.2345/new", year=2026}')
        self.assertEqual(code, 0)
        self.assertEqual(out["records"][0]["title"], "A nested synthetic title")
        self.assertTrue(out["readOnly"])
        self.assertEqual(self.state.posts, [])

    def test_bibtex_macro_is_not_guessed(self):
        code, _ = self.run_cli("import-bibtex", "--text", '@article{t,title=unknown,doi={10.2345/new}}', "--yes")
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_bibtex_existing_doi_does_not_write(self):
        self.state.items = [item("EXIST001")]
        code, out = self.run_cli("import-bibtex", "--text", '@article{t,title={Any title},doi={10.1234/synthetic}}', "--yes")
        self.assertEqual((code, out["status"]), (0, "existing"))
        self.assertEqual(self.state.posts, [])

    def test_import_without_yes_is_read_only(self):
        code, _ = self.run_cli("import-ris", "--text", ris())
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_wrong_expected_collection_blocks_write(self):
        code, _ = self.import_ris(None, "--expect-collection-id", "8")
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_target_change_during_preflight_blocks_write(self):
        self.state.mode = "switch-before"
        code, _ = self.import_ris()
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_lost_response_after_commit_recovers_without_resubmit(self):
        self.state.mode = "drop-after"
        code, out = self.import_ris()
        self.assertEqual((code, out["status"]), (0, "recovered"))
        code, out = self.import_ris()
        self.assertEqual((code, out["status"]), (0, "existing"))
        self.assertEqual(len(self.state.posts), 1)

    def test_uncertain_import_blocks_new_process_and_new_input(self):
        self.state.mode = "drop-before"
        first_code, _ = self.import_ris()
        second_code, out = self.import_ris(ris("Different new synthetic paper", "10.2345/other"))
        self.assertEqual((first_code, second_code), (2, 2))
        self.assertIn("unresolved", out["error"])
        self.assertEqual(len(self.state.posts), 1)
        code, status = self.run_cli("import-status")
        self.assertEqual((code, status["status"]), (2, "pending"))
        self.assertTrue(status["session"].startswith("dsh-"))

    def test_http_201_without_readback_is_not_success(self):
        self.state.mode = "empty-success"
        code, out = self.import_ris()
        self.assertEqual(code, 2)
        self.assertIn("outcome unknown", out["error"])

    def test_partial_batch_never_resubmits(self):
        self.state.mode = "partial"
        batch = ris() + ris("Second distinct synthetic paper", "10.2345/second")
        self.assertEqual(self.import_ris(batch)[0], 2)
        self.assertEqual(self.import_ris(batch)[0], 2)
        self.assertEqual(len(self.state.posts), 1)
        self.assertEqual(len(self.state.items), 1)

    def test_late_completion_reconciles_without_another_post(self):
        self.state.mode = "drop-before"
        self.assertEqual(self.import_ris()[0], 2)
        self.state.items.append(item("LATE0001"))
        code, out = self.run_cli("import-status")
        self.assertEqual((code, out["status"]), (0, "verified"))
        self.assertEqual(out["imported"][0]["key"], "LATE0001")
        self.assertNotIn("before", out)
        self.assertEqual(self.import_ris()[1]["status"], "existing")
        self.assertEqual(len(self.state.posts), 1)

    def test_killed_client_releases_lock_but_retains_pending_journal(self):
        self.state.mode = "hold"
        first = subprocess.Popen(self.command("import-ris", "--text", ris(), "--yes"), env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertTrue(self.state.started.wait(5))
            first.kill()
            first.communicate(timeout=5)
            code, out = self.import_ris()
            self.assertEqual(code, 2)
            self.assertIn("unresolved", out["error"])
            self.assertEqual(len(self.state.posts), 1)
        finally:
            self.state.release.set()
            if first.poll() is None:
                first.kill()
                first.communicate(timeout=5)

    def test_corrupt_journal_blocks_import(self):
        self.state.mode = "drop-before"
        self.import_ris()
        state_file = next(Path(self.tmp.name).glob('*.json'))
        state_file.write_text('{"status":"pending"}', encoding='utf-8')
        code, out = self.import_ris()
        self.assertEqual(code, 2)
        self.assertIn('Unreadable import journal', out['error'])
        self.assertEqual(len(self.state.posts), 1)

    def test_target_output_omits_tag_inventory(self):
        code, out = self.run_cli('selected-target', '--json')
        self.assertEqual(code, 0)
        self.assertNotIn('tags', out)

    def test_unsupported_bibtex_title_does_not_bypass_identity_check(self):
        code, _ = self.run_cli('import-bibtex', '--text',
                               r'@article{t,title={An \textit{encoded} title},doi={10.2345/new}}', '--yes')
        self.assertEqual(code, 2)
        self.assertEqual(self.state.posts, [])

    def test_concurrent_process_cannot_bypass_preflight(self):
        self.state.mode = "hold"
        first = subprocess.Popen(self.command("import-ris", "--text", ris(), "--yes"), env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            self.assertTrue(self.state.started.wait(5))
            code, out = self.import_ris()
            self.assertEqual(code, 2)
            self.assertIn("Another", out["error"])
        finally:
            self.state.release.set()
            stdout, stderr = first.communicate(timeout=10)
        self.assertEqual((first.returncode, stderr), (0, ""), stdout)
        self.assertEqual(len(self.state.posts), 1)

    def test_group_target_not_mapped_by_guessing(self):
        self.state.target["libraryID"] = 2
        code, out = self.import_ris()
        self.assertEqual(code, 2)
        self.assertIn("My Library", out["error"])
        self.assertEqual(self.state.posts, [])

    def test_target_change_after_import_returns_warning_not_resubmit(self):
        self.state.mode = "switch-after"
        code, out = self.import_ris()
        self.assertEqual((code, out["status"]), (2, "verified-target-changed"))
        self.assertTrue(out["targetChanged"])
        self.assertEqual(len(self.state.posts), 1)

    def test_duplicate_report_is_read_only(self):
        self.state.items = [item("FIRST001"), item("SECOND01", collections=["OTHER001"])]
        code, out = self.run_cli("duplicates")
        self.assertEqual(code, 0)
        self.assertTrue(out["readOnly"])
        self.assertEqual(len(out["groups"]), 2)
        self.assertEqual(len(self.state.items), 2)
        self.assertEqual(self.state.posts, [])

    def test_group_search_uses_explicit_group_id(self):
        self.state.items = [item("GROUP001")]
        code, out = self.run_cli("search", "10.1234/synthetic", "--library", "groups/123", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(out[0]["key"], "GROUP001")
        self.assertIn("/api/groups/123/items/top", self.state.paths)


if __name__ == "__main__":
    unittest.main()
