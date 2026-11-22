from fastapi.testclient import TestClient

from app.core.security import create_tokens
from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_management_and_other_profiles_require_authorization() -> None:
    member, _ = create_tokens({"id": 1, "tipo": "usuario", "rol": "Alumno"})
    member_headers = {"Authorization": f"Bearer {member}"}
    with TestClient(app) as client:
        assert client.get("/api/users/").status_code == 401
        assert client.get("/api/trabajadores/").status_code == 401
        assert client.get("/api/reniec/00000001").status_code == 401
        assert client.delete("/api/losas/1", headers=member_headers).status_code == 403
        assert client.delete("/api/disciplinas/1", headers=member_headers).status_code == 403
        assert client.delete("/api/dias-bloqueados/1", headers=member_headers).status_code == 403
        assert client.get("/api/users/2", headers=member_headers).status_code == 403
        assert client.get("/api/trabajadores/1", headers=member_headers).status_code == 403


def test_openapi_contains_existing_route_prefixes() -> None:
    with TestClient(app) as client:
        document = client.get("/openapi.json").json()
    paths = document["paths"]
    assert "/api/auth/login/usuario" in paths
    assert "/api/permisos/" in paths
    assert "/api/disciplinas/" in paths
    assert "/api/notificaciones/" in paths
    assert "/api/permisos/revision-automatica" in paths
    assert "/api/reportes/resumen" in paths
    assert "/api/reportes/pdf" in paths
    assert "/api/reportes/estado" in paths
    assert "/api/reportes/regenerar" in paths
    assert "delete" in paths["/api/reportes"]
    assert "/api/chatbot/" in paths
    assert "post" in paths["/api/chatbot/conversacion"]
    original_paths = {
        path: operations for path, operations in paths.items()
        if not path.startswith(("/api/aprendizaje/", "/api/administracion/"))
    }
    assert sum(len(operations) for operations in original_paths.values()) == 66
    assert "get" in paths["/api/administracion/inicio"]
    assert "get" in paths["/api/aprendizaje/recomendaciones"]
    assert "post" in paths["/api/aprendizaje/asistencias/{detalle_id}"]
    assert "post" in paths["/api/aprendizaje/medidas/{medida_id}/revision"]
    status_schema = document["components"]["schemas"]["EstadoPermisoIn"]
    assert status_schema["required"] == ["estado"]
    assert "id_t" not in status_schema["properties"]
