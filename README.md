# EasyYouTubeVideoDownloader

A simple video archiver for downloading public-domain and authorized YouTube videos with captions, metadata, and source links. Works in modern browsers on phones, tablets, and computers.

**Rust + Leptos frontend. Python + yt-dlp backend. GPL-3.0.**

## What it does

- Saves individual YouTube videos as MP4 (up to 1080p) or audio as M4A.
- Offers a media download or a ZIP containing media, English creator captions when available, description, source link, and dated metadata.
- Queues downloads, displays progress for the current stream, and avoids duplicates for the same video, format, and caption preference.
- Keeps archive history in SQLite across restarts. Interrupted downloads are marked failed and can be retried.
- Protects the API with a shared access key and uses short-lived links for direct browser downloads, without loading large files into browser memory.
- Limits queue length, download duration, file sizes, retention, and archive count. Defaults: one running download, five queued/running, 512 MiB per archive contents, two-hour source duration, 15-minute processing timeout, 20 records, 24-hour retention.

Copyright status is not automatically determined. Archive videos you own, have permission to download, or have confirmed are public domain. Old recordings are not necessarily public domain.

## Choose how to run the app

| Mode | Website | Download processing and files |
| --- | --- | --- |
| Local | Served by Python, or Trunk during development | The same local Python server |
| Docker | Served by the container | The same container, with a persistent volume |
| GitHub Codespaces | Open the full app in your browser, including on iPad | Docker runs inside your codespace |

For an iPad-only development and testing setup, use [GitHub Codespaces](#run-in-github-codespaces-ipad-friendly). The website and Python backend run together there, so you do not need another computer or a separate hosting service.

## Run locally with Docker (recommended)

Install and start [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Mac or Windows, or Docker Engine with Compose on Linux. The prebuilt image includes Python, Node.js, and FFmpeg; you do not need to install them or compile Rust. Images support Intel/AMD (`amd64`) and Apple Silicon (`arm64`).

The prebuilt image becomes available after the first successful publishing run on `main` and the package is made public. Until then, use [Build the image yourself](#build-the-image-yourself) below.

**1. Get the project.** Download this repository using **Code → Download ZIP**, extract it, and open a terminal in the extracted folder. Run every command below from that folder.

**2. Set your access key.** For first-time setup, copy the settings file. Keep your existing `.env` when updating.

```bash
cp .env.example .env
```

Generate a key using Docker:

```bash
docker run --rm python:3.12-slim-bookworm python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Open `.env` in a text editor and paste the generated key after `ARCHIVE_API_KEY=`. Save the file and keep the key for signing in to the app. The other settings can stay as they are.

**3. Download the image and start the app.** Docker chooses the image for your computer's architecture.

```bash
docker compose pull
```

```bash
docker compose up -d
```

Open [http://localhost:8000](http://localhost:8000). Under **Download server settings**, use `http://localhost:8000` as the server address, paste your access key, and select **Connect server**.

To stop the app while keeping your archives:

```bash
docker compose down
```

If startup fails, view the logs:

```bash
docker compose logs --tail=100 archiver
```

To update, run `docker compose pull` followed by `docker compose up -d` again. Your configured access key and archive volume are preserved.

### Build the image yourself

To run your own code changes or use the app before an image is published, complete the same `.env` setup above, then build locally:

```bash
docker compose -f compose.yaml -f compose.build.yaml up --build -d
```

This uses a separate `:local` image tag and the same settings, ports, and archive volume. The first build can take several minutes.

### Use another device on the same Wi-Fi

Keep the host computer and Docker running. On your phone or tablet, open `http://YOUR-COMPUTER-LAN-IP:8000`, use that same address in server settings, and enter your access key. Allow port `8000` through the host computer's firewall if needed. Use HTTPS when exposing the service outside your trusted local network.

Archives and history are stored in the Docker `archives` volume and survive restarts. Run **one backend process and one replica per data directory**; the queue is not distributed.

## Run locally without Docker

For macOS or Linux, install Python 3.12+, Node.js 22+, and FFmpeg/FFprobe. The setup script installs Rust and Trunk. Use Docker on Windows. Start in the project folder.

**1. Install Python dependencies.**

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

**2. Create your settings.** Skip the copy if you already have a configured `.env`.

```bash
cp .env.example .env
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the generated key after `ARCHIVE_API_KEY=` in `.env` and save the file.

**3. Build the website and start the app.** The setup script installs the pinned Rust toolchain and Trunk.

```bash
bash scripts/install-frontend.sh
```

```bash
bash scripts/build-frontend.sh
```

```bash
python -m uvicorn backend.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8000
```

Open [http://localhost:8000](http://localhost:8000), use that address in server settings, and connect with your access key. Keep the terminal running; press **Ctrl+C** to stop the app.

For automatic frontend reloads during development, leave Python running and open a second terminal in the project folder:

```bash
cd frontend
```

```bash
NO_COLOR=true "$HOME/.cargo/bin/trunk" serve
```

Open [http://localhost:8080](http://localhost:8080) and use that address in server settings. Trunk forwards API requests to Python on port `8000`. To run the backend tests, first install `requirements-dev.txt` in your active virtual environment.

## Run in GitHub Codespaces (iPad-friendly)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/DisabledAbel/EasyYouTubeVideoDownloader)

Codespaces runs the full app in a cloud development environment. You can create it, use its terminal, and open the app from Safari on your iPad. The button opens the creation page; it does not start the app automatically.

**1. Create a codespace.** Select `main` and a **2-core** machine, then create the codespace. Wait for the browser editor and terminal to open. Use GitHub's default development environment, which includes Docker and Compose.

**2. Set an access key.** In the codespace terminal, start in the repository folder. For first-time setup:

```bash
cp .env.example .env
```

```bash
docker run --rm python:3.12-slim-bookworm python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Open `.env` in the editor, paste the generated key after `ARCHIVE_API_KEY=`, and save. Keep an already configured `.env` when resuming an existing codespace. Do not commit this file or share the key publicly.

**3. Build and start the app.** This builds the code in your codespace, so it also works before a public GHCR image is available. The first build can take several minutes.

```bash
docker compose -f compose.yaml -f compose.build.yaml up --build -d
```

**4. Open the app.** In the editor's **Ports** tab, select **Forward a Port** and enter `8000`. Keep its visibility **Private**, then select **Open in Browser**. Sign in to GitHub if prompted. The app opens at an HTTPS address like `https://CODESPACENAME-8000.app.github.dev`.

Under **Download server settings**, use that forwarded HTTPS origin as the server address and enter your access key. The address should already be filled in. Do not use `localhost:8000` in Safari on your iPad; that would refer to the iPad rather than the codespace. The frontend and API share the forwarded origin, so the default `ALLOWED_ORIGINS` setting does not need to change.

If the app does not open, check its logs in the codespace terminal:

```bash
docker compose logs --tail=100 archiver
```

**5. Stop when finished.** Open [your codespaces](https://github.com/codespaces), open the codespace's **…** menu, and choose **Stop codespace**. Resume it from the same page next time, then repeat the start command if the app is not already running. Closing a Safari tab alone does not immediately stop the codespace.

### Free usage and storage

GitHub Free personal accounts include **120 core-hours per month** (about **60 running hours on a 2-core machine**) and **15 GB-month of storage**. No payment method is required for the included allowance; without one, further usage is blocked after the quota is exhausted. Storage usage includes stopped codespaces, and development files and Docker images also take space. See [GitHub Codespaces billing](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces).

Codespaces is for on-demand development and testing, not permanent hosting. It normally stops after 30 minutes of inactivity. Save completed downloads to your iPad's Files app for long-term archiving; app files still expire according to `RETENTION_HOURS`, and deleting the codespace removes its data. YouTube downloads may also be blocked from cloud IP addresses and must be tested in your codespace.

## Configuration

See [.env.example](.env.example) for all settings. Python loads `.env` only when started with `--env-file .env` or via Docker Compose. Files are automatically removed after the retention period, so download your copies for long-term storage. ZIP storage roughly doubles the media's disk usage; with the defaults, allow at least 20 GiB plus working space for a full server. Use a host-level disk quota for a strict disk boundary.

Progress percentages describe the current media stream and may restart when audio starts or processing begins. Creator-provided English captions are saved when available; automatic captions, playlists, live streams, DRM, login cookies, and geographic restriction workarounds are not included. Missing MP4-compatible formats can fail rather than silently change the requested format.

YouTube may block downloads from cloud IP addresses or change its extraction requirements. Such failures appear in the archive list; delete a failed record or submit its link again to retry. Dependabot proposes yt-dlp updates weekly. Do not assume that any specific cloud host or video will work until tested.

## Validation

```bash
python -m pytest -q
```

```bash
cargo fmt --manifest-path frontend/Cargo.toml -- --check
```

```bash
bash scripts/build-frontend.sh
```

GitHub Actions runs backend tests, builds the Rust/WebAssembly website, and builds and starts the Docker image on Intel/AMD and ARM runners on pull requests, pushes to `main`, and manual dispatch. It uploads the website build as an artifact. Successful runs on `main` also publish the multi-platform image to GHCR. Tests simulate the media provider; they do not download third-party videos.

## License

[GPL-3.0](LICENSE). The repository's original license is preserved. Third-party components retain their own licenses.
