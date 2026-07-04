from __future__ import annotations

import os
import time
import uuid

import pytest

import wiznote_cli as cli


def _require_live_credentials():
    if os.getenv("WIZNOTE_LIVE_TESTS") != "1":
        pytest.skip("Set WIZNOTE_LIVE_TESTS=1 to run live WizNote MCP integration tests")
    return cli.load_credentials()


def _doc_guid(payload: dict) -> str:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AssertionError(f"Expected result object with docGuid, got: {payload}")
    doc_guid = result.get("docGuid") or result.get("DOCUMENT_GUID")
    if not isinstance(doc_guid, str) or not doc_guid:
        raise AssertionError(f"Expected docGuid in result, got: {payload}")
    return doc_guid


def test_live_mcp_note_lifecycle_creates_folder_reads_updates_and_searches():
    credentials = _require_live_credentials()
    login = cli.login(credentials)
    suffix = uuid.uuid4().hex[:10]
    category_root = os.getenv("WIZNOTE_LIVE_TEST_CATEGORY_ROOT", "/team/mcp-live-tests/")
    category_root = category_root if category_root.endswith("/") else f"{category_root}/"
    category = f"{category_root}mcp-live-{suffix}/"
    title = f"MCP live test {suffix}"
    updated_title = f"MCP live test updated {suffix}"
    unique_text = f"wiznote-mcp-search-{suffix}"

    create_folder = cli.create_category(
        base_url=login.kb_server,
        kb_guid=login.kb_guid,
        token=login.token,
        category=category,
    )
    assert create_folder.get("returnCode") == 200

    created = cli.create_note(
        base_url=login.kb_server,
        kb_guid=login.kb_guid,
        token=login.token,
        title=title,
        category=category,
        html=f"<h1>{title}</h1><p>{unique_text}</p>",
    )
    assert created.get("returnCode") == 200
    doc_guid = _doc_guid(created)

    listed = cli.fetch_note_list(
        base_url=login.kb_server,
        kb_guid=login.kb_guid,
        token=login.token,
        category=category,
        count=20,
    )
    assert listed.get("returnCode") in {None, 200}
    assert title in str(listed)

    info = cli.fetch_note_info(
        base_url=login.kb_server,
        kb_guid=login.kb_guid,
        doc_guid=doc_guid,
        token=login.token,
    )
    assert info.get("returnCode") == 200

    html = cli.fetch_note_html(
        base_url=login.kb_server,
        kb_guid=login.kb_guid,
        doc_guid=doc_guid,
        token=login.token,
    )
    assert unique_text in html

    updated = cli.save_note(
        base_url=login.kb_server,
        kb_guid=login.kb_guid,
        doc_guid=doc_guid,
        token=login.token,
        title=updated_title,
        category=category,
        html=f"<h1>{updated_title}</h1><p>{unique_text} updated</p>",
    )
    assert updated.get("returnCode") == 200
    assert "updated" in cli.fetch_note_html(
        base_url=login.kb_server,
        kb_guid=login.kb_guid,
        doc_guid=doc_guid,
        token=login.token,
    )

    for _ in range(3):
        searched = cli.search_notes(
            base_url=login.kb_server,
            kb_guid=login.kb_guid,
            token=login.token,
            query=unique_text,
            count=20,
        )
        if doc_guid in str(searched) or updated_title in str(searched):
            break
        time.sleep(2)
    else:
        raise AssertionError("Created note did not appear in search results")
