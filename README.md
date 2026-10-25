# Stock Studio

A local Flask application for preparing image metadata. Upload JPEG, PNG, and WebP files, edit titles and comma-separated keywords, and export a CSV with Adobe Stock metadata columns. Category and releases are left blank for manual completion. This independent project does not connect to Adobe or generate metadata with AI.

## Development

Requires Python 3.12+ and uv.

```sh
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --frozen
uv run flask --app app:create_app run --host 0.0.0.0 --port 5000
```

Run checks with `uv run pytest`. Dependencies are pinned in `uv.lock`.

Images and SQLite data are stored in the ignored `instance/` directory. Upload requests have a 25 MB limit. Saved metadata persists across restarts. CSV export includes saved edits only.

This starter is intended for a trusted local development environment. It has no authentication or CSRF protection; add these and configure a secret key before deploying to a shared or public service. The Flask development server is not a production server.
