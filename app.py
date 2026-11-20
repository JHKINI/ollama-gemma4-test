"""Flask proxy server for the Ollama streaming chat UI."""

from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
if not WEB_DIR.is_dir():
    WEB_DIR = BASE_DIR / "ollama-gemma4-test" / "web"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"

app = Flask(__name__)


@app.get("/")
def index():
    """Serve the existing chat page."""
    return send_from_directory(WEB_DIR, "index3.html")


@app.post("/api/chat")
def chat():
    """Forward the browser's chat request to Ollama and stream NDJSON back."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "요청 본문은 JSON 객체여야 합니다."}), 400

    model = data.get("model", "gemma4:e2b")
    messages = data.get("messages")

    if not isinstance(model, str) or not model.strip():
        return jsonify({"error": "model 값이 올바르지 않습니다."}), 400
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "messages는 비어 있지 않은 배열이어야 합니다."}), 400

    # Keep Ollama's streaming response enabled. Forward other supported options
    # (for example, options or format) if the client supplies them.
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    for key in ("format", "options", "tools", "keep_alive"):
        if key in data:
            payload[key] = data[key]

    try:
        ollama_response = requests.post(
            OLLAMA_CHAT_URL,
            json=payload,
            stream=True,
            timeout=(5, 600),
        )
    except requests.RequestException as exc:
        return jsonify({
            "error": "Ollama 서버에 연결할 수 없습니다.",
            "detail": str(exc),
            "hint": "Ollama Docker 컨테이너가 실행 중인지 확인하세요.",
        }), 502

    if not ollama_response.ok:
        status_code = ollama_response.status_code
        try:
            error_body = ollama_response.json()
        except ValueError:
            error_body = {"error": ollama_response.text}
        ollama_response.close()
        return jsonify(error_body), status_code

    @stream_with_context
    def generate():
        try:
            # iter_lines yields complete NDJSON lines from Ollama.
            for line in ollama_response.iter_lines(decode_unicode=True):
                if line:
                    yield line + "\n"
        finally:
            ollama_response.close()

    return Response(
        generate(),
        content_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    # Run from the project folder: python app.py
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
