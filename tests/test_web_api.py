"""
API tests for FastAPI web endpoints and wizard flow.
Uses TestClient from starlette / httpx.
"""

from starlette.testclient import TestClient

from smart_credit_parser.web.app import app

client = TestClient(app)


def test_web_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "Smart Credit System" in response.text
    assert "Мастер загрузки данных" in response.text


def test_api_full_flow():
    # 1. Upload CSV file
    csv_content = (
        "ИНН;Название компании;Отрасль;Дата регистрации\n"
        "1002600008888;ТехноТранс SRL;Логистика;2021-04-10\n"
    ).encode("utf-8")

    files = {"file": ("logistics.csv", csv_content, "text/csv")}
    headers = {"x-user-id": "analyst_demo", "x-user-role": "ANALYST"}

    upload_resp = client.post("/api/upload", files=files, headers=headers)
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert "session_id" in data
    session_id = data["session_id"]
    assert "ИНН" in data["headers"]

    # 2. Get Mapping
    map_resp = client.get(f"/api/mapping/{session_id}?target_table=businesses")
    assert map_resp.status_code == 200
    map_data = map_resp.json()
    assert map_data["target_table"] == "businesses"

    # 3. Update Mapping
    update_payload = {
        "target_table": "businesses",
        "custom_mappings": {
            "ИНН": "tax_id",
            "Название компании": "legal_name",
            "Отрасль": "industry_code",
            "Дата регистрации": "registration_date",
        },
        "save_to_cache": True,
    }
    upd_resp = client.post(f"/api/mapping/{session_id}", json=update_payload)
    assert upd_resp.status_code == 200

    # 4. Dry-Run
    dry_resp = client.post(f"/api/dry-run/{session_id}", json={})
    assert dry_resp.status_code == 200
    dry_data = dry_resp.json()
    assert dry_data["rows_accepted"] == 1
    assert dry_data["is_ready_for_commit"] is True

    # 5. Commit by ANALYST must be blocked with 403 Forbidden
    analyst_commit = client.post(
        f"/api/commit/{session_id}",
        json={"user_id": "analyst_demo", "user_role": "ANALYST"},
    )
    assert analyst_commit.status_code == 403

    # 6. Commit by UNDERWRITER must succeed
    uw_commit = client.post(
        f"/api/commit/{session_id}",
        json={"user_id": "underwriter_chief", "user_role": "UNDERWRITER"},
    )
    assert uw_commit.status_code == 200
    commit_data = uw_commit.json()
    assert commit_data["status"] == "COMMITTED"
    assert commit_data["inserted_count"] == 1

    # 7. History
    hist_resp = client.get("/api/history")
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert len(hist) >= 1
    assert any(h["session_id"] == session_id and h["status"] == "COMMITTED" for h in hist)

    # 8. Report Download
    rep_resp = client.get(f"/api/report/{session_id}?format=markdown")
    assert rep_resp.status_code == 200
    assert "Отчет разбора данных" in rep_resp.text
