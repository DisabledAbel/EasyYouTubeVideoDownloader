use gloo_net::http::Request;
use gloo_timers::callback::Interval;
use leptos::{mount::mount_to_body, prelude::*, task::spawn_local};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Clone, Deserialize)]
struct Job {
    id: String,
    video_id: String,
    url: String,
    kind: String,
    status: String,
    progress: u32,
    title: String,
    error: String,
}

async fn api(
    base: &str,
    key: &str,
    method: &str,
    path: &str,
    body: Option<Value>,
) -> Result<Value, String> {
    let url = format!("{base}{path}");
    let builder = match method {
        "POST" => Request::post(&url),
        "DELETE" => Request::delete(&url),
        _ => Request::get(&url),
    }
    .header("Authorization", &format!("Bearer {key}"));
    let request = if let Some(body) = body {
        builder.json(&body).map_err(|e| e.to_string())?
    } else {
        builder.build().map_err(|e| e.to_string())?
    };
    let response = request.send().await.map_err(|_| {
        "Cannot reach the download server. Check its address, HTTPS, and allowed origins."
            .to_string()
    })?;
    let status = response.status();
    if !(200..300).contains(&status) {
        let detail = response
            .json::<Value>()
            .await
            .ok()
            .and_then(|value| value["detail"].as_str().map(str::to_string));
        return Err(detail.unwrap_or_else(|| {
            format!("The server could not process this request (HTTP {status}).")
        }));
    }
    response.json().await.map_err(|_| {
        "This address did not return the download API. Check your server address.".to_string()
    })
}

async fn fetch_jobs(base: String, key: String, jobs: RwSignal<Vec<Job>>) -> Result<(), String> {
    let data = api(&base, &key, "GET", "/api/jobs", None).await?;
    jobs.set(serde_json::from_value(data).map_err(|_| "Unexpected server response.".to_string())?);
    Ok(())
}

#[component]
fn App() -> impl IntoView {
    let origin = web_sys::window()
        .unwrap()
        .location()
        .origin()
        .unwrap_or_default();
    let configured = option_env!("ARCHIVE_API_URL").unwrap_or("");
    let endpoint = RwSignal::new(if configured.is_empty() {
        origin
    } else {
        configured.to_string()
    });
    let theme = RwSignal::new(
        web_sys::window()
            .and_then(|window| window.local_storage().ok().flatten())
            .and_then(|storage| storage.get_item("download-theme").ok().flatten())
            .filter(|value| matches!(value.as_str(), "system" | "light" | "dark"))
            .unwrap_or_else(|| "system".into()),
    );
    Effect::new(move |_| {
        let value = theme.get();
        if let Some(window) = web_sys::window() {
            if let Some(root) = window
                .document()
                .and_then(|document| document.document_element())
            {
                let _ = root.set_attribute("data-theme", &value);
            }
            // Appearance remains usable when browser storage is unavailable.
            if let Ok(Some(storage)) = window.local_storage() {
                let _ = storage.set_item("download-theme", &value);
            }
        }
    });
    let access_key = RwSignal::new(String::new());
    // Active connection is separate from editable settings, avoiding requests to half-edited URLs.
    let connection = RwSignal::new(None::<(String, String)>);
    let jobs = RwSignal::new(Vec::<Job>::new());
    let url = RwSignal::new(String::new());
    let kind = RwSignal::new("video".to_string());
    let captions = RwSignal::new(true);
    let busy = RwSignal::new(false);
    let error = RwSignal::new(String::new());
    let notice = RwSignal::new(String::new());
    let poll_error = RwSignal::new(String::new());

    Effect::new(move |_| {
        if let Some((base, key)) = connection.get() {
            let interval = Interval::new(2000, move || {
                let (base, key) = (base.clone(), key.clone());
                spawn_local(async move {
                    match fetch_jobs(base, key, jobs).await {
                        Ok(()) => poll_error.set(String::new()),
                        Err(message) => poll_error.set(message),
                    }
                });
            });
            let interval = send_wrapper::SendWrapper::new(interval);
            on_cleanup(move || drop(interval));
        }
    });

    let connect = move |event: web_sys::SubmitEvent| {
        event.prevent_default();
        if busy.get_untracked() {
            return;
        }
        error.set(String::new());
        notice.set(String::new());
        let base = endpoint
            .get_untracked()
            .trim()
            .trim_end_matches('/')
            .to_string();
        let parsed = match web_sys::Url::new(&base) {
            Ok(value)
                if matches!(value.protocol().as_str(), "https:" | "http:")
                    && value.username().is_empty()
                    && value.password().is_empty()
                    && value.pathname() == "/"
                    && value.search().is_empty()
                    && value.hash().is_empty() =>
            {
                value
            }
            _ => {
                error.set(
                    "Enter a server origin such as https://downloads.example.com, without a path."
                        .into(),
                );
                return;
            }
        };
        if web_sys::window()
            .unwrap()
            .location()
            .protocol()
            .unwrap_or_default()
            == "https:"
            && parsed.protocol() != "https:"
        {
            error.set("This HTTPS website needs an HTTPS download server. For local use, open the local website instead.".into());
            return;
        }
        let key = access_key.get_untracked();
        busy.set(true);
        spawn_local(async move {
            match fetch_jobs(base.clone(), key.clone(), jobs).await {
                Ok(()) => {
                    connection.set(Some((base, key)));
                    poll_error.set(String::new());
                    notice.set("Connected. Your downloads are ready.".into());
                }
                Err(message) => error.set(message),
            }
            busy.set(false);
        });
    };

    let start_download = move |event: web_sys::SubmitEvent| {
        event.prevent_default();
        if busy.get_untracked() {
            return;
        }
        let Some((base, key)) = connection.get_untracked() else {
            return;
        };
        let body = json!({"url": url.get_untracked(), "kind": kind.get_untracked(), "captions": captions.get_untracked()});
        busy.set(true);
        error.set(String::new());
        notice.set(String::new());
        spawn_local(async move {
            match api(&base, &key, "POST", "/api/jobs", Some(body)).await {
                Ok(data) => {
                    notice.set(
                        if data["duplicate"] == true {
                            "This video is already in your downloads."
                        } else {
                            "Added to the download queue."
                        }
                        .into(),
                    );
                    url.set(String::new());
                    if let Err(message) = fetch_jobs(base, key, jobs).await {
                        error.set(message);
                    }
                }
                Err(message) => error.set(message),
            }
            busy.set(false);
        });
    };

    view! {
        <div class="page">
            <header>
                <a class="brand" href="/" aria-label="Easy YouTube Video Downloader home">
                    <span class="brand-mark" aria-hidden="true">"↧"</span>
                    <span>"Easy YouTube"<br/><strong>"Video Downloader"</strong></span>
                </a>
                <div class="header-controls">
                <label class="theme-control" for="theme">"Appearance"
                    <select id="theme" prop:value=move || theme.get()
                        on:change=move |event| theme.set(event_target_value(&event))>
                        <option value="system">"System"</option>
                        <option value="light">"Light"</option>
                        <option value="dark">"Dark"</option>
                    </select>
                </label>
                <span class="connection"><span class:online=move || connection.get().is_some()></span>
                    {move || if connection.get().is_some() { "Server connected" } else { "Connect your server" }}
                </span>
                </div>
            </header>
            <main>
                <section class="hero">
                    <p class="eyebrow">"A LITTLE LESS TEMPORARY"</p>
                    <h1>"Keep the videos"<br/><em>"worth keeping."</em></h1>
                    <p class="intro">"Save a video. Preserve its story. An uncomplicated home for the recordings you want to hold on to."</p>
                </section>
                <section class="download-panel" aria-labelledby="download-heading">
                    <div class="panel-heading"><h2 id="download-heading">"Start a download"</h2><span>"01 / ADD A VIDEO"</span></div>
                    <form on:submit=start_download>
                        <label for="video-url">"YouTube video link"</label>
                        <div class="url-row">
                            <input id="video-url" type="url" placeholder="https://www.youtube.com/watch?v=…" required
                                prop:value=move || url.get() on:input=move |e| url.set(event_target_value(&e))/>
                            <button class="primary" type="submit" disabled=move || busy.get() || connection.get().is_none()>
                                {move || if busy.get() { "Please wait…" } else { "Download video ↗" }}
                            </button>
                        </div>
                        <div class="options">
                            <label class="format" for="format">"Save as"
                                <select id="format" on:change=move |e| kind.set(event_target_value(&e))>
                                    <option value="video">"Video · MP4 · up to 1080p"</option>
                                    <option value="audio">"Audio only · M4A"</option>
                                </select>
                            </label>
                            <label class="check"><input type="checkbox" prop:checked=move || captions.get()
                                on:change=move |e| captions.set(event_target_checked(&e))/><span>"Include English captions when available"</span></label>
                        </div>
                    </form>
                    <p class="panel-note">"Every download includes the source link, description, metadata, and download date."</p>
                </section>
                <div class="messages" aria-live="polite">
                    <Show when=move || !error.get().is_empty()><p class="error" role="alert">{move || error.get()}</p></Show>
                    <Show when=move || !notice.get().is_empty()><p class="notice">{move || notice.get()}</p></Show>
                    <Show when=move || !poll_error.get().is_empty()><p class="error">{move || poll_error.get()}</p></Show>
                </div>
                <section class="library" aria-labelledby="library-heading">
                    <div class="section-heading"><h2 id="library-heading">"Your downloads"</h2><span>{move || format!("{:02} recordings", jobs.get().len())}</span></div>
                    <Show when=move || jobs.get().is_empty()>
                        <div class="empty"><span aria-hidden="true">"▤"</span><h3>"Good things deserve a place."</h3><p>"Your saved recordings will appear here."</p></div>
                    </Show>
                    <div class="job-list">
                        <For each=move || jobs.get() key=|job| format!("{}:{}:{}:{}:{}", job.id, job.status, job.progress, job.title, job.error)
                            children=move |job| view! { <JobCard job connection jobs error/> }/>
                    </div>
                    <p class="retention">"Server files expire after 24 hours by default. Download your copies for long-term preservation."</p>
                </section>
                <details class="server" open=move || connection.get().is_none()>
                    <summary>"Download server settings"</summary>
                    <p>"Connect to your local server or a hosted HTTPS server. Your access key stays in memory until this page closes."</p>
                    <form on:submit=connect>
                        <label for="server-url">"Server address"<input id="server-url" type="url" required prop:value=move || endpoint.get()
                            on:input=move |e| endpoint.set(event_target_value(&e))/></label>
                        <label for="access-key">"Access key"<input id="access-key" type="password" required autocomplete="off" prop:value=move || access_key.get()
                            on:input=move |e| access_key.set(event_target_value(&e))/></label>
                        <button class="secondary" type="submit" disabled=move || busy.get()>"Connect server"</button>
                    </form>
                    <Show when=move || connection.get().is_some()>
                        <button class="text-button" on:click=move |_| {connection.set(None); jobs.set(vec![]); access_key.set(String::new()); notice.set(String::new());}>"Disconnect and clear key"</button>
                    </Show>
                </details>
            </main>
            <footer><span>"Made for keeping."</span><p>"Download public-domain videos and videos you have permission to download. Copyright status is not automatically verified."</p></footer>
        </div>
    }
}

#[component]
fn JobCard(
    job: Job,
    connection: RwSignal<Option<(String, String)>>,
    jobs: RwSignal<Vec<Job>>,
    error: RwSignal<String>,
) -> impl IntoView {
    let id = job.id.clone();
    let id2 = job.id.clone();
    let id3 = job.id.clone();
    let ready = job.status == "ready";
    let deletable = matches!(job.status.as_str(), "ready" | "failed");
    let status = match job.status.as_str() {
        "ready" => "Ready to save".to_string(),
        "queued" => "In the queue".to_string(),
        "downloading" => format!("Downloading · {}% of current stream", job.progress),
        _ => "Download failed".to_string(),
    };
    let title = if job.title.is_empty() {
        format!("YouTube · {}", job.video_id)
    } else {
        job.title
    };
    let has_error = !job.error.is_empty();
    let download = move |id: String, artifact: &str| {
        let Some((base, key)) = connection.get_untracked() else {
            return;
        };
        let path = format!("/api/jobs/{id}/ticket?artifact={artifact}");
        spawn_local(async move {
            match api(&base, &key, "POST", &path, None).await {
                Ok(data) => {
                    if let Some(path) = data["path"].as_str() {
                        if let Err(_) = web_sys::window()
                            .unwrap()
                            .location()
                            .set_href(&format!("{base}{path}"))
                        {
                            error.set("Could not open the download link.".into());
                        }
                    }
                }
                Err(message) => error.set(message),
            }
        });
    };
    view! {
        <article class="job">
            <div class="file-icon" aria-hidden="true">{if job.kind == "audio" { "♫" } else { "▷" }}</div>
            <div class="job-info"><span class="job-status" class:ready=ready>{status}</span><h3>{title}</h3>
                <a href=job.url target="_blank" rel="noopener noreferrer">"View original ↗"</a>
                <Show when=move || has_error><p class="error">{job.error.clone()}</p></Show>
            </div>
            <div class="job-actions">
                <Show when=move || ready>
                    <button class="secondary" on:click={let id=id.clone(); move |_| download(id.clone(), "media")}>"Download media ↓"</button>
                    <button class="text-button" on:click={let id=id2.clone(); move |_| download(id.clone(), "bundle")}>"Download ZIP ↓"</button>
                </Show>
                <Show when=move || deletable>
                    <button class="text-button delete" on:click={let id=id3.clone(); move |_| {
                        let Some((base, key)) = connection.get_untracked() else { return; };
                        let id = id.clone();
                        spawn_local(async move {
                            match api(&base, &key, "DELETE", &format!("/api/jobs/{id}"), None).await {
                                Ok(_) => { if let Err(message) = fetch_jobs(base, key, jobs).await { error.set(message); } }
                                Err(message) => error.set(message),
                            }
                        });
                    }}>"Remove"</button>
                </Show>
            </div>
        </article>
    }
}

fn main() {
    console_error_panic_hook::set_once();
    mount_to_body(App);
}
