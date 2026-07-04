from __future__ import annotations

import html
import json
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import Any

import wiznote_cli as cli
from wiznote_helper import LoginResult, extract_html_body


def markdown_to_html(text: str) -> str:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    rendered: list[str] = []
    for block in blocks:
        if block.startswith("# "):
            rendered.append(f"<h1>{html.escape(block[2:].strip())}</h1>")
        elif block.startswith("## "):
            rendered.append(f"<h2>{html.escape(block[3:].strip())}</h2>")
        else:
            lines = [html.escape(line.strip()) for line in block.splitlines()]
            rendered.append(f"<p>{'<br />'.join(lines)}</p>")
    return "\n".join(rendered)


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "wiz_create_folder",
            "description": "Create a WizNote category/folder path.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kbGuid": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["category"],
            },
        },
        {
            "name": "wiz_list_notes",
            "description": "List notes in a WizNote category/folder.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kbGuid": {"type": "string"},
                    "category": {"type": "string"},
                    "start": {"type": "integer"},
                    "count": {"type": "integer"},
                },
                "required": ["category"],
            },
        },
        {
            "name": "wiz_search_notes",
            "description": "Search notes in a WizNote knowledge base.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kbGuid": {"type": "string"},
                    "query": {"type": "string"},
                    "start": {"type": "integer"},
                    "count": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "wiz_get_note",
            "description": "Read note metadata and HTML body.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kbGuid": {"type": "string"},
                    "docGuid": {"type": "string"},
                },
                "required": ["docGuid"],
            },
        },
        {
            "name": "wiz_create_note",
            "description": "Create a note from HTML or Markdown.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kbGuid": {"type": "string"},
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "html": {"type": "string"},
                    "markdown": {"type": "string"},
                },
                "required": ["title", "category"],
            },
        },
        {
            "name": "wiz_update_note",
            "description": "Update an existing note from HTML or Markdown.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kbGuid": {"type": "string"},
                    "docGuid": {"type": "string"},
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "html": {"type": "string"},
                    "markdown": {"type": "string"},
                },
                "required": ["docGuid", "title", "category"],
            },
        },
    ]


def credentials_from_args(argv: list[str]) -> cli.Credentials | None:
    parser = ArgumentParser(prog="wiznote-mcp", add_help=True)
    parser.add_argument("--base-url")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parsed = parser.parse_args(argv)
    values = [parsed.base_url, parsed.username, parsed.password]
    if not any(values):
        return None
    if not all(values):
        raise ValueError("base-url, username, and password must be provided together")
    return cli.load_credentials(base_url=parsed.base_url, user=parsed.username, password=parsed.password)


@dataclass
class WizNoteMcpTools:
    credentials: cli.Credentials | None = None
    api: Any = cli

    def __post_init__(self) -> None:
        self._login: LoginResult | None = None

    def _session(self) -> LoginResult:
        if self._login is None:
            credentials = self.credentials if self.credentials is not None else self.api.load_credentials()
            self._login = self.api.login(credentials)
        return self._login

    def _kb_guid(self, arguments: dict[str, Any], session: LoginResult) -> str:
        kb_guid = arguments.get("kbGuid") or session.kb_guid
        if not isinstance(kb_guid, str) or not kb_guid:
            raise ValueError("kbGuid must be a non-empty string")
        return kb_guid

    def _required_string(self, arguments: dict[str, Any], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} must be a non-empty string")
        return value

    def _body_html(self, arguments: dict[str, Any]) -> str:
        html_body = arguments.get("html")
        markdown = arguments.get("markdown")
        if isinstance(html_body, str) and html_body:
            return html_body
        if isinstance(markdown, str) and markdown:
            return markdown_to_html(markdown)
        raise ValueError("Either html or markdown must be provided")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        session = self._session()
        kb_guid = self._kb_guid(arguments, session)
        if name == "wiz_create_folder":
            return self.api.create_category(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                token=session.token,
                category=self._required_string(arguments, "category"),
            )
        if name == "wiz_list_notes":
            return self.api.fetch_note_list(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                token=session.token,
                category=self._required_string(arguments, "category"),
                start=int(arguments.get("start", 0)),
                count=int(arguments.get("count", 100)),
            )
        if name == "wiz_search_notes":
            return self.api.search_notes(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                token=session.token,
                query=self._required_string(arguments, "query"),
                start=int(arguments.get("start", 0)),
                count=int(arguments.get("count", 20)),
            )
        if name == "wiz_get_note":
            doc_guid = self._required_string(arguments, "docGuid")
            info = self.api.fetch_note_info(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                doc_guid=doc_guid,
                token=session.token,
            )
            note_html = self.api.fetch_note_html(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                doc_guid=doc_guid,
                token=session.token,
            )
            return {"info": info, "html": extract_html_body(note_html)}
        if name == "wiz_create_note":
            return self.api.create_note(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                token=session.token,
                title=self._required_string(arguments, "title"),
                category=self._required_string(arguments, "category"),
                html=self._body_html(arguments),
            )
        if name == "wiz_update_note":
            doc_guid = self._required_string(arguments, "docGuid")
            info = self.api.fetch_note_info(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                doc_guid=doc_guid,
                token=session.token,
            )
            note = info.get("result") if isinstance(info, dict) else {}
            if not isinstance(note, dict):
                note = {}
            title = arguments.get("title") or note.get("title") or note.get("DOCUMENT_TITLE")
            category = arguments.get("category") or note.get("category") or note.get("DOCUMENT_CATEGORY")
            if not isinstance(title, str) or not title:
                raise ValueError("title must be provided when existing note info has no title")
            if not isinstance(category, str) or not category:
                raise ValueError("category must be provided when existing note info has no category")
            return self.api.save_note(
                base_url=session.kb_server,
                kb_guid=kb_guid,
                doc_guid=doc_guid,
                token=session.token,
                title=title,
                category=category,
                html=self._body_html(arguments),
            )
        raise ValueError(f"Unknown tool: {name}")


def _jsonrpc_response(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _jsonrpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _tool_content(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle_jsonrpc_message(message: dict[str, Any], tools: WizNoteMcpTools) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _jsonrpc_response(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "wiznote-mcp", "version": "0.1.0"},
            },
        )
    if method == "tools/list":
        return _jsonrpc_response(message_id, {"tools": tool_schemas()})
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict):
            return _jsonrpc_error(message_id, -32602, "tools/call params must be an object")
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            return _jsonrpc_error(message_id, -32602, "tools/call params.name must be a string")
        if not isinstance(arguments, dict):
            return _jsonrpc_error(message_id, -32602, "tools/call params.arguments must be an object")
        try:
            return _jsonrpc_response(message_id, _tool_content(tools.call_tool(name, arguments)))
        except Exception as exc:
            return _jsonrpc_response(message_id, _tool_content(str(exc), is_error=True))
    return _jsonrpc_error(message_id, -32601, f"Method not found: {method}")


def main(argv: list[str] | None = None) -> int:
    credentials = credentials_from_args(sys.argv[1:] if argv is None else argv)
    tools = WizNoteMcpTools(credentials=credentials)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                response = _jsonrpc_error(None, -32600, "JSON-RPC message must be an object")
            else:
                response = handle_jsonrpc_message(message, tools)
        except json.JSONDecodeError as exc:
            response = _jsonrpc_error(None, -32700, f"Parse error: {exc}")
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
