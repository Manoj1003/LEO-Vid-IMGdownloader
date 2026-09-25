"""Universal Downloader - runs on your own computer, saves to a folder you pick."""
import os, re, sys, shutil, threading, subprocess, uuid, webbrowser
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory
import yt_dlp

try:
    from gallery_dl import extractor as gdl_extractor
except Exception:
    gdl_extractor = None

HERE = Path(__file__).resolve().parent
DEFAULT_DIR = Path.home() / "Downloads" / "Downloader"
PORT = 8765
JOBS, INFO_CACHE, ITEMS_CACHE = {}, {}, {}
BROWSER_ORDER = ["firefox", "edge", "chrome", "brave", "opera"] + (["safari"] if sys.platform == "darwin" else [])
LOGIN_HOSTS = ("instagram.com", "x.com", "twitter.com", "facebook.com", "fb.watch", "threads.net")
LOGIN_RE = re.compile(r"log ?in|sign in|cookies|rate.?limit|private|authoriz|authent|age.?restrict|confirm your age|empty media|nsfw", re.I)
NO_MEDIA_RE = re.compile(r"no video (could be found|in this post)|there is no video|no media (found|in this post)|unsupported url", re.I)
COOKIE_FAIL_RE = re.compile(r"could not copy|decrypt|dpapi|cookie database|keyring|could not find|no such file", re.I)
LOGIN_HINT = " This site needs you to be logged in. Log in to it in your normal browser, then paste the link again."
COOKIE_HINT = " Your browser's login couldn't be read. Close Chrome/Edge completely (or log in with Firefox) and try again."
SPOTIFY_MSG = ("Spotify songs are DRM-protected, so this app can't download them. Use Spotify Premium's "
               "offline downloads, or paste a link from a site that allows downloads (SoundCloud, Bandcamp, your own uploads).")

app = Flask(__name__)


def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = find_ffmpeg()


def clean_name(s, n=80):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s or "").strip(" .")
    return s[:n] or "Downloads"


def clean_err(e):
    return re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")[:240]


def host_of(url):
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def is_spotify(url):
    h = host_of(url)
    return h.endswith("spotify.com") or h == "spotify.link"


def needs_login(url, err):
    if NO_MEDIA_RE.search(str(err)):
        return False  # the post is just missing that media type (e.g. a photo-only post) - not a login issue
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in LOGIN_HOSTS) or bool(LOGIN_RE.search(str(err)))


def images_supported(url):
    if not gdl_extractor:
        return False
    try:
        return gdl_extractor.find(url) is not None
    except Exception:
        return False


def _extract(url, browser):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True}
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("entries") is not None:
        items = []
        for e in info["entries"]:
            if not e:
                continue
            u = e.get("url") or e.get("webpage_url") or ""
            if not u.startswith("http"):
                u = f"https://www.youtube.com/watch?v={e.get('id')}"
            items.append({"url": u, "title": e.get("title") or e.get("id") or "Untitled"})
        return info.get("title") or "Playlist", items
    return info.get("title") or "Video", [{"url": info.get("webpage_url") or url, "title": info.get("title") or "Video"}]


def get_entries(url):
    """Returns (title, items, browser_used). Tries with no login first, then each browser's login only if needed."""
    if url in ITEMS_CACHE:
        return ITEMS_CACHE[url]
    try:
        res = (*_extract(url, ""), "")
    except Exception as first:
        if not needs_login(url, first):
            raise
        res, cookie_problem = None, False
        for b in BROWSER_ORDER:
            try:
                res = (*_extract(url, b), b)
                break
            except Exception as err:
                cookie_problem = cookie_problem or bool(COOKIE_FAIL_RE.search(str(err)))
        if not res:
            raise RuntimeError(clean_err(first) + (COOKIE_HINT if cookie_problem else LOGIN_HINT)) from None
    ITEMS_CACHE[url] = res
    return res


def probe(url):
    if url in INFO_CACHE:
        return INFO_CACHE[url]
    video_ok, title, count, err, browser = False, None, 0, "", ""
    try:
        title, items, browser = get_entries(url)
        video_ok, count = True, len(items)
    except Exception as e:
        err = clean_err(e)
    images_ok = images_supported(url)
    if not video_ok and not images_ok:
        raise RuntimeError(err or "This link isn't supported.")
    if not title:
        title = clean_name(f"{host_of(url)} {Path(urlparse(url).path).name}")
    note = err if (not video_ok and needs_login(url, err)) else ""
    res = dict(title=title, count=count, video_ok=video_ok, images_ok=images_ok, note=note, browser=browser)
    if not note:
        INFO_CACHE[url] = res
    return res


def make_opts(fmt, outdir, idx, job, label):
    def hook(d):
        if job["cancel"]:
            raise yt_dlp.utils.DownloadCancelled("cancelled")
        info = d.get("info_dict") or {}
        est = sum((x.get("filesize") or x.get("filesize_approx") or 0) for x in (info.get("requested_formats") or [info]))
        got = d.get("downloaded_bytes") or 0
        tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        if d["status"] == "finished":
            got = tot = d.get("total_bytes") or got
            job["phase"] = "processing"
        else:
            job["phase"] = "downloading"
            job["speed_bps"] = d.get("speed") or 0
        job["_streams"][d.get("filename")] = (got, tot)
        job["cur_done"] = sum(v[0] for v in job["_streams"].values())
        job["cur_total"] = max(est, sum(v[1] for v in job["_streams"].values()))

    o = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "retries": 5, "fragment_retries": 5, "concurrent_fragment_downloads": 4,
        "windowsfilenames": True, "progress_hooks": [hook],
        "outtmpl": str(outdir / f"{idx:03d} - %(title).100s [{label}].%(ext)s"),
    }
    if job["browser"]:
        o["cookiesfrombrowser"] = (job["browser"],)
    if FFMPEG:
        o["ffmpeg_location"] = FFMPEG
    if fmt == "mp3":
        if not FFMPEG:
            raise RuntimeError("ffmpeg is needed for MP3. Run start.bat / start.sh again.")
        o["format"] = "bestaudio/best"
        o["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    elif FFMPEG:
        # video capped at the chosen height (unknown heights allowed) + best audio => MP4 always has sound
        o["format"] = f"bv*[height<=?{fmt}]+ba/b[height<=?{fmt}]/wv*+ba/w"
        o["format_sort"] = ["res", "vcodec:h264", "acodec:aac"]
        o["merge_output_format"] = "mp4"
    else:
        o["format"] = f"b[height<=?{fmt}][ext=mp4]/b[height<=?{fmt}]/w"
    return o


def gallery_pass(job, outdir, browser):
    """One gallery-dl run. Returns the error lines it printed."""
    cmd = [sys.executable, "-m", "gallery_dl", "-D", str(outdir), "--no-part"]
    if browser:
        cmd += ["--cookies-from-browser", browser]
    cmd.append(job["url"])
    errors = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    job["_proc"] = proc
    for line in proc.stdout:
        line = line.strip()
        if job["cancel"]:
            proc.terminate()
            break
        if line.startswith("#"):
            continue
        if "[error]" in line or "Error" in line[:40]:
            errors.append(line)
        elif line and os.path.isfile(line):
            job["images"] += 1
            job["cur_done"] += os.path.getsize(line)
    proc.wait()
    job["_proc"] = None
    return errors


def run_images(job, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    job.update(current="Images and photos", cur_done=0, cur_total=0, speed_bps=0, phase="images", _streams={})
    errs = gallery_pass(job, outdir, job["browser"])
    retried = False
    if not job["images"] and not job["cancel"] and needs_login(job["url"], " ".join(errs)):
        retried = True
        for b in BROWSER_ORDER:
            if job["cancel"] or job["images"]:
                break
            gallery_pass(job, outdir, b)
    if job["images"]:
        job["ok"] += 1
        job["bytes_done"] += job["cur_done"]
    elif not job["cancel"]:
        msg = clean_err(errs[-1]) if errs else "No images were found at this link."
        job["failed"].append({"title": "Images", "format": "images", "error": msg + (LOGIN_HINT if retried else "")})
    job["done"] += 1


def run_job(job):
    vfmts = [f for f in job["formats"] if f != "images"]
    want_images = "images" in job["formats"]
    try:
        p = probe(job["url"])
        job["browser"] = p["browser"]
        items = get_entries(job["url"])[1] if (vfmts and p["video_ok"]) else []
    except Exception as e:
        job.update(state="error", error=clean_err(e))
        return
    if not items and not want_images:
        job.update(state="error", error="No video or audio was found at this link.")
        return
    root = Path(job["folder"])
    job["path"] = str(root)
    tasks = [(i, it, f) for i, it in enumerate(items, 1) for f in vfmts]
    job["total"], job["state"] = len(tasks) + (1 if want_images else 0), "running"
    job["_fmts"] = [f for _, _, f in tasks]
    for i, it, f in tasks:
        if job["cancel"]:
            break
        label = "MP3" if f == "mp3" else f"{f}p"
        job.update(current=f"{i}. {it['title']}  [{label}]", cur_done=0, cur_total=0, speed_bps=0, phase="downloading", _streams={})
        try:
            with yt_dlp.YoutubeDL(make_opts(f, root, i, job, label)) as ydl:
                ydl.download([it["url"]])
            job["ok"] += 1
            job["bytes_done"] += job["cur_done"]
            st = job["_stats"].setdefault(f, [0, 0])
            st[0] += job["cur_done"]
            st[1] += 1
        except yt_dlp.utils.DownloadCancelled:
            break
        except Exception as e:
            job["failed"].append({"title": it["title"], "format": label, "error": clean_err(e)})
        job["done"] += 1
    if want_images and not job["cancel"]:
        try:
            run_images(job, root)
        except Exception as e:
            job["failed"].append({"title": "Images", "format": "images", "error": clean_err(e)})
    job["state"] = "cancelled" if job["cancel"] else "done"


def pick_folder():
    code = (
        "import tkinter as tk\nfrom tkinter import filedialog\n"
        "r=tk.Tk(); r.withdraw(); r.attributes('-topmost', True); r.lift(); r.focus_force()\n"
        "p=filedialog.askdirectory(parent=r, title='Choose where to save your downloads')\n"
        "print('PICKED:' + (p or ''))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    for line in reversed(r.stdout.splitlines()):
        if line.startswith("PICKED:"):
            return line[7:].strip()
    raise RuntimeError(r.stderr[-200:] or "no folder window")


def estimate(job):
    st = job["_stats"]
    known = [b / c for b, c in st.values() if c]
    fallback = sum(known) / len(known) if known else 0
    rest = 0
    for f in job["_fmts"][job["done"] + 1:]:
        b, c = st.get(f, [0, 0])
        rest += (b / c) if c else fallback
    got = job["bytes_done"] + job["cur_done"]
    total = job["bytes_done"] + max(job["cur_total"], job["cur_done"]) + rest
    return int(got), int(max(total, got))


@app.post("/api/pick-folder")
def pick():
    try:
        p = pick_folder()
    except Exception:
        return jsonify(path=str(DEFAULT_DIR), fallback=True, cancelled=False)
    return jsonify(path=p, fallback=False, cancelled=not p)


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.get("/api/config")
def config():
    return jsonify(ffmpeg=bool(FFMPEG), images=bool(gdl_extractor))


@app.post("/api/info")
def info():
    b = request.json or {}
    url = b.get("url", "").strip()
    if is_spotify(url):
        return jsonify(error=SPOTIFY_MSG), 400
    try:
        return jsonify(probe(url))
    except Exception as e:
        return jsonify(error="Couldn't read that link. " + clean_err(e)), 400


@app.post("/api/start")
def start():
    b = request.json or {}
    url = b.get("url", "").strip()
    if is_spotify(url):
        return jsonify(error=SPOTIFY_MSG), 400
    valid = {"mp3", "1080", "720", "480", "360", "240", "144", "images"}
    formats = [f for f in b.get("formats", []) if f in valid]
    if not url or not formats:
        return jsonify(error="Paste a link and choose at least one format."), 400
    folder = Path(os.path.expanduser(b.get("folder") or str(DEFAULT_DIR)))
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        return jsonify(error="That save folder can't be created. Pick another one."), 400
    jid = uuid.uuid4().hex[:8]
    job = dict(id=jid, url=url, formats=formats, folder=str(folder), browser="",
               state="preparing", cancel=False, total=0, done=0, ok=0, images=0, current="", failed=[],
               path="", error="", cur_done=0, cur_total=0, speed_bps=0, bytes_done=0, phase="",
               _streams={}, _stats={}, _fmts=[], _proc=None)
    JOBS[jid] = job
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return jsonify(id=jid)


@app.get("/api/status/<jid>")
def status(jid):
    job = JOBS.get(jid)
    if not job:
        return jsonify(error="Unknown job"), 404
    out = {k: v for k, v in job.items() if k not in ("url", "cancel", "browser") and not k.startswith("_")}
    got, total = estimate(job)
    sp = job["speed_bps"] or 0
    out.update(got=got, total_est=total, eta=int((total - got) / sp) if sp and total > got else None)
    return jsonify(out)


@app.post("/api/cancel/<jid>")
def cancel(jid):
    job = JOBS.get(jid)
    if job:
        job["cancel"] = True
        if job.get("_proc"):
            try:
                job["_proc"].terminate()
            except Exception:
                pass
    return jsonify(ok=True)


@app.post("/api/open/<jid>")
def open_folder(jid):
    job = JOBS.get(jid)
    p = (job or {}).get("path") or (job or {}).get("folder")
    if not p or not os.path.isdir(p):
        return jsonify(error="Folder not found"), 404
    if sys.platform.startswith("win"):
        os.startfile(p)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])
    return jsonify(ok=True)


if __name__ == "__main__":
    print(f"\n  Downloader is running at http://127.0.0.1:{PORT}\n  Keep this window open. Press Ctrl+C to stop.\n")
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, threaded=True)
