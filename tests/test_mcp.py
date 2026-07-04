from __future__ import annotations

import json

import pytest

import wiznote_cli as cli
from wiznote_helper import LoginResult


class FakeApi:
    def __init__(self):
        self.calls = []
        self.login_result = LoginResult(token="tok", kb_server="http://kb", kb_guid="kb-1")

    def login(self, credentials):
        self.calls.append(("login", credentials))
        return self.login_result

    def create_category(self, **kwargs):
        self.calls.append(("create_category", kwargs))
        return {"returnCode": 200, "result": {"category": kwargs["category"]}}

    def fetch_note_list(self, **kwargs):
        self.calls.append(("fetch_note_list", kwargs))
        return {"returnCode": 200, "result": [{"docGuid": "doc-1", "title": "Spec"}]}

    def search_notes(self, **kwargs):
        self.calls.append(("search_notes", kwargs))
        return {"returnCode": 200, "result": [{"docGuid": "doc-2", "title": "Roadmap"}]}

    def fetch_note_info(self, **kwargs):
        self.calls.append(("fetch_note_info", kwargs))
        return {"returnCode": 200, "result": {"docGuid": kwargs["doc_guid"], "title": "Old", "category": "/team/docs/"}}

    def fetch_note_html(self, **kwargs):
        self.calls.append(("fetch_note_html", kwargs))
        return "<html><body><p>Old body</p></body></html>"

    def create_note(self, **kwargs):
        self.calls.append(("create_note", kwargs))
        return {"returnCode": 200, "result": {"docGuid": "created-doc"}}

    def save_note(self, **kwargs):
        self.calls.append(("save_note", kwargs))
        return {"returnCode": 200, "result": {"docGuid": kwargs["doc_guid"]}}


def make_tools(fake_api: FakeApi):
    from wiznote_mcp import WizNoteMcpTools

    return WizNoteMcpTools(
        credentials=cli.Credentials(base_url="http://wiz", user="user@example.com", password="secret"),
        api=fake_api,
    )


def test_tool_schemas_include_required_wiznote_tools():
    from wiznote_mcp import tool_schemas

    schemas = tool_schemas()
    names = {schema["name"] for schema in schemas}

    assert {
        "wiz_create_folder",
        "wiz_list_notes",
        "wiz_search_notes",
        "wiz_get_note",
        "wiz_create_note",
        "wiz_update_note",
    }.issubset(names)
    update_schema = next(schema for schema in schemas if schema["name"] == "wiz_update_note")
    assert update_schema["inputSchema"]["required"] == ["docGuid", "title", "category"]


def test_credentials_from_args_returns_none_when_no_connection_args():
    from wiznote_mcp import credentials_from_args

    assert credentials_from_args([]) is None


def test_credentials_from_args_builds_credentials_from_mcp_config_args():
    from wiznote_mcp import credentials_from_args

    credentials = credentials_from_args(
        ["--base-url", "http://wiz/", "--username", "user@example.com", "--password", "secret"]
    )

    assert credentials == cli.Credentials(base_url="http://wiz", user="user@example.com", password="secret")


def test_credentials_from_args_requires_complete_connection_args():
    from wiznote_mcp import credentials_from_args

    with pytest.raises(ValueError, match="base-url, username, and password"):
        credentials_from_args(["--base-url", "http://wiz", "--username", "user@example.com"])


def test_create_folder_logs_in_once_and_calls_category_api():
    fake_api = FakeApi()
    tools = make_tools(fake_api)

    result = tools.call_tool("wiz_create_folder", {"category": "/team/docs/new/"})
    tools.call_tool("wiz_list_notes", {"category": "/team/docs/new/"})

    assert result == {"returnCode": 200, "result": {"category": "/team/docs/new/"}}
    assert fake_api.calls[0][0] == "login"
    assert fake_api.calls[0][1].user == "user@example.com"
    assert fake_api.calls[1] == (
        "create_category",
        {
            "base_url": "http://kb",
            "kb_guid": "kb-1",
            "token": "tok",
            "category": "/team/docs/new/",
        },
    )
    assert [name for name, _ in fake_api.calls].count("login") == 1


def test_search_notes_uses_default_kb_and_paging():
    fake_api = FakeApi()
    tools = make_tools(fake_api)

    result = tools.call_tool("wiz_search_notes", {"query": "roadmap", "start": 5, "count": 10})

    assert result["result"] == [{"docGuid": "doc-2", "title": "Roadmap"}]
    assert fake_api.calls[-1] == (
        "search_notes",
        {
            "base_url": "http://kb",
            "kb_guid": "kb-1",
            "token": "tok",
            "query": "roadmap",
            "start": 5,
            "count": 10,
        },
    )


def test_get_note_returns_info_and_html_body():
    fake_api = FakeApi()
    tools = make_tools(fake_api)

    result = tools.call_tool("wiz_get_note", {"docGuid": "doc-1"})

    assert result == {
        "info": {"returnCode": 200, "result": {"docGuid": "doc-1", "title": "Old", "category": "/team/docs/"}},
        "html": "<p>Old body</p>",
    }


def test_create_note_converts_markdown_and_calls_create_api():
    fake_api = FakeApi()
    tools = make_tools(fake_api)

    result = tools.call_tool(
        "wiz_create_note",
        {"title": "New", "category": "/team/docs/", "markdown": "# Heading\n\nBody"},
    )

    assert result == {"returnCode": 200, "result": {"docGuid": "created-doc"}}
    assert fake_api.calls[-1] == (
        "create_note",
        {
            "base_url": "http://kb",
            "kb_guid": "kb-1",
            "token": "tok",
            "title": "New",
            "category": "/team/docs/",
            "html": "<h1>Heading</h1>\n<p>Body</p>",
        },
    )


def test_update_note_preserves_existing_title_and_category_when_omitted():
    fake_api = FakeApi()
    tools = make_tools(fake_api)

    result = tools.call_tool("wiz_update_note", {"docGuid": "doc-1", "html": "<p>Updated</p>"})

    assert result == {"returnCode": 200, "result": {"docGuid": "doc-1"}}
    assert fake_api.calls[-1] == (
        "save_note",
        {
            "base_url": "http://kb",
            "kb_guid": "kb-1",
            "doc_guid": "doc-1",
            "token": "tok",
            "title": "Old",
            "category": "/team/docs/",
            "html": "<p>Updated</p>",
        },
    )


def test_unknown_tool_raises_clear_error():
    tools = make_tools(FakeApi())

    with pytest.raises(ValueError, match="Unknown tool"):
        tools.call_tool("wiz_delete_note", {})


def test_handle_jsonrpc_initialize_returns_mcp_capabilities():
    from wiznote_mcp import handle_jsonrpc_message

    response = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        make_tools(FakeApi()),
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "wiznote-mcp", "version": "0.1.0"},
        },
    }


def test_handle_jsonrpc_initialized_notification_returns_none():
    from wiznote_mcp import handle_jsonrpc_message

    response = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        make_tools(FakeApi()),
    )

    assert response is None


def test_handle_jsonrpc_tools_list_returns_schemas():
    from wiznote_mcp import handle_jsonrpc_message

    response = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        make_tools(FakeApi()),
    )

    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 2
    assert "wiz_create_note" in tool_names
    assert "wiz_update_note" in tool_names


def test_handle_jsonrpc_tools_call_returns_json_text_content():
    from wiznote_mcp import handle_jsonrpc_message

    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "wiz_search_notes", "arguments": {"query": "roadmap"}},
        },
        make_tools(FakeApi()),
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 3
    assert response["result"]["isError"] is False
    content = response["result"]["content"]
    assert content[0]["type"] == "text"
    assert json.loads(content[0]["text"]) == {
        "returnCode": 200,
        "result": [{"docGuid": "doc-2", "title": "Roadmap"}],
    }


def test_handle_jsonrpc_tools_call_returns_error_content_for_tool_error():
    from wiznote_mcp import handle_jsonrpc_message

    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "wiz_delete_note", "arguments": {}},
        },
        make_tools(FakeApi()),
    )

    assert response["result"]["isError"] is True
    assert response["result"]["content"] == [{"type": "text", "text": "Unknown tool: wiz_delete_note"}]
