#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json
import sqlite3
from datetime import datetime
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "tasks.db")
HOST = "127.0.0.1"
PORT = 8000


def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            done INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def row_to_task(row):
    # row: (id, title, done, created_at)
    return {
        "id": row[0],
        "title": row[1],
        "done": bool(row[2]),
        "createdAt": row[3]
    }


class TaskAPIHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload=None, headers=None):
        body = b""
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()

        if body:
            self.wfile.write(body)

    def _send_status(self, status_code, headers=None):
        self.send_response(status_code)
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()

    def _read_json_body(self):
        length = self.headers.get("Content-Length")
        if not length:
            return None, "Missing Content-Length"
        try:
            length_int = int(length)
        except ValueError:
            return None, "Invalid Content-Length"

        raw = self.rfile.read(length_int)
        if not raw:
            return None, "Empty body"
        try:
            return json.loads(raw.decode("utf-8")), None
        except Exception:
            return None, "Invalid JSON"

    def _parse_path(self):
        """
        Returns: (resource, id_or_none)
        Examples:
          /tasks        -> ("tasks", None)
          /tasks/3      -> ("tasks", 3)
        """
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if len(parts) == 1:
            return parts[0], None
        if len(parts) == 2:
            resource = parts[0]
            try:
                rid = int(parts[1])
            except ValueError:
                return resource, "invalid_id"
            return resource, rid
        return None, None

    def _db(self):
        return sqlite3.connect(DB_FILE)

    # --- GET ---
    def do_GET(self):
        resource, rid = self._parse_path()
        if resource != "tasks":
            self._send_json(404, {"error": "Not Found"})
            return
        if rid == "invalid_id":
            self._send_json(400, {"error": "Invalid id"})
            return

        con = self._db()
        cur = con.cursor()

        if rid is None:
            # GET /tasks (optionally: ?done=true/false)
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            done_filter = qs.get("done", [None])[0]

            if done_filter is None:
                cur.execute("SELECT id, title, done, created_at FROM tasks ORDER BY id")
                rows = cur.fetchall()
            else:
                if done_filter.lower() not in ("true", "false"):
                    con.close()
                    self._send_json(400, {"error": "done must be true or false"})
                    return
                done_int = 1 if done_filter.lower() == "true" else 0
                cur.execute("SELECT id, title, done, created_at FROM tasks WHERE done=? ORDER BY id", (done_int,))
                rows = cur.fetchall()

            con.close()
            self._send_json(200, [row_to_task(r) for r in rows])
            return

        # GET /tasks/{id}
        cur.execute("SELECT id, title, done, created_at FROM tasks WHERE id=?", (rid,))
        row = cur.fetchone()
        con.close()

        if not row:
            self._send_json(404, {"error": "Task not found"})
            return
        self._send_json(200, row_to_task(row))

    # --- POST ---
    def do_POST(self):
        resource, rid = self._parse_path()
        if resource != "tasks":
            self._send_json(404, {"error": "Not Found"})
            return
        if rid == "invalid_id":
            self._send_json(400, {"error": "Invalid id"})
            return

        data, err = self._read_json_body()
        if err:
            self._send_json(400, {"error": err})
            return

        # validate minimal fields
        title = data.get("title")
        done = data.get("done", False)

        if not isinstance(title, str) or not title.strip():
            self._send_json(400, {"error": "title is required and must be a non-empty string"})
            return
        if not isinstance(done, bool):
            self._send_json(400, {"error": "done must be boolean"})
            return

        created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        done_int = 1 if done else 0

        con = self._db()
        cur = con.cursor()

        if rid is None:
            # POST /tasks -> server assigns id
            cur.execute(
                "INSERT INTO tasks(title, done, created_at) VALUES(?,?,?)",
                (title.strip(), done_int, created_at)
            )
            new_id = cur.lastrowid
            con.commit()
            con.close()

            headers = {"Location": f"/tasks/{new_id}"}
            self._send_json(201, {"id": new_id, "title": title.strip(), "done": done, "createdAt": created_at}, headers=headers)
            return

        # POST /tasks/{id} -> client chosen id
        cur.execute("SELECT id FROM tasks WHERE id=?", (rid,))
        if cur.fetchone():
            con.close()
            self._send_json(409, {"error": "Task with this id already exists"})
            return

        cur.execute(
            "INSERT INTO tasks(id, title, done, created_at) VALUES(?,?,?,?)",
            (rid, title.strip(), done_int, created_at)
        )
        con.commit()
        con.close()

        headers = {"Location": f"/tasks/{rid}"}
        self._send_json(201, {"id": rid, "title": title.strip(), "done": done, "createdAt": created_at}, headers=headers)

     # --- PUT ---
    def do_PUT(self):
        resource, rid = self._parse_path()
        if resource != "tasks":
            self._send_json(404, {"error": "Not Found"})
            return
        if rid == "invalid_id":
            self._send_json(400, {"error": "Invalid id"})
            return

        data, err = self._read_json_body()
        if err:
            self._send_json(400, {"error": err})
            return

        con = self._db()
        cur = con.cursor()

        # PUT /tasks -> replace entire collection 
   
        if rid is None:
            if not isinstance(data, list):
                con.close()
                self._send_json(400, {"error": "Body must be a JSON array of tasks"})
                return

            # validate + normalize
            normalized = []
            seen_ids = set()

            for item in data:
                if not isinstance(item, dict):
                    con.close()
                    self._send_json(400, {"error": "Each item must be an object"})
                    return

                tid = item.get("id")
                title = item.get("title")
                done = item.get("done")

                if not isinstance(tid, int) or tid <= 0:
                    con.close()
                    self._send_json(400, {"error": "Each task must have a positive integer id"})
                    return
                if tid in seen_ids:
                    con.close()
                    self._send_json(400, {"error": f"Duplicate id in body: {tid}"})
                    return
                seen_ids.add(tid)

                if not isinstance(title, str) or not title.strip():
                    con.close()
                    self._send_json(400, {"error": f"Task {tid}: title must be a non-empty string"})
                    return
                if not isinstance(done, bool):
                    con.close()
                    self._send_json(400, {"error": f"Task {tid}: done must be boolean"})
                    return

                normalized.append((tid, title.strip(), 1 if done else 0))

            try:
                # Replace collection:
       
                cur.execute("BEGIN")

                if normalized:
                    placeholders = ",".join(["?"] * len(normalized))
                    ids = [t[0] for t in normalized]
                    cur.execute(f"DELETE FROM tasks WHERE id NOT IN ({placeholders})", ids)

                    for tid, title, done_int in normalized:
                        cur.execute("SELECT created_at FROM tasks WHERE id=?", (tid,))
                        row = cur.fetchone()
                        if row:
                            # update existing, keep created_at
                            cur.execute(
                                "UPDATE tasks SET title=?, done=? WHERE id=?",
                                (title, done_int, tid)
                            )
                        else:
                            # insert new with created_at now
                            created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                            cur.execute(
                                "INSERT INTO tasks(id, title, done, created_at) VALUES(?,?,?,?)",
                                (tid, title, done_int, created_at)
                            )
                else:
                    cur.execute("DELETE FROM tasks")

                con.commit()
                con.close()
                self._send_status(204)
            except Exception:
                con.rollback()
                con.close()
                self._send_json(500, {"error": "Internal Server Error"})
            return

        # PUT /tasks/{id} -> replace a single resource 
        title = data.get("title")
        done = data.get("done")

        if not isinstance(title, str) or not title.strip():
            con.close()
            self._send_json(400, {"error": "title is required and must be a non-empty string"})
            return
        if not isinstance(done, bool):
            con.close()
            self._send_json(400, {"error": "done is required and must be boolean"})
            return

        try:
            cur.execute("SELECT id FROM tasks WHERE id=?", (rid,))
            if not cur.fetchone():
                con.close()
                self._send_json(404, {"error": "Task not found"})
                return

            done_int = 1 if done else 0
            cur.execute("UPDATE tasks SET title=?, done=? WHERE id=?", (title.strip(), done_int, rid))
            con.commit()
            con.close()
            self._send_status(204)
        except Exception:
            con.close()
            self._send_json(500, {"error": "Internal Server Error"})

    # --- DELETE ---
    def do_DELETE(self):
        resource, rid = self._parse_path()
        if resource != "tasks":
            self._send_json(404, {"error": "Not Found"})
            return
        if rid == "invalid_id":
            self._send_json(400, {"error": "Invalid id"})
            return

        con = self._db()
        cur = con.cursor()

        # DELETE /tasks -> delete collection (optionally filter by ?done=true/false)
        if rid is None:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            done_filter = qs.get("done", [None])[0]

            try:
                if done_filter is None:
                    cur.execute("DELETE FROM tasks")
                else:
                    if done_filter.lower() not in ("true", "false"):
                        con.close()
                        self._send_json(400, {"error": "done must be true or false"})
                        return
                    done_int = 1 if done_filter.lower() == "true" else 0
                    cur.execute("DELETE FROM tasks WHERE done=?", (done_int,))

                con.commit()
                con.close()
                self._send_status(204)
            except Exception:
                con.close()
                self._send_json(500, {"error": "Internal Server Error"})
            return

        # DELETE /tasks/{id} -> delete single resource 
        try:
            cur.execute("SELECT id FROM tasks WHERE id=?", (rid,))
            if not cur.fetchone():
                con.close()
                self._send_json(404, {"error": "Task not found"})
                return

            cur.execute("DELETE FROM tasks WHERE id=?", (rid,))
            con.commit()
            con.close()
            self._send_status(204)
        except Exception:
            con.close()
            self._send_json(500, {"error": "Internal Server Error"})

    # make logs cleaner
    def log_message(self, format, *args):
        return


def main():
    init_db()
    server = HTTPServer((HOST, PORT), TaskAPIHandler)
    print(f"Server running on http://{HOST}:{PORT}")
    print("Endpoints: /tasks and /tasks/{id}")
    server.serve_forever()


if __name__ == "__main__":
    main()
