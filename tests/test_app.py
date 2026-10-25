import csv
import io

from PIL import Image

from app import create_app


def test_upload_edit_export_and_persistence(tmp_path):
    config = {"TESTING": True, "DATA_DIR": str(tmp_path)}
    client = create_app(config).test_client()
    assert b"A blank canvas" in client.get("/").data
    image = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(image, format="PNG")
    image.seek(0)
    response = client.post("/upload", data={"images": (image, "forest.png")}, follow_redirects=True)
    assert b"Added 1 image" in response.data
    import sqlite3
    with sqlite3.connect(tmp_path / "studio.sqlite3") as db:
        asset_id, stored_name = db.execute("SELECT id, stored_name FROM assets").fetchone()
    assert client.get(f"/images/{stored_name}").status_code == 200
    client.post(f"/assets/{asset_id}", data={"title": "Green forest", "keywords": "green, trees, green"})
    restored = create_app(config).test_client()
    rows = list(csv.reader(io.StringIO(restored.get("/export.csv").text)))
    assert rows[1] == ["forest.png", "Green forest", "green, trees", "", ""]


def test_invalid_upload_and_limits(tmp_path):
    client = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)}).test_client()
    response = client.post("/upload", data={"images": (io.BytesIO(b"not an image"), "bad.png")}, follow_redirects=True)
    assert b"choose a valid" in response.data
    assert len(list(csv.reader(io.StringIO(client.get("/export.csv").text)))) == 1
    assert client.post("/assets/missing", data={"title": "test"}).status_code == 404
