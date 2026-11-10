"""Robot bridge: one HTTP client for the real robot (Talaria firmware) and the virtual robot
(``hermes talaria sim``), which speak the same API (from caduceus-body's BodyClient and sim server).

  GET /info   GET /state   POST /play {name, loops, easing, frames}   POST /pose {joints, ms}   POST /stop {home}

The virtual robot runs the plugin's own motion engine (same easing and speed rules as the simulator
and the firmware) on a local HTTP server, so the whole bridge path is testable without hardware.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

from .motion import MAX_FRAMES, MotionEngine, home_pose
from .spec import Spec

SIM_VERSION = "talaria-sim/0.1.0"
API_VERSION = 1
TOKEN_HEADER = "X-Robot-Token"
MAX_BODY_BYTES = 64 * 1024
TICK_SECONDS = 0.02
HOME_MS = 3000   # every return to home takes at least this long (a quick drop tips the foam robot over)


class RobotError(Exception):
    """A request the robot refused or answered with an error."""


class RobotUnreachable(RobotError):
    """No answer at all (robot off, wrong address, other network)."""


def normalize_url(url: str) -> str:
    """``192.168.1.8`` -> ``http://192.168.1.8``; only http(s), no credentials, no path."""
    url = (url or "").strip().rstrip("/")
    if not url:
        raise RobotError("no robot address set")
    if "://" not in url:
        url = "http://" + url
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RobotError(f"robot address must be http(s)://host[:port], got {url!r}")
    if parts.username or parts.password:
        raise RobotError("robot address must not contain a user name or password")
    return f"{parts.scheme}://{parts.netloc}"


class RobotClient:
    """JSON over HTTP. Requests skip any HTTP proxy: a robot lives on the local network."""

    def __init__(self, url: str, token: Optional[str] = None, timeout: float = 3.0):
        self.url = normalize_url(url)
        self.token = token or None
        self.timeout = max(0.2, float(timeout))
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method: str, path: str, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header(TOKEN_HEADER, self.token)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read(256 * 1024)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read(16 * 1024) or b"{}").get("error", "")
            except (ValueError, AttributeError):
                pass
            if exc.code == 401:
                raise RobotError("the robot refused the request: wrong or missing token (set "
                                 "TALARIA_ROBOT_TOKEN in the plugin settings)") from None
            raise RobotError(f"the robot answered {exc.code}{': ' + detail if detail else ''}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            raise RobotUnreachable(f"no answer from the robot at {self.url} ({reason})") from None
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            raise RobotError(f"{self.url} did not answer with JSON; is this a Talaria robot?") from None
        if not isinstance(payload, dict):
            raise RobotError("the robot answered with something other than a JSON object")
        if payload.get("ok") is False:
            raise RobotError(str(payload.get("error") or "the robot refused the request"))
        return payload

    def info(self) -> dict[str, Any]:
        info = self.request("GET", "/info")
        if not info.get("joints"):
            raise RobotError(f"{self.url} answered but reported no joints; is this a Talaria robot?")
        return info

    def state(self) -> dict[str, Any]:
        return self.request("GET", "/state")

    def play(self, frames: list[dict[str, Any]], *, loops: int = 1, easing: str = "smoothstep",
             name: Optional[str] = None) -> dict[str, Any]:
        return self.request("POST", "/play", {"name": name, "loops": loops, "easing": easing, "frames": frames})

    def pose(self, joints: dict[str, float], ms: int = 400) -> dict[str, Any]:
        return self.request("POST", "/pose", {"joints": joints, "ms": ms})

    def stop(self, home: bool = False) -> dict[str, Any]:
        return self.request("POST", "/stop", {"home": bool(home)})


# ─── Virtual robot ───────────────────────────────────────────────────────────────────────────────


class VirtualRobot:
    """The motion engine and joint table of one spec, behind the firmware API."""

    def __init__(self, spec: Spec):
        self.spec = spec
        self.joints = spec.joint_limits()
        self.engine = MotionEngine(self.joints)
        self.lock = threading.Lock()
        self.name: Optional[str] = None
        self.loops = 1
        self.stop_reason: Optional[str] = None
        self.started = time.monotonic()
        self.t0 = time.monotonic()

    def now(self) -> float:
        return time.monotonic() - self.t0

    def info(self) -> dict[str, Any]:
        return {"ok": True, "name": self.spec.name, "firmware": SIM_VERSION, "api": API_VERSION,
                "spec_hash": self.spec.hash()[:16], "simulated": True, "max_frames": MAX_FRAMES,
                "joints": [{"name": n, "min": j["min"], "max": j["max"], "home": j["home"],
                            "max_speed": j["max_speed"]} for n, j in self.joints.items()]}

    def state(self) -> dict[str, Any]:
        with self.lock:
            self.engine.tick(self.now())
            busy = self.engine.busy
            return {"ok": True, "pose": {n: round(a, 2) for n, a in self.engine.pose.items()}, "busy": busy,
                    "move": self.name if busy else None, "stop_reason": self.stop_reason,
                    "uptime_ms": int((time.monotonic() - self.started) * 1000)}

    def play(self, frames: list[dict[str, Any]], loops: int, easing: str, name: Optional[str]) -> None:
        with self.lock:
            self.engine.load(frames[:MAX_FRAMES], loops=loops, now=self.now(),
                             easing="linear" if easing == "linear" else "smoothstep")
            self.name, self.stop_reason = name or "move", None

    def stop(self, home: bool) -> None:
        with self.lock:
            if self.engine.busy:
                self.stop_reason = "stopped"
            self.engine.load([], now=self.now())
            if home:
                self.engine.load([{"ms": HOME_MS, "joints": home_pose(self.joints)}], now=self.now())
                self.name = "home"

    def tick(self) -> None:
        with self.lock:
            self.engine.tick(self.now())


class _Handler(BaseHTTPRequestHandler):
    server: "VirtualServer"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        token = self.server.token
        if not token:
            return True
        return hmac.compare_digest(self.headers.get(TOKEN_HEADER, "").encode(), token.encode())

    def _json_body(self) -> Optional[dict[str, Any]]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return self._send(401, {"ok": False, "error": "unauthorized"})
        robot = self.server.robot
        if self.path == "/info":
            return self._send(200, robot.info())
        if self.path == "/state":
            return self._send(200, robot.state())
        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return self._send(401, {"ok": False, "error": "unauthorized"})
        data = self._json_body()
        if data is None:
            return self._send(400, {"ok": False, "error": "body must be a JSON object under 64 KB"})
        robot = self.server.robot
        if self.path == "/play":
            frames = data.get("frames")
            if not isinstance(frames, list) or not frames:
                return self._send(400, {"ok": False, "error": "frames must be a non-empty list"})
            if len(frames) > MAX_FRAMES:
                return self._send(400, {"ok": False, "error": f"at most {MAX_FRAMES} frames"})
            loops = int(data.get("loops") or 1)
            easing = data.get("easing") or "smoothstep"
            robot.play([f for f in frames if isinstance(f, dict)], loops, easing, data.get("name"))
            self.server.report(f"play {data.get('name') or 'move'}: {len(frames)} frame(s) x{loops} ({easing})")
            return self._send(200, {"ok": True, "frames": len(frames), "loops": loops, "easing": easing})
        if self.path == "/pose":
            joints = data.get("joints")
            if not isinstance(joints, dict) or not joints:
                return self._send(400, {"ok": False, "error": "joints must be a non-empty object"})
            robot.play([{"ms": int(data.get("ms") or 400), "joints": joints}], 1, "smoothstep", "pose")
            self.server.report("pose " + ", ".join(f"{k}={v}" for k, v in joints.items()))
            return self._send(200, {"ok": True})
        if self.path == "/stop":
            robot.stop(bool(data.get("home")))
            self.server.report("stop" + (" and go home" if data.get("home") else ""))
            return self._send(200, {"ok": True})
        return self._send(404, {"ok": False, "error": "not found"})


class VirtualServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], robot: VirtualRobot, token: Optional[str] = None,
                 reporter: Optional[Callable[[str], None]] = None):
        super().__init__(address, _Handler)
        self.robot = robot
        self.token = token or None
        self._reporter = reporter
        self._stop = threading.Event()
        threading.Thread(target=self._tick_loop, name="talaria-sim-tick", daemon=True).start()

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def report(self, message: str) -> None:
        if self._reporter:
            self._reporter(message)

    def _tick_loop(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            self.robot.tick()

    def server_close(self) -> None:
        self._stop.set()
        super().server_close()


def start_virtual(spec: Spec, host: str = "127.0.0.1", port: int = 0, token: Optional[str] = None) -> VirtualServer:
    """A virtual robot on a background thread (``port=0`` picks a free port)."""
    server = VirtualServer((host, port), VirtualRobot(spec), token=token)
    threading.Thread(target=server.serve_forever, name=f"talaria-sim-{spec.name}", daemon=True).start()
    return server


def serve(spec: Spec, host: str = "127.0.0.1", port: int = 8765, token: Optional[str] = None,
          out: Callable[[str], None] = print) -> int:
    """Run a virtual robot in the foreground until Ctrl-C."""
    try:
        server = VirtualServer((host, port), VirtualRobot(spec), token=token,
                               reporter=lambda msg: out(time.strftime("%H:%M:%S ") + msg))
    except OSError as exc:
        out(f"Could not listen on {host}:{port}: {exc}")
        return 1
    out(f"Virtual {spec.title or spec.name} listening on {server.url} (simulation of the firmware API)")
    out(f"Point the plugin at it: robot_url = {server.url}   (or use target 'virtual' in robot_play)")
    out("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        out("Stopping the virtual robot.")
    finally:
        server.server_close()
    return 0
