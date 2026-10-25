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


def upload_image(client, filename='festival.png', niche_id=''):
    image = io.BytesIO()
    Image.new('RGB', (40, 30), 'orange').save(image, format='PNG')
    image.seek(0)
    return client.post('/upload', data={'images': (image, filename), 'niche_id': niche_id}, follow_redirects=True)


def read_rows(tmp_path, query):
    import sqlite3
    with sqlite3.connect(tmp_path / 'studio.sqlite3') as db:
        db.row_factory = sqlite3.Row
        return db.execute(query).fetchall()


def test_niche_lifecycle_and_library_filters(tmp_path):
    config = {'TESTING': True, 'DATA_DIR': str(tmp_path)}
    client = create_app(config).test_client()
    result = client.post('/niches', data={'name': 'Festivals', 'description': 'Seasonal traditions', 'notes': 'Lanterns and flowers'}, follow_redirects=True)
    assert b'Seasonal traditions' in result.data
    niche = read_rows(tmp_path, 'SELECT * FROM niches')[0]
    assert b'already exists' in client.post('/niches', data={'name': 'festivals'}, follow_redirects=True).data
    assert len(read_rows(tmp_path, 'SELECT * FROM niches')) == 1
    upload_image(client, niche_id=niche['id'])
    upload_image(client, filename='nature.png')
    asset = read_rows(tmp_path, "SELECT * FROM assets WHERE filename='festival.png'")[0]
    assert (asset['width'], asset['height']) == (40, 30)
    assert asset['created_at']
    response = client.post(f"/assets/{asset['id']}", data={'title': 'Lantern festival', 'keywords': 'lantern, temple', 'status': 'ready', 'category': '21', 'notes': 'Review releases', 'niche_id': niche['id']}, follow_redirects=True)
    assert b'Metadata saved' in response.data
    for path in ['/library?q=Lantern', f"/library?niche={niche['id']}", '/library?status=ready']:
        response = client.get(path)
        assert b'Lantern festival' in response.data
        assert b'nature.png' not in response.data
    assert b'nature.png' in client.get('/library?niche=unassigned').data
    assert b'Lantern festival' not in client.get('/library?niche=unassigned').data
    rows = list(csv.reader(io.StringIO(client.get('/export.csv?status=ready').text)))
    assert len(rows) == 2
    assert rows[1][3] == '21'
    dashboard = client.get('/').text
    assert 'Ready to submit' in dashboard and 'Lantern festival' in dashboard
    client.post(f"/niches/{niche['id']}", data={'name': 'Thai festivals', 'description': 'Updated', 'notes': 'New ideas'})
    assert b'Thai festivals' in client.get('/niches').data
    client.post(f"/niches/{niche['id']}/delete")
    assert not read_rows(tmp_path, 'SELECT * FROM niches')
    assets = read_rows(tmp_path, 'SELECT * FROM assets')
    assert len(assets) == 2 and all(a['niche_id'] is None for a in assets)
    assert create_app(config).test_client().get(f"/images/{asset['stored_name']}").status_code == 200


def test_metadata_validation_and_image_deletion(tmp_path):
    client = create_app({'TESTING': True, 'DATA_DIR': str(tmp_path)}).test_client()
    assert client.post('/upload', data={'niche_id': 'missing'}).status_code == 400
    upload_image(client)
    asset = read_rows(tmp_path, 'SELECT * FROM assets')[0]
    path = f"/assets/{asset['id']}"
    for fields in [
        {'title': '', 'keywords': '', 'status': 'ready'},
        {'title': 'x' * 201},
        {'keywords': ','.join(str(i) for i in range(50))},
        {'status': 'invented'},
        {'niche_id': 'missing'},
    ]:
        result = client.post(path, data=fields, follow_redirects=True)
        assert 'notice error' in result.text
        assert read_rows(tmp_path, 'SELECT * FROM assets')[0]['status'] == 'draft'
    client.post(path, data={'title': '=SUM(1,2)', 'keywords': 'flowers'})
    rows = list(csv.reader(io.StringIO(client.get('/export.csv').text)))
    assert rows[1][1].startswith("'=")
    client.post(path + '/delete')
    assert not read_rows(tmp_path, 'SELECT * FROM assets')
    assert not (tmp_path / 'uploads' / asset['stored_name']).exists()
    assert client.get(path).status_code == 404
    assert client.post(path + '/delete').status_code == 404


def test_upgrade_original_database_is_repeatable(tmp_path):
    import sqlite3
    with sqlite3.connect(tmp_path / 'studio.sqlite3') as db:
        db.execute("CREATE TABLE assets (id TEXT PRIMARY KEY, filename TEXT NOT NULL, stored_name TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '')")
        db.execute("INSERT INTO assets VALUES ('old', 'old.png', 'old.png', 'Original title', 'original')")
    config = {'TESTING': True, 'DATA_DIR': str(tmp_path)}
    for _ in range(2):
        client = create_app(config).test_client()
        assert b'Original title' in client.get('/library').data
        assert b'Original title' in client.get('/assets/old').data
        assert b'Original title' in client.get('/export.csv').data
    asset = read_rows(tmp_path, 'SELECT * FROM assets')[0]
    assert asset['status'] == 'draft' and asset['niche_id'] is None


def test_pagination_and_upload_limit(tmp_path):
    client = create_app({'TESTING': True, 'DATA_DIR': str(tmp_path), 'MAX_CONTENT_LENGTH': 1024 * 1024}).test_client()
    for i in range(13):
        upload_image(client, filename=f'image-{i:02}.png')
    first = client.get('/library').text
    second = client.get('/library?page=2').text
    assert first.count('class="card"') == 12
    assert second.count('class="card"') == 1
    assert 'Page 2 of 2' in second
    assert 'Page 2 of 2' in client.get('/library?page=999').text
    assert client.post('/upload', data={'images': (io.BytesIO(b'x' * (1024 * 1024 + 1)), 'big.png')}).status_code == 413
