#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def call_generate(host: str, model: str, prompt: str, timeout: float = 30.0) -> str:
    url = host.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        print(f"[generate] Request failed: {e}", file=sys.stderr)
        raise

    print(f"[generate] HTTP {resp.status} from {url}")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"[generate] Invalid JSON: {e}", file=sys.stderr)
        print(body)
        raise

    # Standard Ollama /api/generate responses have a 'response' field
    resp_text = parsed.get("response")
    if not isinstance(resp_text, str):
        print("[generate] Missing 'response' field:", parsed, file=sys.stderr)
        raise RuntimeError("Missing 'response' in /api/generate response")
    return resp_text.strip()


def call_chat(host: str, model: str, system_prompt: str, user_prompt: str, timeout: float = 30.0) -> str:
    url = host.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        print(f"[chat] Request failed: {e}", file=sys.stderr)
        raise

    print(f"[chat] HTTP {resp.status} from {url}")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"[chat] Invalid JSON: {e}", file=sys.stderr)
        print(body)
        raise

    # Standard /api/chat responses have a 'message': {'content': ...}
    message = parsed.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        print("[chat] Missing 'message.content' field:", parsed, file=sys.stderr)
        raise RuntimeError("Missing 'message.content' in /api/chat response")
    return content.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick Ollama test client.")
    parser.add_argument("prompt", help="User prompt text")
    parser.add_argument(
        "--model",
        default=os.getenv("OLLAMA_MODEL", "gpt-oss"),
        help="Ollama model name (default: gpt-oss or $OLLAMA_MODEL)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama host URL (default: http://localhost:11434 or $OLLAMA_HOST)",
    )
    args = parser.parse_args()

    system_prompt = "You are a helpful assistant."

    print(f"Using host={args.host}, model={args.model}\n")

    print("=== /api/generate ===")
    gen_text = call_generate(args.host, args.model, args.prompt)
    print(gen_text, "\n")

    print("=== /api/chat ===")
    chat_text = call_chat(args.host, args.model, system_prompt, args.prompt)
    print(chat_text)


if __name__ == "__main__":
    main()

