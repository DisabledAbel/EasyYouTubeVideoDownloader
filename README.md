# EasyYouTubeVideoDownloader

Download public-domain and authorized YouTube videos from a browser on your phone, tablet, or computer.

**Rust + Leptos frontend · Python + yt-dlp backend · GPL-3.0**

- **Video or audio:** MP4 up to 1080p, or audio-only M4A.
- **Extras:** download a ZIP with the media, English creator captions when available, description, source link, and dated metadata.
- **Download history:** a queue, progress updates, duplicate detection, and SQLite history across restarts.
- **Light and dark mode:** choose Light, Dark, or System under **Appearance**.
- **Your server:** a shared access key protects the API; short-lived links let your browser save completed files.

Download only videos you own, have permission to download, or have confirmed are public domain. The app does not check copyright status; an old recording is not necessarily public domain.

## Choose your setup

| You want to… | Start here |
| --- | --- |
| Run on a Mac, Windows PC, or Linux computer | [Docker](#docker-mac-windows-or-linux) |
| Change the code or run without Docker | [Development](#development) |
| Use an iPad without another computer | [GitHub Codespaces](#github-codespaces-ipad) |

The website and download server run together. On iPad, Codespaces runs the server while Safari displays the app. **YouTube can block cloud servers, so a running app does not guarantee a successful download.**

## Get the project locally

For Docker or development on your own computer, install Git if needed, then open a terminal and clone the repository:

```bash
git clone https://github.com/DisabledAbel/EasyYouTubeVideoDownloader.git
```

Enter the project folder:

```bash
cd EasyYouTubeVideoDownloader
```

Run the remaining setup commands from this folder. If you already have a checkout, open that folder instead of cloning again. Without Git, use **Code → Download ZIP**, extract it, and open a terminal in the extracted folder.

Continue with [Docker setup](#docker-mac-windows-or-linux) or [Development](#development).

## Docker (Mac, Windows, or Linux)

Install and start [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Mac or Windows, or Docker Engine with Compose on Linux. The image supports Intel/AMD and Apple Silicon and includes Python, Node.js, and FFmpeg.

1. Follow [Get the project locally](#get-the-project-locally) above.
2. Follow [Create your access key](#2-create-your-access-key) below.
3. Start the app:

```bash
docker compose pull
```

```bash
docker compose up -d
```

Open [http://localhost:8000](http://localhost:8000) and connect using your access key. Follow [Download a video](#download-a-video).

To stop the app and keep its files:

```bash
docker compose down
```

To update, run `docker compose pull`, then `docker compose up -d` again. Downloads and history are kept in the `archives` Docker volume; their configured retention period still applies.

**On another device on the same Wi-Fi:** keep the host computer and Docker running, then open `http://YOUR-COMPUTER-LAN-IP:8000` and use that same server address in the app. Allow port `8000` through the host's firewall if needed. Use HTTPS outside a trusted local network.

## Development

Start with [Get the project locally](#get-the-project-locally), or use the existing repository folder in Codespaces.

### Build your changes

After configuring `.env`, build and run the code in your checkout:

```bash
docker compose -f compose.yaml -f compose.build.yaml up --build -d
```

This uses the separate `:local` image and the same settings, port, and data volume. The first build can take several minutes. Use this command again after source changes; pulling the prebuilt image does not build your checkout.

### Run without Docker

On macOS or Linux, install Python 3.12+, Node.js 22+, and FFmpeg/FFprobe. Start in the repository folder. Use Docker on Windows.

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements-dev.txt
```

For a new setup only:

```bash
cp .env.example .env
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the generated key after `ARCHIVE_API_KEY=` in `.env`. Install the pinned Rust toolchain and Trunk, then build the frontend:

```bash
bash scripts/install-frontend.sh
```

```bash
bash scripts/build-frontend.sh
```

```bash
python -m uvicorn backend.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) and connect with your access key. Keep the terminal running; press **Ctrl+C** to stop.

For frontend reloads, leave Python running and open a second terminal in the repository folder:

```bash
cd frontend
```

```bash
NO_COLOR=true "$HOME/.cargo/bin/trunk" serve
```

Open [http://localhost:8080](http://localhost:8080), using that address in server settings. Trunk forwards API requests to Python on port 8000.

### Checks

From the repository root, with the Python virtual environment active and frontend tools installed:

```bash
python -m pytest -q
```

```bash
cargo fmt --manifest-path frontend/Cargo.toml -- --check
```

```bash
bash scripts/build-frontend.sh
```

GitHub Actions runs backend tests, builds the frontend, and builds and starts the Docker image on Intel/AMD and ARM runners. Successful runs on `main` publish the multi-platform image to GHCR. Tests simulate the media provider; passing CI does not verify live YouTube downloads.

## GitHub Codespaces (iPad)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/DisabledAbel/EasyYouTubeVideoDownloader)

### 1. Create your codespace

Use the button above, select `main` and a **2-core** machine, and create the codespace. Wait for the browser editor to load, then open its terminal. GitHub's default development environment includes Docker and Compose.

The button opens the setup page; it does not start the app automatically. Codespaces clones the repository for you, so skip the local clone steps. Run the commands below in the repository folder.

### 2. Create your access key

For a new setup, copy the settings file. **Keep your existing `.env` when resuming or updating.**

```bash
cp .env.example .env
```

Generate a random key:

```bash
docker run --rm python:3.12-slim-bookworm python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Open `.env` in the editor. Paste the generated key after `ARCHIVE_API_KEY=` and save. Leave the other settings at their defaults. Keep a private copy of the key for connecting to the app; do not commit `.env` or share the key publicly.

**This is your app's access key, not a Google password or YouTube login.**

### 3. Start the app

Use the prebuilt image so you do not need to compile Rust:

```bash
docker compose pull
```

```bash
docker compose up -d
```

To run changes you made to the source instead, use [Build your changes](#build-your-changes).

### 4. Open the app on your iPad

In the editor's **Ports** tab, forward port **8000**, keep its visibility **Private**, and select **Open in Browser**. Sign in to GitHub if prompted.

The app's address looks like `https://CODESPACENAME-8000.app.github.dev`. Under **Download server settings**, keep that address, enter your access key, and select **Connect server**. Do not use `localhost:8000` on your iPad—it would point to the iPad instead of the codespace. You do not need to change `ALLOWED_ORIGINS` for this setup.

Follow [Download a video](#download-a-video) below.

### Stop, resume, and update

When finished, open [your codespaces](https://github.com/codespaces), select the codespace's **…** menu, and choose **Stop codespace**. Closing a Safari tab does not immediately stop it.

Next time, resume the same codespace and reopen its forwarded port. If the app is not running:

```bash
docker compose up -d
```

To update the prebuilt app, run `docker compose pull`, then `docker compose up -d` again. These commands preserve your `.env` and download volume.

## Download a video

1. Open **Download server settings**, enter your access key, and select **Connect server**. Reconnect after reloading or reopening the page; the key is held only in memory.
2. Paste a link into **YouTube video link**.
3. Choose video or audio under **Save as**, and choose whether to include English captions.
4. Select **Download video** and watch its status under **Your downloads**.
5. When finished, select **Download media** for the video/audio alone, or **Download ZIP** for the media and extras. Save the file to your device.

The first button starts processing on the server. The **Download media** and **Download ZIP** buttons appear after processing finishes. Progress measures the current stream and can restart when audio or another processing stage begins.

## Optional YouTube cookies

Try a download first. If YouTube asks you to sign in, the app can import a **Netscape-format `cookies.txt` file containing only youtube.com cookies**. This file gives the server access to your YouTube session. It is separate from your app access key.

**There is no “Sign in with Google” button.** yt-dlp does not support YouTube OAuth login. The upload feature cannot export cookies from iPad Safari; it accepts an existing file from Files. Cookies may help with sign-in requirements, but they do not guarantee downloads from a cloud server.

1. On a supported desktop browser, follow [yt-dlp's YouTube cookie export guide](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies). Its [FAQ links cookie-export extensions](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp). Export only YouTube cookies, not your whole browser's cookies. If using an iPad, transfer the file privately to Files, for example with AirDrop from a Mac.
2. Connect to your download server, expand **Download server settings**, and select **Upload YouTube cookies.txt**. Choose the file (up to 64 KiB).
3. Submit the video link again. Use **Remove saved YouTube cookies** when finished, or upload a replacement if the session expires.

Treat the file like a password: never commit it, send it in chat, or place it in a public folder. Upload only to your own trusted server over HTTPS or localhost. Anyone with the app access key can replace or remove the shared session. yt-dlp warns that using an account can lead to temporary or permanent account restrictions.

Cookies are stored privately under `ARCHIVE_DATA_DIR/.credentials/`, outside download folders, and are never included in downloads. They survive restarts and are not deleted by download retention. Removing them affects future downloads; it does not stop an active download, revoke the session at Google, or delete the original file on your device.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| App will not open | Resume the codespace or start Docker, run `docker compose up -d`, and check the address. In Codespaces, use the forwarded HTTPS port 8000. |
| Download button is disabled | Connect under **Download server settings** first. |
| Access key is rejected | Use the value of `ARCHIVE_API_KEY` from your server's `.env`. It must be at least 24 characters. If you change it, run `docker compose up -d` to apply it. |
| `Temporary failure in name resolution` or `Failed to resolve` | The download server cannot resolve YouTube's address. Check its network/DNS and retry after connectivity is restored. Cookies or Google sign-in do not fix DNS. |
| `Sign in to confirm you're not a bot` | YouTube is rejecting the server's request. See [Optional YouTube cookies](#optional-youtube-cookies); a cloud server can still be blocked after adding cookies. |
| Download failed | Read the error under **Your downloads**. After addressing the cause, submit the link again to retry. |
| Download link expired | Select **Download media** or **Download ZIP** again to create a fresh link. |
| A saved download disappeared | Files expire after 24 hours by default. Save a copy to your device before retention removes it. |

For startup or server errors, view the logs:

```bash
docker compose logs --tail=100 archiver
```

## Configuration and limits

See [.env.example](.env.example) for settings. Docker Compose reads `.env`; when running Python directly, pass `--env-file .env` as shown in [Development](#development).

Default limits: **one active download**, five queued/running jobs, 20 records, two-hour source duration, 15-minute processing timeout, 512 MiB per download's contents, and 24-hour retention. ZIP files roughly double media storage; a full server at these defaults needs at least 20 GiB plus working space. Lower the limits for a small codespace; use a host-level disk quota for a strict storage boundary.

Run **one backend process and one replica per data directory**. The queue is not distributed. Interrupted downloads are marked failed and can be retried.

Only creator-provided English captions are supported. Automatic captions, playlists, live streams, DRM, and geographic restriction workarounds are not included. A download can fail if MP4-compatible formats are unavailable. YouTube can change its requirements; Dependabot proposes yt-dlp updates weekly.

## License

[GPL-3.0](LICENSE). Third-party components retain their own licenses.
