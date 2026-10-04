"""Audio & video tools on ffmpeg: convert, compress to a target size, trim, reframe to any aspect ratio."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .registry import AUDIO, VIDEO, Result, ToolError, fmt_size, for_each, num, out_path, run, target_bytes, tool

LONG = 3600


def probe(path: Path) -> dict:
    proc = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise ToolError(f"{path.name} is not a readable media file.")
    data = json.loads(proc.stdout or "{}")
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    dur = float(data.get("format", {}).get("duration") or (v or a or {}).get("duration") or 0)
    return {"duration": dur, "video": v, "audio": a,
            "width": int(v["width"]) if v else 0, "height": int(v["height"]) if v else 0}


def ffmpeg(args: list[str], timeout: int = LONG) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], timeout=timeout)


def ts(value: str) -> float | None:
    """'90', '1:30', '00:01:30.5' -> seconds."""
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"[\d:.]+", value):
        raise ToolError(f"Time '{value}' should look like 1:30 or 90")
    sec = 0.0
    for part in value.split(":"):
        sec = sec * 60 + float(part or 0)
    return sec


VCODEC = {
    "mp4": ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k"],
    "mov": ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k"],
    "mkv": ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-b:a", "160k"],
    "webm": ["-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "4", "-row-mt", "1", "-b:v", "0", "-crf", "36",
             "-c:a", "libopus", "-b:a", "96k"],
    "avi": ["-c:v", "mpeg4", "-q:v", "4", "-c:a", "libmp3lame", "-b:a", "160k"],
}
ACODEC = {
    "mp3": ["-c:a", "libmp3lame"], "m4a": ["-c:a", "aac"], "aac": ["-c:a", "aac"], "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"], "ogg": ["-c:a", "libvorbis"], "opus": ["-c:a", "libopus"],
}


def even(n: float) -> int:
    return max(2, int(round(n / 2)) * 2)


@tool(
    id="convert-video", name="Convert video", category="media", glyph="film", popular=True,
    description="MP4, MOV, MKV, WebM, AVI — re-encode for any player or platform.",
    keywords="mov to mp4 webm mkv avi format",
    accept=VIDEO, multiple=True,
    options=[{"name": "format", "label": "Convert to", "type": "segmented", "default": "mp4",
              "choices": [["mp4", "MP4"], ["webm", "WebM"], ["mov", "MOV"], ["mkv", "MKV"], ["avi", "AVI"]]}],
)
def convert_video(files, opts, work):
    fmt = opts.get("format") if opts.get("format") in VCODEC else "mp4"

    def one(f):
        dest = out_path(work, f, f".{fmt}")
        if dest.suffix == f.suffix.lower():
            dest = out_path(work, f, f".{fmt}", "converted")
        ffmpeg(["-i", str(f), *VCODEC[fmt], str(dest)])
        return dest

    return for_each(files, work, one, "videos.zip")


@tool(
    id="compress-video", name="Compress video", category="media", glyph="compress", popular=True,
    description="Shrink by quality level or to an exact size like 16 MB for WhatsApp or 25 MB for email.",
    keywords="reduce mb whatsapp email smaller target size",
    accept=VIDEO,
    options=[
        {"name": "mode", "label": "Mode", "type": "segmented", "default": "size",
         "choices": [["size", "Target size"], ["quality", "Quality level"]]},
        {"name": "target", "label": "Target size", "type": "number", "min": 0.5, "default": 16, "half": True, "when": {"mode": "size"}},
        {"name": "unit", "label": "Unit", "type": "segmented", "default": "mb", "half": True,
         "choices": [["kb", "KB"], ["mb", "MB"]], "when": {"mode": "size"}},
        {"name": "crf", "label": "Quality", "type": "cards", "default": "28", "when": {"mode": "quality"}, "choices": [
            ["23", "High", "Visually close to the original"], ["28", "Balanced", "Good for sharing"],
            ["33", "Small", "Noticeably softer, much smaller"]]},
        {"name": "res", "label": "Max resolution", "type": "segmented", "default": "keep",
         "choices": [["keep", "Keep"], ["1080", "1080p"], ["720", "720p"], ["480", "480p"]]},
    ],
)
def compress_video(files, opts, work):
    f = files[0]
    info = probe(f)
    vf = []
    res = opts.get("res", "keep")
    if res != "keep" and info["height"]:
        vf = ["-vf", f"scale=-2:'min({int(res)},ih)'" if info["height"] <= info["width"] else f"scale='min({int(res)},iw)':-2"]
    dest = out_path(work, f, ".mp4", "compressed")
    base = ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    meta = {}
    if opts.get("mode") == "quality":
        crf = opts.get("crf") if opts.get("crf") in ("23", "28", "33") else "28"
        ffmpeg(["-i", str(f), *vf, *base, "-crf", crf, "-c:a", "aac", "-b:a", "128k", str(dest)])
    else:
        goal = target_bytes(opts)
        if goal <= 0 or not info["duration"]:
            raise ToolError("Enter a target size (and use a file with a known duration).")
        audio_k = 64 if info["audio"] else 0
        total_k = goal * 8 / 1024 / info["duration"] * 0.90
        video_k = int(total_k - audio_k)
        if video_k < 40:
            raise ToolError(f"{fmt_size(goal)} is too small for a {info['duration']:.0f}-second video.")
        if not vf and info["height"]:
            # pick a sensible resolution for the bitrate budget
            cap = 1080 if video_k > 2500 else 720 if video_k > 900 else 480 if video_k > 350 else 360
            short = min(info["width"], info["height"])
            if short > cap:
                vf = ["-vf", f"scale=-2:{cap}" if info["height"] <= info["width"] else f"scale={cap}:-2"]
        common = ["-i", str(f), *vf, *base, "-b:v", f"{video_k}k", "-maxrate", f"{int(video_k * 1.4)}k",
                  "-bufsize", f"{video_k * 2}k"]
        log = str(work / "x264pass")
        ffmpeg([*common, "-pass", "1", "-passlogfile", log, "-an", "-f", "null", "/dev/null"])
        ffmpeg([*common, "-pass", "2", "-passlogfile", log,
                *(["-c:a", "aac", "-b:a", f"{audio_k}k"] if audio_k else ["-an"]), str(dest)])
        meta = {"target-met": "1" if dest.stat().st_size <= goal else "0",
                "note": f"{fmt_size(dest.stat().st_size)} at ~{video_k} kbps"}
    return Result("file", dest, original_size=f.stat().st_size, meta=meta)


@tool(
    id="trim-media", name="Trim audio / video", category="media", glyph="scissors",
    description="Cut a clip between two timestamps — frame-accurate or instant.",
    keywords="cut clip shorten",
    accept=VIDEO + AUDIO,
    options=[
        {"name": "start", "label": "Start", "type": "text", "default": "0:00", "placeholder": "0:00", "half": True},
        {"name": "end", "label": "End", "type": "text", "default": "", "placeholder": "e.g. 1:30", "half": True},
        {"name": "precise", "label": "Frame-accurate (re-encode)", "type": "checkbox", "default": True,
         "help": "Off = instant copy, cut snaps to nearest keyframe."},
    ],
)
def trim_media(files, opts, work):
    f = files[0]
    s, e = ts(opts.get("start")) or 0, ts(opts.get("end"))
    dur = probe(f)["duration"]
    if e is not None and e <= s:
        raise ToolError("End must be after start.")
    if dur and s >= dur:
        raise ToolError(f"Start is past the end of the file ({dur:.1f}s).")
    dest = out_path(work, f, f.suffix.lower(), "trim")
    span = ["-ss", str(s)] + (["-to", str(e)] if e is not None else [])
    if opts.get("precise"):
        is_video = f.suffix.lower() in VIDEO
        codec = VCODEC.get(f.suffix.lower().lstrip("."), VCODEC["mp4"]) if is_video else ACODEC.get(f.suffix.lower().lstrip("."), [])
        if is_video and f.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            dest = dest.with_suffix(".mp4")
            codec = VCODEC["mp4"]
        ffmpeg(["-i", str(f), *span, *codec, str(dest)])
    else:
        ffmpeg([*span, "-i", str(f), "-c", "copy", "-avoid_negative_ts", "make_zero", str(dest)])
    return Result("file", dest)


ASPECTS = [["9:16", "9:16 Reels / Shorts / TikTok"], ["1:1", "1:1 Square"], ["4:5", "4:5 Feed"],
           ["16:9", "16:9 YouTube"], ["4:3", "4:3"], ["21:9", "21:9 Cinema"]]


@tool(
    id="resize-video", name="Resize & reframe video", category="media", glyph="ratio", popular=True,
    description="Change resolution or aspect ratio — 9:16 reels, 1:1, 16:9 — with crop, bars or blurred fill.",
    keywords="aspect ratio vertical reel tiktok shorts instagram resolution 1080 720",
    accept=VIDEO,
    options=[
        {"name": "aspect", "label": "Aspect ratio", "type": "select", "default": "9:16",
         "choices": [["keep", "Keep original"], *ASPECTS]},
        {"name": "fill", "label": "Fit", "type": "segmented", "default": "blur", "when": {"aspect": [a[0] for a in ASPECTS]},
         "choices": [["crop", "Crop"], ["pad", "Bars"], ["blur", "Blurred fill"]]},
        {"name": "color", "label": "Bar colour", "type": "color", "default": "#000000", "when": {"fill": "pad"}},
        {"name": "res", "label": "Resolution (short side)", "type": "segmented", "default": "1080",
         "choices": [["2160", "4K"], ["1080", "1080"], ["720", "720"], ["480", "480"], ["360", "360"]]},
    ],
)
def resize_video(files, opts, work):
    f = files[0]
    info = probe(f)
    if not info["video"]:
        raise ToolError("No video stream found.")
    short = int(opts.get("res") or 1080)
    asp = opts.get("aspect", "keep")
    if asp == "keep":
        r = info["width"] / info["height"]
    else:
        a, b = (float(x) for x in asp.split(":"))
        r = a / b
    W, H = (even(short * r), even(short)) if r >= 1 else (even(short), even(short / r))
    mode = opts.get("fill", "blur") if asp != "keep" else "pad"
    if asp == "keep":
        vf = f"scale={W}:{H}"
    elif mode == "crop":
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    elif mode == "pad":
        col = (opts.get("color") or "#000000").lstrip("#")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x{col},setsar=1")
    else:
        vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2,"
              f"eq=brightness=-0.06[bg];[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    dest = out_path(work, f, ".mp4", f"{W}x{H}")
    ffmpeg(["-i", str(f), "-filter_complex" if mode == "blur" and asp != "keep" else "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", str(dest)])
    return Result("file", dest, meta={"note": f"{W} × {H}"})


@tool(
    id="video-to-gif", name="Video to GIF", category="media", glyph="smile",
    description="Turn a clip into a crisp looping GIF with an optimised palette.",
    accept=VIDEO,
    options=[
        {"name": "start", "label": "Start", "type": "text", "default": "0:00", "half": True},
        {"name": "length", "label": "Length (s)", "type": "number", "min": 0.5, "max": 60, "default": 5, "half": True},
        {"name": "width", "label": "Width (px)", "type": "segmented", "default": "480",
         "choices": [["320", "320"], ["480", "480"], ["640", "640"], ["800", "800"]]},
        {"name": "fps", "label": "Frames per second", "type": "segmented", "default": "12",
         "choices": [["8", "8"], ["12", "12"], ["15", "15"], ["24", "24"]]},
    ],
)
def video_to_gif(files, opts, work):
    f = files[0]
    w, fps = int(opts.get("width") or 480), int(opts.get("fps") or 12)
    dest = out_path(work, f, ".gif")
    filt = (f"fps={fps},scale={w}:-1:flags=lanczos,split[s0][s1];"
            "[s0]palettegen=max_colors=192:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4")
    ffmpeg(["-ss", str(ts(opts.get("start")) or 0), "-t", str(min(60, num(opts, "length", 5))), "-i", str(f),
            "-filter_complex", filt, "-loop", "0", str(dest)])
    return Result("file", dest)


@tool(
    id="convert-audio", name="Convert audio", category="media", glyph="audio", popular=True,
    description="MP3, WAV, M4A, AAC, FLAC, OGG, Opus — with bitrate control.",
    keywords="wav to mp3 m4a flac ogg format",
    accept=AUDIO + VIDEO, multiple=True,
    options=[
        {"name": "format", "label": "Convert to", "type": "segmented", "default": "mp3",
         "choices": [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"], ["flac", "FLAC"], ["ogg", "OGG"], ["opus", "Opus"]]},
        {"name": "bitrate", "label": "Bitrate", "type": "segmented", "default": "192",
         "choices": [["96", "96k"], ["128", "128k"], ["192", "192k"], ["256", "256k"], ["320", "320k"]],
         "when": {"format": ["mp3", "m4a", "ogg", "opus"]}},
        {"name": "mono", "label": "Mix down to mono", "type": "checkbox", "default": False},
        {"name": "normalize", "label": "Normalize loudness", "type": "checkbox", "default": False},
    ],
)
def convert_audio(files, opts, work):
    fmt = opts.get("format") if opts.get("format") in ACODEC else "mp3"

    def one(f):
        dest = out_path(work, f, f".{fmt}")
        if dest.suffix == f.suffix.lower():
            dest = out_path(work, f, f".{fmt}", "converted")
        args = ["-i", str(f), "-vn", *ACODEC[fmt]]
        if fmt in ("mp3", "m4a", "ogg", "opus", "aac"):
            args += ["-b:a", f"{int(opts.get('bitrate') or 192)}k"]
        if opts.get("mono"):
            args += ["-ac", "1"]
        if opts.get("normalize"):
            args += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
        ffmpeg([*args, str(dest)])
        return dest

    return for_each(files, work, one, "audio.zip")


tool(
    id="extract-audio", name="Extract audio from video", category="media", glyph="audio",
    description="Pull the soundtrack out of any video as MP3, M4A or WAV.",
    keywords="mp4 to mp3 video to audio",
    accept=VIDEO, multiple=True,
    options=[{"name": "format", "label": "Format", "type": "segmented", "default": "mp3",
              "choices": [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"], ["flac", "FLAC"]]},
             {"name": "bitrate", "label": "Bitrate", "type": "segmented", "default": "192",
              "choices": [["128", "128k"], ["192", "192k"], ["320", "320k"]], "when": {"format": ["mp3", "m4a"]}}],
)(convert_audio)


@tool(
    id="mute-video", name="Mute video", category="media", glyph="mute",
    description="Remove the audio track instantly, no re-encoding.",
    accept=VIDEO, multiple=True,
)
def mute_video(files, opts, work):
    def one(f):
        dest = out_path(work, f, f.suffix.lower(), "muted")
        ffmpeg(["-i", str(f), "-c:v", "copy", "-an", str(dest)])
        return dest

    return for_each(files, work, one, "muted.zip")


@tool(
    id="video-frames", name="Video to images", category="media", glyph="image",
    description="Grab frames every N seconds — or a single thumbnail — as JPG.",
    keywords="screenshot thumbnail frame extract",
    accept=VIDEO,
    options=[{"name": "every", "label": "One frame every (s)", "type": "number", "min": 0.1, "default": 2},
             {"name": "max", "label": "Max frames", "type": "number", "min": 1, "max": 500, "default": 60}],
)
def video_frames(files, opts, work):
    f = files[0]
    every = max(0.1, num(opts, "every", 2))
    frames = work / "frames"
    frames.mkdir()
    ffmpeg(["-i", str(f), "-vf", f"fps=1/{every}", "-frames:v", str(int(num(opts, "max", 60))), "-q:v", "3",
            str(frames / f"{f.stem}_%04d.jpg")])
    outs = sorted(frames.glob("*.jpg"))
    if not outs:
        raise ToolError("No frames could be extracted.")
    if len(outs) == 1:
        return Result("file", outs[0])
    from .registry import zip_files

    return Result("file", zip_files(outs, work / "out" / f"{f.stem}_frames.zip"))


@tool(
    id="change-speed", name="Change speed", category="media", glyph="bolt",
    description="Speed up or slow down audio and video while keeping pitch natural.",
    keywords="fast slow motion timelapse",
    accept=VIDEO + AUDIO,
    options=[{"name": "speed", "label": "Speed", "type": "segmented", "default": "1.5",
              "choices": [["0.5", "0.5×"], ["0.75", "0.75×"], ["1.25", "1.25×"], ["1.5", "1.5×"], ["2", "2×"], ["4", "4×"]]}],
)
def change_speed(files, opts, work):
    f = files[0]
    k = num(opts, "speed", 1.5)
    if not 0.25 <= k <= 4:
        raise ToolError("Speed must be between 0.25× and 4×.")
    info = probe(f)
    atempo = []
    rest = k
    while rest > 2:
        atempo.append("atempo=2.0")
        rest /= 2
    while rest < 0.5:
        atempo.append("atempo=0.5")
        rest /= 0.5
    atempo.append(f"atempo={rest:.4f}")
    is_video = bool(info["video"])
    dest = out_path(work, f, ".mp4" if is_video else f.suffix.lower(), f"{k:g}x")
    args = ["-i", str(f)]
    if is_video:
        args += ["-filter:v", f"setpts=PTS/{k}"]
        args += ["-filter:a", ",".join(atempo)] if info["audio"] else ["-an"]
        args += VCODEC["mp4"]
    else:
        args += ["-filter:a", ",".join(atempo)]
    ffmpeg([*args, str(dest)])
    return Result("file", dest)
