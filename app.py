import csv
import io
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

STATUSES = ('draft', 'ready', 'submitted', 'accepted', 'rejected')


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(SECRET_KEY=os.environ.get('STUDIO_SECRET_KEY', 'local-development-only'), MAX_CONTENT_LENGTH=25 * 1024 * 1024)
    if test_config:
        app.config.update(test_config)
    root = Path(app.config.get('DATA_DIR', app.instance_path))
    uploads = root / 'uploads'
    uploads.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect():
        db = sqlite3.connect(root / 'studio.sqlite3', timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    # Additive migration keeps images and metadata from the initial application.
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS niches (id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, description TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        db.execute("CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, filename TEXT NOT NULL, stored_name TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '')")
        columns = {row['name'] for row in db.execute('PRAGMA table_info(assets)')}
        additions = {
            'niche_id': 'TEXT REFERENCES niches(id) ON DELETE SET NULL',
            'status': "TEXT NOT NULL DEFAULT 'draft'",
            'category': "TEXT NOT NULL DEFAULT ''",
            'notes': "TEXT NOT NULL DEFAULT ''",
            'width': 'INTEGER', 'height': 'INTEGER',
            'created_at': "TEXT NOT NULL DEFAULT ''",
        }
        for name, declaration in additions.items():
            if name not in columns:
                db.execute(f'ALTER TABLE assets ADD COLUMN {name} {declaration}')
        db.execute("CREATE INDEX IF NOT EXISTS assets_niche ON assets(niche_id)")
        db.execute("CREATE INDEX IF NOT EXISTS assets_status ON assets(status)")

    @app.context_processor
    def shared():
        return {'statuses': STATUSES}

    @app.get('/')
    def index():
        with connect() as db:
            total = db.execute('SELECT count(*) FROM assets').fetchone()[0]
            counts = {row['status']: row['total'] for row in db.execute('SELECT status, count(*) AS total FROM assets GROUP BY status')}
            incomplete = db.execute("SELECT count(*) FROM assets WHERE trim(title)='' OR trim(keywords)=''").fetchone()[0]
            niches = db.execute('SELECT n.*, count(a.id) AS total FROM niches n LEFT JOIN assets a ON a.niche_id=n.id GROUP BY n.id ORDER BY total DESC, n.name LIMIT 5').fetchall()
            niche_count = db.execute('SELECT count(*) FROM niches').fetchone()[0]
            recent = db.execute('SELECT a.*, n.name AS niche_name FROM assets a LEFT JOIN niches n ON n.id=a.niche_id ORDER BY a.rowid DESC LIMIT 6').fetchall()
        return render_template('dashboard.html', total=total, counts=counts, incomplete=incomplete, niches=niches, niche_count=niche_count, recent=recent)

    def selected_assets(db, paginate=False):
        query = request.args.get('q', '').strip()[:200]
        niche_id = request.args.get('niche', '')
        status = request.args.get('status', '')
        where, params = [], []
        if query:
            where.append('(a.filename LIKE ? OR a.title LIKE ? OR a.keywords LIKE ?)')
            params += [f'%{query}%'] * 3
        if niche_id == 'unassigned':
            where.append('a.niche_id IS NULL')
        elif niche_id:
            where.append('a.niche_id=?')
            params.append(niche_id)
        if status in STATUSES:
            where.append('a.status=?')
            params.append(status)
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        total = db.execute('SELECT count(*) FROM assets a' + clause, params).fetchone()[0]
        page = max(1, request.args.get('page', 1, type=int) or 1)
        page = min(page, max(1, (total + 11) // 12))
        sql = 'SELECT a.*, n.name AS niche_name FROM assets a LEFT JOIN niches n ON n.id=a.niche_id' + clause + ' ORDER BY a.rowid DESC'
        if paginate:
            sql += ' LIMIT 12 OFFSET ?'
            params.append((page - 1) * 12)
        return db.execute(sql, params).fetchall(), total, page

    @app.get('/library')
    def library():
        with connect() as db:
            assets, total, page = selected_assets(db, paginate=True)
            niches = db.execute('SELECT * FROM niches ORDER BY name').fetchall()
        filters = {key: request.args.get(key, '') for key in ('q', 'niche', 'status')}
        return render_template('library.html', assets=assets, total=total, page=page, pages=max(1, (total + 11) // 12), niches=niches, filters=filters)

    @app.post('/upload')
    def upload():
        niche_id = request.form.get('niche_id') or None
        with connect() as db:
            if niche_id and not db.execute('SELECT id FROM niches WHERE id=?', (niche_id,)).fetchone():
                abort(400, 'Choose an existing niche.')
        files = request.files.getlist('images')
        count = 0
        for file in files:
            filename = secure_filename(file.filename or '')
            if not filename:
                continue
            try:
                with Image.open(file.stream) as img:
                    image_format = img.format
                    width, height = img.size
                    img.verify()
                if image_format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValueError('Unsupported image format')
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                flash(f'{filename}: choose a valid JPEG, PNG, or WebP image.', 'error')
                continue
            asset_id = uuid.uuid4().hex
            stored_name = asset_id + {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}[image_format]
            file.stream.seek(0)
            file.save(uploads / stored_name)
            try:
                with connect() as db:
                    db.execute("INSERT INTO assets (id, filename, stored_name, niche_id, width, height, created_at) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", (asset_id, filename, stored_name, niche_id, width, height))
            except Exception:
                (uploads / stored_name).unlink(missing_ok=True)
                raise
            count += 1
        if count:
            flash(f'Added {count} image(s).')
        elif not any(file.filename for file in files):
            flash('Choose at least one image.', 'error')
        return redirect(url_for('library'))

    @app.get('/assets/<asset_id>')
    def asset_detail(asset_id):
        with connect() as db:
            asset = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
            if not asset:
                abort(404)
            niches = db.execute('SELECT * FROM niches ORDER BY name').fetchall()
        return render_template('asset.html', asset=asset, niches=niches)

    @app.post('/assets/<asset_id>')
    def update(asset_id):
        with connect() as db:
            asset = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
            if not asset:
                abort(404)
            title = request.form.get('title', '').strip()
            keywords = list(dict.fromkeys(k.strip() for k in request.form.get('keywords', '').split(',') if k.strip()))
            status = request.form.get('status', asset['status'])
            niche_id = request.form.get('niche_id', asset['niche_id']) or None
            category = request.form.get('category', asset['category']).strip()
            notes = request.form.get('notes', asset['notes']).strip()
            error = None
            if len(title) > 200 or len(keywords) > 49:
                error = 'Use a title of at most 200 characters and up to 49 keywords.'
            elif status not in STATUSES:
                error = 'Choose a valid status.'
            elif status != 'draft' and (not title or not keywords):
                error = 'Add a title and keywords before marking an image ready or submitted.'
            elif len(category) > 100 or len(notes) > 5000:
                error = 'Category is limited to 100 characters and notes to 5,000.'
            elif niche_id and not db.execute('SELECT id FROM niches WHERE id=?', (niche_id,)).fetchone():
                error = 'Choose an existing niche.'
            if error:
                flash(error, 'error')
                return redirect(url_for('asset_detail', asset_id=asset_id))
            db.execute('UPDATE assets SET title=?, keywords=?, niche_id=?, status=?, category=?, notes=? WHERE id=?', (title, ', '.join(keywords), niche_id, status, category, notes, asset_id))
        flash('Metadata saved.')
        return redirect(url_for('asset_detail', asset_id=asset_id))

    @app.post('/assets/<asset_id>/delete')
    def delete_asset(asset_id):
        with connect() as db:
            asset = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
            if not asset:
                abort(404)
            # Only delete a row after its corresponding file has been removed.
            (uploads / asset['stored_name']).unlink(missing_ok=True)
            db.execute('DELETE FROM assets WHERE id=?', (asset_id,))
        flash('Image deleted from your library.')
        return redirect(url_for('library'))

    @app.get('/niches')
    def niches():
        with connect() as db:
            items = db.execute('SELECT n.*, count(a.id) AS total FROM niches n LEFT JOIN assets a ON a.niche_id=n.id GROUP BY n.id ORDER BY n.name').fetchall()
        return render_template('niches.html', niches=items)

    def save_niche(niche_id=None):
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        notes = request.form.get('notes', '').strip()
        if not name or len(name) > 100 or len(description) > 500 or len(notes) > 5000:
            flash('Enter a name (1–100 characters), description (up to 500), and notes (up to 5,000).', 'error')
            return redirect(url_for('niches'))
        try:
            with connect() as db:
                if niche_id:
                    if not db.execute('UPDATE niches SET name=?, description=?, notes=? WHERE id=?', (name, description, notes, niche_id)).rowcount:
                        abort(404)
                else:
                    db.execute('INSERT INTO niches (id, name, description, notes) VALUES (?, ?, ?, ?)', (uuid.uuid4().hex, name, description, notes))
        except sqlite3.IntegrityError:
            flash('A niche with that name already exists.', 'error')
            return redirect(url_for('niches'))
        flash('Niche saved.')
        return redirect(url_for('niches'))

    @app.post('/niches')
    def create_niche():
        return save_niche()

    @app.post('/niches/<niche_id>')
    def update_niche(niche_id):
        return save_niche(niche_id)

    @app.post('/niches/<niche_id>/delete')
    def delete_niche(niche_id):
        with connect() as db:
            if not db.execute('DELETE FROM niches WHERE id=?', (niche_id,)).rowcount:
                abort(404)
        flash('Niche deleted. Its images remain in the library, unassigned.')
        return redirect(url_for('niches'))

    @app.get('/images/<path:filename>')
    def image(filename):
        return send_from_directory(uploads, filename)

    @app.get('/export.csv')
    def export():
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['Filename', 'Title', 'Keywords', 'Category', 'Releases'])
        with connect() as db:
            assets, _, _ = selected_assets(db)
            for asset in assets:
                cells = [asset['filename'], asset['title'], asset['keywords'], asset['category'], '']
                writer.writerow(["'" + s if s.lstrip().startswith(('=', '+', '-', '@')) else s for s in cells])
        return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=stock-metadata.csv'})

    @app.errorhandler(413)
    def too_large(error):
        return render_template('error.html', code=413, message='Upload exceeds the 25 MB request limit. Try fewer or smaller images.'), 413

    @app.errorhandler(404)
    def missing(error):
        return render_template('error.html', code=404, message='This image or page could not be found.'), 404

    return app
