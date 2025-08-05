import pytest
import pytest_asyncio
import httpx
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Clase.MinimalAlfrescoServer import MinimalAlfrescoServer
from unittest.mock import MagicMock, AsyncMock, patch

@pytest_asyncio.fixture
async def server():
    srv = MinimalAlfrescoServer("http://localhost:8080", "admin", "admin")
    srv.client = AsyncMock()
    return srv

@pytest.mark.asyncio
async def test_list_root_children(server):

    # Mock response
    mock_response = {
        "list": {
            "entries": [{
                "entry": {
                    "id": "123",
                    "name": "TestFolder",
                    "isFolder": True,
                    "nodeType": "cm:folder",
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "modifiedAt": "2024-01-02T00:00:00.000Z",
                    "createdByUser": {"displayName": "Admin"},
                    "modifiedByUser": {"displayName": "Admin"},
                    "path": {"name": "/Company Home/TestFolder"}
                }
            }]
        }
    }

    # Mock complet pentru răspunsul HTTP
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=mock_response)

    # Injectăm răspunsul mock
    server.client.get = AsyncMock(return_value=response)

    result = await server.list_root_children()
    assert result["total"] == 1
    assert result["items"][0]["name"] == "TestFolder"
    assert "message" in result

@pytest.mark.asyncio
async def test_get_node_children(server):

    mock_response={
        "list": {
            "entries": [{
                "entry": {
                    "id": "123",
                    "name": "Document.txt",
                    "isFolder": False,
                    "nodeType": "cm:folder",
                    "createdAt": "2024-01-01T12:00:00.000Z",
                    "modifiedAt": "2024-01-02T13:00:00.000Z",
                    "createdByUser": {"displayName": "UserA"},
                    "modifiedByUser": {"displayName": "UserB"},
                    "content": {
                        "sizeInBytes": 2048,
                        "mimeType": "text/plain",
                        "encoding": "utf-8"
                    },
                    "path": {"name": "/Company Home/Documents"}
                }
            }]
        }
    }

    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=mock_response)

    server.client.get = AsyncMock(return_value=response)

    result = await server.get_node_children("node-001", max_items=10)

    assert result["parent_id"] == "node-001"
    assert result["total"] == 1
    assert isinstance(result["items"], list)
    assert result["items"][0]["name"] == "Document.txt"
    assert result["items"][0]["type"] == "file"
    assert result["items"][0]["size"] == 2048
    assert "message" in result

@pytest.mark.asyncio
async def test_create_folder(server):

    mock_response ={
        "entry": {
            "id": "folder-001",
            "name": "TestFolder"
        }
    }

    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=mock_response)

    server.client.post = AsyncMock(return_value=response)

    result = await server.create_folder("TestFolder", parent_id="-root-", title="Titlu", description="Desc")

    assert result["created"] is True
    assert result["folder_id"] == "folder-001"
    assert result["folder_name"] == "TestFolder"
    assert result["parent_id"] == "-root-"
    assert "Folderul 'TestFolder'" in result["message"]

    server.client.post.assert_called_once()
    args, kwargs = server.client.post.call_args
    assert kwargs["json"]["name"] == "TestFolder"
    assert kwargs["json"]["nodeType"] == "cm:folder"
    assert kwargs["json"]["properties"]["cm:title"] == "Titlu"
    assert kwargs["json"]["properties"]["cm:description"] == "Desc"

@pytest.mark.asyncio
async def test_create_folder_already_exists(server):

    response = MagicMock()
    response.status_code = 409
    response.json.return_value = {
        "error": {
            "status code": 409,
            "briefSummary": "Folder already exists"
        }
    }

    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Conflict", request=MagicMock(), response=response
    )

    server.client.post = AsyncMock(return_value=response)

    # Rulează funcția și verifică că se aruncă excepția
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await server.create_folder("TestFolder")

    # Verifică dacă mesajul de eroare e cel așteptat
    assert "Conflict" in str(exc_info.value)
    assert exc_info.value.response.status_code == 409

@pytest.mark.asyncio
async def test_delete_node(server):

    node_id = "node-001"

    response = MagicMock()
    response.status_code = 204
    response.raise_for_status = MagicMock()

    server.client.delete = AsyncMock(return_value=response)

    result = await server.delete_node(node_id)
    assert result["deleted"] is True
    assert result["node_id"] == node_id
    assert result["permanent"] is False
    assert "trash" in result["message"]

@pytest.mark.asyncio
async def test_delete_node_not_found(server):

    node_id = "invalid_node"

    response = MagicMock()
    response.status_code = 404
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=response
    )

    server.client.delete = AsyncMock(return_value=response)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await server.delete_node(node_id)

    assert exc_info.value.response.status_code == 404

@pytest.mark.asyncio
async def test_get_node_info(server):

    node_id = "abc-123"

    mock_response = {
        "id": node_id,
        "name": "document.pdf",
        "isFolder": False,
        "nodeType": "cm:content",
        "createdAt": "2024-01-01T00:00:00.000Z",
        "modifiedAt": "2024-01-02T00:00:00.000Z",
        "createdByUser": {"displayName": "Admin"},
        "modifiedByUser": {"displayName": "Admin"},
        "parentId": "parent-456",
        "path": {"name": "/Company Home/docs", "isRoot": False},
        "content": {
            "sizeInBytes": 1024,
            "mimeType": "application/pdf",
            "encoding": "UTF-8"
        },
        "properties": {
            "cm:title": "Titlu",
            "cm:description": "Descriere"
        }
    }

    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"entry": mock_response})

    server.client.get = AsyncMock(return_value=response)

    result = await server.get_node_info(node_id)
    assert result["node"]["id"] == node_id
    assert result["node"]["type"] == "file"
    assert result["node"]["content"]["mimeType"] == "application/pdf"
    assert result["node"]["properties"]["title"] == "Titlu"

@pytest.mark.asyncio
async def test_get_node_info_not_found(server):
    node_id = "invalid-node"
    response = MagicMock()
    response.status_code = 404
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=response
    )

    server.client.get = AsyncMock(return_value=response)

    with pytest.raises(httpx.HTTPStatusError):
        await server.get_node_info(node_id)

@pytest.mark.asyncio
async def test_get_node_info_not_found(server):
    node_id = "invalid-node"
    response = MagicMock()
    response.status_code = 404
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=response
    )

    server.client.get = AsyncMock(return_value=response)

    with pytest.raises(httpx.HTTPStatusError):
        await server.get_node_info(node_id)

@pytest.mark.asyncio
async def test_browse_by_path_company_home_found(server):
    # Simulăm că avem un folder "Company Home"
    server.get_node_children = AsyncMock(side_effect=[
        {
            "items": [{"name": "Company Home", "type": "folder", "id": "company-home-id"}]
        },
        {
            "items": [{"id": "abc", "name": "doc", "type": "file"}],
            "message": "conținut companie"
        }
    ])

    result = await server.browse_by_path("/Company Home")
    assert "Navighează la path" in result["message"]
    assert result["items"][0]["name"] == "doc"

@pytest.mark.asyncio
async def test_browse_by_path_root(server):
    server.list_root_children = AsyncMock(return_value={"items": [{"name": "RootFile"}]})

    result = await server.browse_by_path("/")
    assert "items" in result
    assert result["items"][0]["name"] == "RootFile"

@pytest.mark.asyncio
async def test_get_node_id_by_name(server):
    
    mock_items = {
        "items": [
            {
                "id": "folder-001",
                "name": "TestFolder",
                "type": "folder"
            },
            {
                "id": "file-001",
                "name": "TestFile.txt",
                "type": "file"
            }
        ]
    }

    server.get_node_children = AsyncMock(return_value=mock_items)

    # test folder
    result_folder = await server.get_node_id_by_name("TestFolder")
    assert result_folder["id"] == "folder-001"
    assert result_folder["type"] == "folder"

    # test file
    result_folder = await server.get_node_id_by_name("TestFile.txt")
    assert result_folder["id"] == "file-001"
    assert result_folder["type"] == "file"

    # test negasit
    result_missing = await server.get_node_id_by_name("Inexistent")
    assert result_missing["error"] is True

@pytest.mark.asyncio
async def test_format_simple_response(server):

    raw = {
        "message": "Test Response",
        "items": [{"name": "FolderA", "type": "folder", "id": "id-001"}]
    }

    formatted = server.format_simple_response(raw, "context_test")
    assert formatted["summary"] == "Test Response"
    assert "- FolderA [folder] (ID: id-001)" in formatted["items"][0]