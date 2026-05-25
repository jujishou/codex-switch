#!/usr/bin/env python3
# This file is derived from LearnPrompt/stepfun-codex-adapter
# (https://github.com/LearnPrompt/stepfun-codex-adapter), released under the
# MIT License. The original code was extracted from the project's installer
# script (the PYADAPTER heredoc) and is redistributed here under the same MIT
# License. See NOTICE in the project root for attribution.
import json
import os
import sqlite3
import socket
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 18667
CONFIG_PATH = Path.home() / ".cc-switch" / "stepfun-codex-adapter-config.json"
DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"


def load_saved_api_key():
    if not DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                """
                select json_extract(settings_config, '$.auth.OPENAI_API_KEY')
                from providers
                where app_type = 'codex' and id = 'stepfun-codex-adapter'
                limit 1
                """
            ).fetchone()
        return row[0] if row and row[0] else None
    except sqlite3.Error:
        return None


def load_config():
    if not CONFIG_PATH.exists():
        return {
            "upstream": "https://api.stepfun.com/v1/chat/completions",
            "model": "step-3.5-flash-2603",
            "subscription": "normal",
        }
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "upstream": data.get("upstream") or "https://api.stepfun.com/v1/chat/completions",
        "model": data.get("model") or "step-3.5-flash-2603",
        "subscription": data.get("subscription") or "normal",
        "api_key": data.get("api_key") or os.environ.get("STEPFUN_API_KEY") or load_saved_api_key(),
    }


def extract_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [extract_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        value_type = value.get("type")
        if value_type in ("input_text", "output_text", "text"):
            return extract_text(value.get("text"))
        if value_type == "image_url":
            return "[image_url omitted by stepfun-codex-adapter]"
        if value_type in ("input_audio", "video_url"):
            return f"[{value_type} omitted by stepfun-codex-adapter]"
        for key in ("text", "content", "output", "result"):
            if key in value:
                text = extract_text(value[key])
                if text:
                    return text
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def normalize_role(role):
    if role in ("developer", "system"):
        return "system"
    if role in ("assistant", "tool"):
        return role
    return "user"


def responses_to_messages(body):
    messages = []
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": extract_text(instructions)})

    inp = body.get("input", "")
    if isinstance(inp, str):
        if inp.strip():
            messages.append({"role": "user", "content": inp})
        return messages or [{"role": "user", "content": ""}]

    if isinstance(inp, list):
        for item in inp:
            if not isinstance(item, dict):
                text = extract_text(item)
                if text:
                    messages.append({"role": "user", "content": text})
                continue

            typ = item.get("type")
            if typ == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id") or item.get("id") or "call_unknown",
                    "content": extract_text(item.get("output")),
                })
                continue

            if typ == "function_call":
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": item.get("call_id") or item.get("id") or "call_unknown",
                        "type": "function",
                        "function": {
                            "name": item.get("name") or "unknown",
                            "arguments": item.get("arguments") or "{}",
                        },
                    }],
                })
                continue

            role = normalize_role(item.get("role") or ("assistant" if typ == "message" else "user"))
            text = extract_text(item.get("content"))
            if not text and typ:
                text = extract_text(item)
            if text:
                messages.append({"role": role, "content": text})

    return messages or [{"role": "user", "content": ""}]


def responses_tools_to_chat_tools(tools):
    chat_tools = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") != "function":
            continue
        function = tool.get("function") or {}
        name = tool.get("name") or function.get("name")
        if not name:
            continue
        chat_tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description") or function.get("description") or "",
                "parameters": tool.get("parameters") or function.get("parameters") or {
                    "type": "object",
                    "properties": {},
                },
            },
        })
    return chat_tools


def sse(handler, event, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    try:
        handler.wfile.write(f"event: {event}\n".encode("utf-8"))
        handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        handler.wfile.flush()
        return True
    except (BrokenPipeError, ConnectionResetError, socket.timeout):
        return False


def response_shell(response_id, model, status, output=None, usage=None):
    body = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "model": model,
        "output": output or [],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
    }
    if usage:
        body["usage"] = usage
    return body


def output_from_chat_message(message):
    output = []
    text = message.get("content") or ""
    audio = message.get("audio") or {}
    if not text and isinstance(audio, dict):
        text = audio.get("transcript") or ""
    if text:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        })
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        output.append({
            "id": "fc_" + uuid.uuid4().hex,
            "type": "function_call",
            "status": "completed",
            "call_id": call.get("id") or "call_" + uuid.uuid4().hex,
            "name": fn.get("name") or "unknown",
            "arguments": fn.get("arguments") or "{}",
        })
    return output


def mapped_usage(usage):
    if not usage:
        return None
    return {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "stepfun-codex-adapter/0.1"

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} {fmt % args}", flush=True)

    def send_json(self, status, payload):
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        config = load_config()
        if path in ("/health", "/v1/health"):
            self.send_json(200, {"ok": True, "model": config["model"], "subscription": config["subscription"]})
            return
        if path in ("/models", "/v1/models"):
            self.send_json(200, {
                "object": "list",
                "data": [{
                    "id": config["model"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "stepfun",
                }],
            })
            return
        self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not (path.startswith("/v1/responses") or path.startswith("/responses")):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8") or "{}")
            auth = self.headers.get("authorization") or self.headers.get("Authorization")

            config = load_config()
            if not auth and not config.get("api_key"):
                self.send_error(401, "Missing StepFun API key")
                return
            messages = responses_to_messages(body)
            max_tokens = body.get("max_output_tokens") or body.get("max_tokens") or 4096
            upstream_body = {
                "model": config["model"],
                "messages": messages,
                "stream": False,
                "max_tokens": max_tokens,
            }
            chat_tools = responses_tools_to_chat_tools(body.get("tools"))
            if chat_tools:
                upstream_body["tools"] = chat_tools
                tool_choice = body.get("tool_choice")
                if tool_choice and tool_choice != "auto":
                    upstream_body["tool_choice"] = tool_choice
            for key in ("temperature", "top_p"):
                if key in body:
                    upstream_body[key] = body[key]

            if body.get("stream", True) is not False:
                self.handle_stream(auth, config, upstream_body)
            else:
                self.handle_non_stream(auth, config, upstream_body)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return
        except Exception as exc:
            traceback.print_exc()
            self.send_json(500, {"error": str(exc)})

    def upstream_request(self, auth, config, upstream_body):
        upstream_auth = f"Bearer {config['api_key']}" if config.get("api_key") else auth
        req = urllib.request.Request(
            config["upstream"],
            data=json.dumps(upstream_body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": upstream_auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        return urllib.request.urlopen(req, timeout=600)

    def fetch_upstream(self, auth, config, upstream_body):
        with self.upstream_request(auth, config, upstream_body) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def handle_non_stream(self, auth, config, upstream_body):
        try:
            data = self.fetch_upstream(auth, config, upstream_body)
        except urllib.error.HTTPError as err:
            payload = err.read().decode("utf-8", "replace")
            self.send_json(err.code, {"error": payload})
            return
        except urllib.error.URLError as err:
            self.send_json(502, {"error": str(err)})
            return

        message = (data.get("choices") or [{}])[0].get("message") or {}
        output = output_from_chat_message(message)
        result = response_shell(
            "resp_" + uuid.uuid4().hex,
            config["model"],
            "completed",
            output=output,
            usage=mapped_usage(data.get("usage")),
        )
        self.send_json(200, result)

    def handle_stream(self, auth, config, upstream_body):
        response_id = "resp_" + uuid.uuid4().hex
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "close")
        self.end_headers()

        if not sse(self, "response.created", {
            "type": "response.created",
            "response": response_shell(response_id, config["model"], "in_progress"),
        }):
            return

        try:
            data = self.fetch_upstream(auth, config, upstream_body)
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")
            print(f"upstream HTTP {err.code}: {detail}", flush=True)
            data = {"choices": [{"message": {"content": f"StepFun upstream HTTP {err.code}: {detail[:1200]}"}}]}
        except urllib.error.URLError as err:
            detail = str(err)
            print(f"upstream URL error: {detail}", flush=True)
            data = {"choices": [{"message": {"content": f"StepFun upstream connection failed: {detail[:1200]}"}}]}

        message = (data.get("choices") or [{}])[0].get("message") or {}
        output = output_from_chat_message(message)

        for index, item in enumerate(output):
            added_item = dict(item)
            if added_item.get("type") == "message":
                added_item["status"] = "in_progress"
                added_item["content"] = []
            if not sse(self, "response.output_item.added", {
                "type": "response.output_item.added",
                "response_id": response_id,
                "output_index": index,
                "item": added_item,
            }):
                return
            if item.get("type") == "message":
                part = item["content"][0]
                if not sse(self, "response.content_part.added", {
                    "type": "response.content_part.added",
                    "response_id": response_id,
                    "item_id": item["id"],
                    "output_index": index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                }):
                    return
                if not sse(self, "response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "response_id": response_id,
                    "item_id": item["id"],
                    "output_index": index,
                    "content_index": 0,
                    "delta": part.get("text", ""),
                }):
                    return
                if not sse(self, "response.output_text.done", {
                    "type": "response.output_text.done",
                    "response_id": response_id,
                    "item_id": item["id"],
                    "output_index": index,
                    "content_index": 0,
                    "text": part.get("text", ""),
                }):
                    return
                if not sse(self, "response.content_part.done", {
                    "type": "response.content_part.done",
                    "response_id": response_id,
                    "item_id": item["id"],
                    "output_index": index,
                    "content_index": 0,
                    "part": part,
                }):
                    return
            if item.get("type") == "function_call":
                if not sse(self, "response.function_call_arguments.done", {
                    "type": "response.function_call_arguments.done",
                    "response_id": response_id,
                    "item_id": item["id"],
                    "output_index": index,
                    "arguments": item.get("arguments", "{}"),
                }):
                    return
            if not sse(self, "response.output_item.done", {
                "type": "response.output_item.done",
                "response_id": response_id,
                "output_index": index,
                "item": item,
            }):
                return

        sse(self, "response.completed", {
            "type": "response.completed",
            "response": response_shell(
                response_id,
                config["model"],
                "completed",
                output=output,
                usage=mapped_usage(data.get("usage")),
            ),
        })
        self.close_connection = True


def main():
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"stepfun codex adapter listening on http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
