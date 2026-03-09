import os
import threading
import logging
from pathlib import Path
from typing import List, Optional

from flask import Flask, jsonify, send_from_directory

from .base import DisplayBackend

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"


class WebDisplay(DisplayBackend):
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        idle_message: str = "Scanning the skies...",
    ):
        self._host = host
        # Allow PORT env var override (for preview tooling)
        self._port = int(os.environ.get("PORT", port))
        self._idle_message = idle_message
        self._messages: List[str] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        self._app = Flask(__name__, static_folder=str(STATIC_DIR))
        self._setup_routes()

    def _setup_routes(self):
        @self._app.route("/")
        def index():
            return send_from_directory(str(STATIC_DIR), "marquee.html")

        @self._app.route("/api/flights")
        def flights():
            with self._lock:
                msgs = self._messages.copy()
            return jsonify({
                "flights": msgs,
                "idle_message": self._idle_message,
            })

        @self._app.route("/static/<path:filename>")
        def static_files(filename):
            return send_from_directory(str(STATIC_DIR), filename)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=lambda: self._app.run(
                host=self._host,
                port=self._port,
                debug=False,
                use_reloader=False,
            ),
            daemon=True,
        )
        self._thread.start()
        logger.info("Web marquee running at http://%s:%d", self._host, self._port)

    def update(self, messages: List[str]) -> None:
        with self._lock:
            self._messages = messages.copy()

    def stop(self) -> None:
        pass  # Flask doesn't have a clean shutdown from a thread; daemon=True handles it
