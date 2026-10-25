import csv
import io
import sqlite3
import uuid
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(SECRET_KEY="local-development-only", MAX_CONTENT_LENGTH=25 * 1024 * 1024)
    if test_config:
        app.config.update(test_config)
    root = Path(app.config.get("DATA_DIR", app.instance_path))
    uploads = root / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)

    def connect():
        db = sqlite3.connect(root / "studio.sqlite3")
        db.row_factory = sqlite3.Row
        return db

    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, filename TEXT NOT NULL, stored_name TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '')")

    @app.get("/")
    def index():
        with connect() as db:
            assets = db.execute("SELECT * FROM assets ORDER BY rowid DESC").fetchall()
        return render_template("index.html", assets=assets)

    @app.post("/upload")
    def upload():
        files = request.files.getlist("images")
        count = 0
        for file in files:
            filename = secure_filename(file.filename or "")
            if not filename:
                continue
            try:
                img = Image.open(file.stream)
                image_format = img.format
                img.verify()
                if image_format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported image format")
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                flash(f"{filename}: choose a valid JPEG, PNG, or WebP image.")
                continue
            asset_id = uuid.uuid4().hex
            stored_name = asset_id + {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
            file.stream.seek(0)
            file.save(uploads / stored_name)
            with connect() as db:
                db.execute("INSERT INTO assets (id, filename, stored_name) VALUES (?, ?, ?)", (asset_id, filename, stored_name))
            count += 1
        if count:
            flash(f"Added {count} image(s).")
        elif not any(file.filename for file in files):
            flash("Choose at least one image.")
        return redirect(url_for("index"))

    @app.post("/assets/<asset_id>")
    def update(asset_id):
        title = request.form.get("title", "").strip()
        keywords = list(dict.fromkeys(k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()))
        if len(title) > 200 or len(keywords) > 49:
            flash("Use a title of at most 200 characters and up to 49 keywords.")
            return redirect(url_for("index"))
        with connect() as db:
            result = db.execute("UPDATE assets SET title=?, keywords=? WHERE id=?", (title, ", ".join(keywords), asset_id))
            if not result.rowcount:
                abort(404)
        flash("Metadata saved.")
        return redirect(url_for("index"))

    @app.get("/images/<path:filename>")
    def image(filename):
        return send_from_directory(uploads, filename)

    @app.get("/export.csv")
    def export():
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Filename", "Title", "Keywords", "Category", "Releases"])
        with connect() as db:
            for asset in db.execute("SELECT * FROM assets ORDER BY rowid"):
                # Prevent spreadsheet formulas in user-supplied cells.
                cells = [asset["filename"], asset["title"], asset["keywords"]]
                writer.writerow(["'" + s if s.lstrip().startswith(("=", "+", "-", "@")) else s for s in cells] + ["", ""])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=stock-metadata.csv"})

    @app.errorhandler(413)
    def too_large(error):
        return "Upload exceeds the 25 MB request limit.", 413

    return app
