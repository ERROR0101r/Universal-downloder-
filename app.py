from flask import Flask, request, jsonify, Response
import requests
import re
import html
import traceback

app = Flask(__name__)

USER_AGENT = "Mozilla/5.0"
REQUEST_TIMEOUT = 10  # seconds

# attribution / credit
CREDIT = "full credit"
DEV_HANDLE = "t.me/anshapi"


def json_response(obj, status=200):
    """
    Wrap jsonify but automatically inject 'credit' and 'dev' fields
    into dict responses (unless already present).
    """
    try:
        if isinstance(obj, dict):
            # do not overwrite if user already supplied these keys
            if "credit" not in obj:
                obj["credit"] = CREDIT
            if "dev" not in obj:
                obj["dev"] = DEV_HANDLE
        resp = jsonify(obj)
        resp.status_code = status
        return resp
    except Exception:
        # fallback safe response
        resp = jsonify({"error": "internal json error", "credit": CREDIT, "dev": DEV_HANDLE})
        resp.status_code = 500
        return resp


def sanitize_title(t: str) -> str:
    t = re.sub(r'[\n\r]+', ' ', t).strip()
    # remove filesystem illegal chars similar to your JS
    return re.sub(r'[\\\/:*?"<>|]', '', t)


def process_url(video_url: str):
    try:
        search_resp = requests.get(
            "https://www.videofk.com/search",
            params={"url": video_url},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        html_text = search_resp.text or ""
        title = "media_download"
        m = re.search(r"<title>(.*?)</title>", html_text, re.I | re.S)
        if m:
            title = sanitize_title(html.unescape(m.group(1)))

        # find href="...#url=ENC..." and capture both full href and encoded part
        encrypted_links = []
        for m in re.finditer(r'href="([^"]*#url=([^"]+))"', html_text, re.I):
            href_full = m.group(1)
            enc = m.group(2)
            encrypted_links.append({"encrypted": enc, "text": href_full.lower()})

        if len(encrypted_links) == 0:
            return {"error": "Download links not found"}

        media_items = []
        best_video = {"size": 0, "url": None, "quality": "unknown", "title": title}
        best_audio = {"url": None, "bitrate": "unknown", "title": title}
        no_watermark = None

        for item in encrypted_links:
            # call the decryptor endpoint from your worker
            try:
                dec_resp = requests.get(
                    "https://downloader.twdown.online/load_url",
                    params={"url": item["encrypted"]},
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )
                final = (dec_resp.text or "").strip()
            except Exception:
                final = ""

            if not final.startswith("http"):
                # skip non-http responses
                continue

            is_audio = re.search(r"mp3|m4a|aac|kbps|audio", item["text"], re.I) is not None
            q_match = re.search(r"(\d+p|\d+kbps)", item["text"])
            quality = q_match.group(1) if q_match else "unknown"

            if is_audio:
                if not best_audio["url"]:
                    best_audio = {"url": final, "bitrate": quality, "title": title}
                media_items.append({"type": "audio", "url": final, "quality": quality})
                continue

            # attempt HEAD to get size
            size = 0
            try:
                head = requests.head(final, allow_redirects=True, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
                size = int(head.headers.get("content-length") or 0)
            except Exception:
                size = 0

            if re.search(r"no watermark|without water", item["text"], re.I):
                no_watermark = {"url": final, "size": size, "quality": quality, "title": title}

            if size > best_video["size"]:
                best_video = {"url": final, "size": size, "quality": quality, "title": title}

            media_items.append({"type": "video", "url": final, "quality": quality, "size": size})

        out = {
            "success": True,
            "title": title,
            "original_url": video_url,
            "formats": len(media_items),
            "media": media_items,
        }

        if no_watermark:
            out["video_no_watermark"] = no_watermark
        elif best_video["url"]:
            out["video_best"] = best_video

        if best_audio["url"]:
            out["audio_best"] = best_audio

        return out

    except Exception as e:
        # include limited error info
        return {"error": "unexpected: " + str(e)}


# CORS + developer header
@app.after_request
def add_cors_headers(response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    # include developer on every response header
    response.headers["X-Developer"] = DEV_HANDLE
    # for preflight CORS
    response.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type,Authorization")
    return response


@app.route("/", methods=["GET", "OPTIONS"])
def root():
    return json_response({
        "endpoints": {
            "/download?url=": "Full result + links",
            "/info?url=": "Only information",
            "/direct/{type}?url=": "Decrypt encrypted URL"
        }
    })


@app.route("/download", methods=["GET", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return json_response({"success": True})
    link = request.args.get("url")
    if not link:
        return json_response({"error": "url missing"}, 400)
    result = process_url(link)
    if result.get("error"):
        return json_response(result, 400)
    return json_response(result)


@app.route("/info", methods=["GET", "OPTIONS"])
def info():
    if request.method == "OPTIONS":
        return json_response({"success": True})
    link = request.args.get("url")
    if not link:
        return json_response({"error": "url missing"}, 400)
    r = process_url(link)
    if r.get("error"):
        return json_response(r, 400)

    has_video = bool((r.get("video_best") and r["video_best"].get("url")) or r.get("video_no_watermark"))
    has_audio = bool(r.get("audio_best") and r["audio_best"].get("url"))
    qualities = list({v.get("quality", "unknown") for v in r.get("media", [])})

    return json_response({
        "success": True,
        "title": r.get("title"),
        "formats": r.get("formats"),
        "has_video": has_video,
        "has_audio": has_audio,
        "qualities": qualities
    })


@app.route("/direct/<typ>", methods=["GET", "OPTIONS"])
def direct(typ):
    if request.method == "OPTIONS":
        return json_response({"success": True})
    encrypted = request.args.get("url")
    if not encrypted:
        return json_response({"error": "encrypted url missing"}, 400)

    try:
        a = requests.get(
            "https://downloader.twdown.online/load_url",
            params={"url": encrypted},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        res = (a.text or "").strip()
    except Exception:
        res = ""

    if not res.startswith("http"):
        return json_response({"error": "decrypt failed"}, 400)

    return json_response({"success": True, "direct_url": res})


if __name__ == "__main__":
    # For local testing only. Use gunicorn/uvicorn for production.
    app.run(host="0.0.0.0", port=8080, debug=False)