# Stock Studio

A local application for managing stock image collections. Built with Flask, Pillow, and SQLite. No account, API key, or external database service is needed.

## Windows: start here

1. Install **Python 3.12 or newer** from https://www.python.org/downloads/windows/ and enable the Python launcher during installation.
2. Download the repository ZIP from GitHub (**Code → Download ZIP**).
3. Right-click the ZIP and choose **Extract All**. Open the extracted project folder.
4. Double-click **start-windows.bat**. The first run installs the pinned application dependencies and requires Internet access.
5. Keep the terminal window open and open **http://localhost:5000** in Chrome.

The launcher always runs from the project folder, avoiding `Could not import app` errors. Press **Ctrl+C** in the terminal to stop the server. Double-click the launcher again to restart it. Do not run the launcher from inside the ZIP archive.

If your existing `.venv` is in the parent folder, you can leave it there; the launcher creates the project's own `.venv` automatically. If port 5000 is already in use, stop the previous Flask terminal with Ctrl+C first.

## Your workspace

- **Dashboard:** image and niche totals, manually tracked submission pipeline, metadata completeness, and recent images.
- **Niche manager:** create and edit themes, descriptions, and planning notes; view each niche's collection. Deleting a niche preserves its images and removes their assignment.
- **Image library:** upload multiple JPEG, PNG, or WebP images; search filenames, titles, and keywords; filter by niche or status; browse 12 images per page.
- **Image details:** preview and download the original, edit metadata, assign a niche, record category and private notes, and track draft/ready/submitted/accepted/rejected status. Deleting an image removes its original file and metadata permanently.
- **CSV export:** export all images or the current library filters with Filename, Title, Keywords, Category, and Releases columns. Releases are left blank; notes and niches are private and excluded. Export includes saved edits only. Spreadsheet formula prefixes are escaped.

Titles are limited to 200 characters and keywords to 49. Non-draft statuses require a title and keywords. Marking an image ready does not verify releases, resolution, or marketplace eligibility. This independent project does not connect to Adobe, submit images, report marketplace analytics, or generate metadata with AI.

## Database and backups

The app creates `instance/studio.sqlite3` and `instance/uploads/` automatically. Metadata and uploaded originals persist across server restarts. Existing databases from the first version are upgraded additively without deleting records or files. Older images keep their metadata; dimensions and upload dates may be unavailable.

To back up, stop the app and copy the **entire instance folder**, including the database and uploads. To upgrade from a fresh project download, stop the old app, back up `instance/`, copy that folder into the new project folder, and then launch the new version. Do not delete the old copy until your collection is verified. Local data is ignored by Git and is not included in repository ZIP downloads.

## Development

Requires Python 3.12+ and uv.

```sh
uv sync --frozen
uv run --frozen flask --app app:create_app run --host 127.0.0.1 --port 5000
uv run --frozen pytest
```

In the Codex cloud environment, first set `UV_CACHE_DIR=/workspace/.cache/uv` and bind to `0.0.0.0` when needed. Cloud loopback addresses cannot be opened from a separate PC. Python dependencies are pinned in `uv.lock`. No frontend build step is required.

This application is for a trusted local development environment. It has no authentication or CSRF protection. Before exposing it to other users, add those protections, configure `STUDIO_SECRET_KEY`, and use a production WSGI server. The development server binds only to your computer by default. The maximum upload request size is 25 MB.
