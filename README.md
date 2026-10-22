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

## Deploy the frontend to Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FDisabledAbel%2FEasyYouTubeVideoDownloader)

**This button deploys the website only. You also need a running Python backend with HTTPS.** It uses this repository's default branch; merge the initial implementation PR before deploying from `main`.

1. Deploy the Python Docker container to a container host with an HTTPS endpoint and a persistent `/data` volume. Set a generated `ARCHIVE_API_KEY`, use port `8000`, and run one replica with one worker.
2. Click **Deploy with Vercel** above. Use the repository root and **Other** as the framework. `vercel.json` supplies the build settings. Optionally set `ARCHIVE_API_URL` to your backend origin, such as `https://archive.example.com`, to prefill the app's server address. This is a public build variable; never put an access key in it.
3. Set the backend's `ALLOWED_ORIGINS` to your deployed Vercel origin, such as `https://your-project.vercel.app`. Separate multiple origins with commas; add preview origins explicitly when testing preview deployments.
4. Open the Vercel website, enter your backend address and access key under **Download server settings**, and select **Connect server**.

Share the access key privately with trusted users. Anyone with it can see and delete this shared server's archives. Keys stay in browser memory and are cleared on reload.

The Vercel HTTPS website requires an HTTPS backend; it cannot reliably use an HTTP localhost or private-network backend because of browser mixed-content and local-network restrictions. Use the local website when running everything locally. This repository does not provision or pay for a backend host.

## Publishing images to GHCR

The **Publish Docker image to GHCR** job in the **CI** workflow runs after backend tests, the frontend build, and container build/startup checks on both architectures pass. It publishes automatically on pushes to `main`. To publish manually, open **Actions → CI → Run workflow**, select `main`, and run it. Pull requests and manual runs on other branches do not publish.

Images are published to `ghcr.io/disabledabel/easyyoutubevideodownloader` with two tags:

- `latest`: the latest successfully published `main` commit.
- `sha-<full-commit-sha>`: an image for a specific commit.

The workflow uses GitHub's built-in `GITHUB_TOKEN` with `packages: write`; no PAT or extra repository secret is needed. Image labels link the package to this repository.

**One-time owner setup after the first publish:** GitHub creates new container packages as private. On your GitHub profile, open **Packages → easyyoutubevideodownloader → Package settings → Change visibility → Public** so users can pull without signing in. See [GitHub's package visibility instructions](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).

If publishing reports a package permission error, check that the package grants Actions access to this repository and that repository or organization policy permits package writes. An existing private package requires authentication until its visibility is changed to public.

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
