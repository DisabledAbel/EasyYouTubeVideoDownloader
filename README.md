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

## Local or Vercel?

| Mode | Website | Download processing and files |
| --- | --- | --- |
| Local | Served by Python, or Trunk during development | The same local Python server |
| Docker | Served by the container | The same container, with a persistent volume |
| Vercel | Rust frontend compiled to static WebAssembly | A separately hosted Python backend with an HTTPS address |

**Vercel deployment hosts the frontend only.** This project does not run yt-dlp, FFmpeg, a persistent job queue, or video storage in Vercel functions. The browser connects directly to your backend, including for file downloads. A Vercel frontend without a running backend cannot download videos.

See [Vercel function limits](https://vercel.com/docs/functions/limitations) and [Leptos CSR deployment](https://book.leptos.dev/deployment/csr.html).

## Easiest local setup: Docker

Install Docker Desktop on the iMac (or use Docker on Linux). From a checkout of this repository:

```bash
cp .env.example .env
```

Generate a secret and replace `ARCHIVE_API_KEY` in `.env` with its output:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
docker compose up --build -d
```

Open `http://localhost:8000`. In **Download server settings**, enter the same access key and connect. To access it from a phone or tablet on the same trusted Wi-Fi network, open `http://YOUR-COMPUTER-LAN-IP:8000` and set that same address as the server. The computer must stay running, and its firewall must allow the connection. Use HTTPS when exposing the service outside your local network.

The named `archives` volume preserves the database and files. The container runs as an unprivileged user and includes FFmpeg and Node.js for yt-dlp's YouTube support. Run **one backend process and one replica per data directory**; the in-process scheduler is not a distributed queue.

## Development without Docker

Requires Python 3.12+, Node.js 22+, FFmpeg/FFprobe, and Rust. macOS and Linux are supported directly; use Docker for Windows. The browser client does not need these tools installed.

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements-dev.txt
```

```bash
cp .env.example .env
```

Replace the example access key with a generated secret, then start Python:

```bash
python -m uvicorn backend.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8000
```

In a second terminal, install the pinned Rust toolchain, WebAssembly target, and Trunk:

```bash
bash scripts/install-frontend.sh
```

```bash
cd frontend
```

```bash
NO_COLOR=true trunk serve
```

Open `http://localhost:8080`, keep the server address as `http://localhost:8080`, and enter your access key. Trunk proxies `/api/` to Python. To instead serve the production frontend from Python, run `bash scripts/build-frontend.sh` from the repository root, then restart Python and open `http://localhost:8000`.

## Deploy the frontend to Vercel

1. Import this GitHub repository into Vercel with the repository root as the project root and **Other** as the framework. `vercel.json` supplies the install command, build command, and `frontend/dist` output directory.
2. Optionally set the **public build variable** `ARCHIVE_API_URL` to your backend's origin, such as `https://archive.example.com`. This address is compiled into the browser app; never put a key or password in it. Users can also enter the address in server settings.
3. Deploy the Python Docker container to a container host with an HTTPS endpoint and a persistent `/data` volume. Set `ARCHIVE_API_KEY` to a generated secret. Configure port `8000`, one replica, and one worker.
4. Set the backend's `ALLOWED_ORIGINS` to the exact Vercel origin, for example `https://your-project.vercel.app`. Multiple origins are comma-separated. Add preview origins explicitly when testing a Vercel preview. Wildcards are rejected.
5. Open the Vercel website, connect to the backend, and enter the access key. Share the key privately with trusted users. Anyone with the key can see and delete this shared server's archives. Keys are held in browser memory and are cleared on a page reload.

The Vercel HTTPS website requires an HTTPS backend; it cannot reliably use an HTTP localhost or private-network backend because of browser mixed-content and local-network restrictions. Use the local website when running everything locally. This repository does not provision or pay for a backend host.

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

GitHub Actions runs backend tests, builds the Rust/WebAssembly website, and builds the Docker image on pull requests, pushes to `main`, and manual dispatch. It uploads the website build as an artifact. Tests simulate the media provider; they do not download third-party videos.

## License

[GPL-3.0](LICENSE). The repository's original license is preserved. Third-party components retain their own licenses.
