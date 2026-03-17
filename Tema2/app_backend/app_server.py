#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, quote
import urllib.request
import urllib.error
import json
import os
import socket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
HOST = "127.0.0.1"
DEFAULT_TIMEOUT = 6


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()
PORT = int(CONFIG.get("app_port", 8080))


def send_json(handler, status_code, payload=None, extra_headers=None):
    body = b""
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(body)))
    if extra_headers:
        for k, v in extra_headers.items():
            handler.send_header(k, v)
    handler.end_headers()
    if body:
        handler.wfile.write(body)



def read_json_body(handler):
    length = handler.headers.get("Content-Length")
    if not length:
        return None, "Missing Content-Length"
    try:
        raw = handler.rfile.read(int(length))
    except Exception:
        return None, "Could not read request body"

    if not raw:
        return None, "Empty body"

    try:
        return json.loads(raw.decode("utf-8")), None
    except Exception:
        return None, "Invalid JSON"



def request_json(url, method="GET", data=None, headers=None, timeout=DEFAULT_TIMEOUT):
    req_headers = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            raw = response.read()
            if not raw:
                return status, None
            return status, json.loads(raw.decode("utf-8")), dict(response.headers)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            payload = {"error": str(e)}
        return e.code, payload, dict(getattr(e, "headers", {}) or {})
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        return 502, {"error": f"Upstream service unavailable: {e}"}, {}
    except Exception as e:
        return 500, {"error": f"Unexpected server error: {e}"}, {}



def config_value(name, default=None):
    value = CONFIG.get(name, default)
    if isinstance(value, str):
        return value.strip()
    return value


# ---------- TASK SERVICE ----------
def task_service_url(path=""):
    base = config_value("task_service_url", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}{path}"


def get_tasks(done_filter=None):
    url = task_service_url("/tasks")
    if done_filter is not None:
        url += f"?done={'true' if done_filter else 'false'}"
    return request_json(url)


def create_task(task_data):
    return request_json(task_service_url("/tasks"), method="POST", data=task_data)


def update_task(task_id, task_data):
    return request_json(task_service_url(f"/tasks/{task_id}"), method="PUT", data=task_data)


def delete_task(task_id):
    return request_json(task_service_url(f"/tasks/{task_id}"), method="DELETE")


# ---------- WEATHER SERVICE ----------
def get_weather(city):
    api_key = config_value("openweather_api_key", "")
    if not api_key or api_key == "PUT_YOUR_OPENWEATHER_KEY_HERE":
        return 503, {"error": "OpenWeather API key missing in config.json"}, {}

    base_url = config_value("openweather_base_url", "https://api.openweathermap.org/data/2.5/weather")
    url = f"{base_url}?q={quote(city)}&appid={api_key}&units=metric"
    status, data, headers = request_json(url)

    if status != 200 or not isinstance(data, dict):
        return status, data, headers

    transformed = {
        "city": data.get("name"),
        "country": data.get("sys", {}).get("country"),
        "temperature": data.get("main", {}).get("temp"),
        "feelsLike": data.get("main", {}).get("feels_like"),
        "humidity": data.get("main", {}).get("humidity"),
        "description": ((data.get("weather") or [{}])[0]).get("description"),
        "windSpeed": data.get("wind", {}).get("speed")
    }
    return 200, transformed, headers


# ---------- FACTS SERVICE ----------
def get_fact():
    api_key = config_value("api_ninjas_api_key", "")
    if not api_key or api_key == "PUT_YOUR_API_NINJAS_KEY_HERE":
        return 503, {"error": "API Ninjas key missing in config.json"}, {}

    url = config_value("api_ninjas_fact_url", "https://api.api-ninjas.com/v1/facts")
    headers = {"X-Api-Key": api_key}
    status, data, resp_headers = request_json(url, headers=headers)

    if status != 200:
        return status, data, resp_headers

    if isinstance(data, list) and data:
        return 200, {"fact": data[0].get("fact")}, resp_headers

    return 502, {"error": "Facts service returned an unexpected response"}, resp_headers


class AppServerHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_json(self, 204)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/health":
            send_json(self, 200, {"status": "ok"})
            return

        if path == "/api/tasks":
            done_param = qs.get("done", [None])[0]
            done_filter = None
            if done_param is not None:
                if done_param.lower() not in ("true", "false"):
                    send_json(self, 400, {"error": "done must be true or false"})
                    return
                done_filter = done_param.lower() == "true"

            status, data, _ = get_tasks(done_filter)
            send_json(self, status, data)
            return

        if path == "/api/weather":
            city = qs.get("city", [""])[0].strip()
            if not city:
                send_json(self, 400, {"error": "city query parameter is required"})
                return

            status, data, _ = get_weather(city)
            send_json(self, status, data)
            return

        if path == "/api/fact":
            status, data, _ = get_fact()
            send_json(self, status, data)
            return

        if path == "/api/dashboard":
            city = qs.get("city", [config_value("default_city", "Bucharest")])[0].strip() or config_value("default_city", "Bucharest")

            tasks_status, tasks_data, _ = get_tasks()
            weather_status, weather_data, _ = get_weather(city)
            fact_status, fact_data, _ = get_fact()

            response = {
                "tasks": tasks_data if tasks_status == 200 else [],
                "weather": weather_data if weather_status == 200 else None,
                "fact": fact_data if fact_status == 200 else None,
                "errors": {}
            }

            if tasks_status != 200:
                response["errors"]["tasks"] = tasks_data
            if weather_status != 200:
                response["errors"]["weather"] = weather_data
            if fact_status != 200:
                response["errors"]["fact"] = fact_data

            send_json(self, 200, response)
            return

        send_json(self, 404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path != "/api/tasks":
            send_json(self, 404, {"error": "Not Found"})
            return

        data, err = read_json_body(self)
        if err:
            send_json(self, 400, {"error": err})
            return

        status, payload, headers = create_task(data)
        extra = {}
        location = headers.get("Location")
        if location:
            extra["Location"] = location
        send_json(self, status, payload, extra_headers=extra)

    def do_PUT(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if len(parts) != 3 or parts[0] != "api" or parts[1] != "tasks":
            send_json(self, 404, {"error": "Not Found"})
            return

        try:
            task_id = int(parts[2])
        except ValueError:
            send_json(self, 400, {"error": "Invalid task id"})
            return

        data, err = read_json_body(self)
        if err:
            send_json(self, 400, {"error": err})
            return

        status, payload, _ = update_task(task_id, data)
        if status == 204:
            send_json(self, 200, {"message": "Task updated"})
        else:
            send_json(self, status, payload)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if len(parts) != 3 or parts[0] != "api" or parts[1] != "tasks":
            send_json(self, 404, {"error": "Not Found"})
            return

        try:
            task_id = int(parts[2])
        except ValueError:
            send_json(self, 400, {"error": "Invalid task id"})
            return

        status, payload, _ = delete_task(task_id)
        if status == 204:
            send_json(self, 200, {"message": "Task deleted"})
        else:
            send_json(self, status, payload)

    def log_message(self, format, *args):
        return


def main():
    server = HTTPServer((HOST, PORT), AppServerHandler)
    print(f"App backend running on http://{HOST}:{PORT}")
    print("Endpoints: /api/tasks, /api/weather?city=..., /api/fact, /api/dashboard?city=...")
    server.serve_forever()


if __name__ == "__main__":
    main()
