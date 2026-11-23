#!/usr/bin/env python3
"""Render deck.html step by step, add a `say` voiceover and stitch an MP4 with crossfades.

Usage: python3 video/build.py [--engine kokoro|say] [--voice af_heart] [--speed 0.95]
Kokoro voices: af_heart (default, warm), af_bella (soft), am_michael (calm male), bf_emma (British).
With --engine say, --voice is a macOS voice name and --rate the words per minute.
Output: video/out/experiment.mp4 and video/out/experiment.srt
"""
import argparse, json, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "out"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (scene, step, narration)
SCRIPT = [
    (1, 0, "What happens if you take Shopware and ask a slightly crazy question: what if we just threw out the database?"),
    (1, 1, "And then, while we're at it, the DAL too. This is a short story about an experiment that did exactly that, and why experiments like this matter more than ever."),
    (2, 1, "Shopware runs on MySQL and MariaDB. Every query, every migration, every id is built around that. So question one: can the same code run on PostgreSQL, or even SQLite, without a rewrite?"),
    (2, 2, "Question two, even crazier: do we actually need our own data abstraction layer? What if Doctrine, Cycle ORM, or plain hand-written SQL did the job better?"),
    (2, 3, "Nobody planned to ship any of this. The goal was to break things on purpose, and see where it hurts."),
    (3, 1, "We ran it as eight waves in six days."),
    (3, 2, "AI agents worked in parallel lanes. Each wave was split into handoffs, and a coordinator checked every result."),
    (3, 3, "And every claim had to be backed by a measurement: four databases, the same machine, the same data."),
    (3, 4, "In the end, the proof of concept branch had a hundred and eighteen commits, across four hundred seventy nine files."),
    (4, 0, "Result one: it runs. The same Shopware code installs and serves requests on MySQL, MariaDB, PostgreSQL, and SQLite."),
    (4, 1, "All nine hundred ten core migrations run on PostgreSQL, with zero schema differences to MySQL."),
    (4, 2, "The DAL integration suite, eight hundred and four tests, is fully green on PostgreSQL and MariaDB."),
    (4, 3, "And SQLite passes seven hundred ninety five of them, with nothing more than its own dialect and a few shims."),
    (5, 0, "Now performance. Here is the storefront on PostgreSQL, compared to MariaDB."),
    (5, 1, "The first run was rough: two point six to three point six times slower."),
    (5, 2, "After seven waves of fixes, connection handling, plan caching, indexes, it's down to one point one to one point five times."),
    (5, 3, "Search got a lot faster with a trigram index, from about a hundred fifty milliseconds to ninety three."),
    (5, 4, "But writes stayed the weak spot. A bulk write takes twice as long on PostgreSQL. And that pointed us somewhere unexpected."),
    (6, 0, "So, crazy idea number two: remove the DAL."),
    (6, 1, "We built the same five scenarios with today's DAL, with plain SQL, with Doctrine ORM, with Cycle ORM, and with a DAL version two, our own DAL with improvements we could switch on one at a time."),
    (6, 2, "Nine configurations, four databases, and every result was checked against the DAL, so nobody could cheat."),
    (7, 0, "Here's what it showed. Writing fifty products on MySQL takes the DAL ninety milliseconds, and three hundred seventy one SQL statements."),
    (7, 1, "The ORMs are faster, but they still send around three hundred fifty statements."),
    (7, 2, "DAL version two batches its updates and gets down to twenty three statements."),
    (7, 3, "And plain SQL does the same write in seven milliseconds, with five statements."),
    (7, 4, "So the database was never the problem. The number of statements, and the PHP code around the writer, were. We only saw that because we were crazy enough to take the DAL away."),
    (8, 0, "On reads, DAL version two takes a product listing on MySQL from twelve milliseconds down to under four."),
    (8, 1, "On PostgreSQL, from twenty one down to ten."),
    (8, 2, "And one surprise: on PostgreSQL, our hand-written SQL was slower than the DAL. Hand-written does not automatically mean fast. You have to measure."),
    (9, 0, "So what's the verdict?"),
    (9, 1, "Replacing the DAL with an ORM would cost an estimated one hundred to two hundred thirty person-weeks, break every plugin and app, and we'd have to rebuild translations, inheritance and versioning by hand."),
    (9, 2, "Building DAL version two step by step is an estimated eleven to twenty seven person-weeks, with no breaking change, and every lever is already measured. Keep the DAL. Make it better."),
    (10, 0, "And the crazy idea paid off for today's Shopware, too."),
    (10, 1, "We collected thirty four core findings that help Shopware on MySQL right now: performance, robustness, and real bugs."),
    (10, 2, "We scanned three thousand seven hundred forty seven store plugins, so we know how much raw SQL is out there and what would break."),
    (10, 3, "And the core work is already cut into upstream-ready epics."),
    (11, 0, "So, what do we take away?"),
    (11, 1, "Crazy questions got cheap. With AI agents, a big what-if fits into a week."),
    (11, 2, "Removing something is the fastest way to see what it costs."),
    (11, 3, "A no is a result. We won't replace the DAL, and now we know why, with numbers."),
    (11, 4, "Side findings pay off right away."),
    (11, 5, "And measure, don't guess. Our intuition was wrong more than once."),
    (12, 0, "So: be a bit crazy. Measure everything. And keep what's true."),
    (12, 1, "Thanks for watching."),
]

# spoken form of terms the TTS gets wrong; subtitles keep the written form
SPOKEN = [(r"\bDAL\b", "D-A-L"), (r"\bMySQL\b", "My S Q L"), (r"\bPostgreSQL\b", "Postgres")]

PAD = 0.9      # silence after each narration
LEAD = 0.35    # silence before each narration
XFADE = 0.4    # crossfade between steps


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def duration(path):
    probe = run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path))
    return float(json.loads(probe.stdout)["format"]["duration"])


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="kokoro", choices=["kokoro", "say"])
    ap.add_argument("--voice", default=None)
    ap.add_argument("--speed", type=float, default=0.95)
    ap.add_argument("--rate", default="178")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    deck = (ROOT / "deck.html").as_uri()

    def spoken(text):
        for pat, rep in SPOKEN:
            text = re.sub(pat, rep, text)
        return text

    raw = [OUT / f"{i:02}.raw.wav" for i in range(len(SCRIPT))]
    if args.engine == "kokoro":
        jobs = OUT / "tts-jobs.json"
        jobs.write_text(json.dumps({"voice": args.voice or "af_heart", "speed": args.speed,
                                    "items": [{"text": spoken(t), "out": str(r)} for (_, _, t), r in zip(SCRIPT, raw)]}))
        run("uv", "run", "--quiet", "--python", "3.12", "--with", "kokoro", "--with", "soundfile",
            str(ROOT / "tts_kokoro.py"), str(jobs))
    else:
        for (_, _, t), r in zip(SCRIPT, raw):
            aiff = r.with_suffix(".aiff")
            run("say", "-v", args.voice or "Samantha", "-r", args.rate, "-o", str(aiff), spoken(t))
            run("ffmpeg", "-y", "-v", "error", "-i", str(aiff), str(r))
            aiff.unlink()

    segs = []
    for i, (scene, step, text) in enumerate(SCRIPT):
        png = OUT / f"{i:02}.png"
        wav = OUT / f"{i:02}.wav"
        run(CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
            "--window-size=1920,1080", "--virtual-time-budget=1000", f"--screenshot={png}", f"{deck}#{scene}-{step}")
        run("ffmpeg", "-y", "-v", "error", "-i", str(raw[i]), "-ar", "48000", "-ac", "2", str(wav))
        raw[i].unlink()
        a = duration(wav)
        segs.append({"png": png, "wav": wav, "audio": a, "len": LEAD + a + PAD, "text": text})
        print(f"{i:02} scene {scene}.{step}  {a:5.2f}s")

    # video: one still per step, chained xfades; audio: each narration delayed to its slot
    inputs, vf, af = [], [], []
    for s in segs:
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{s['len'] + XFADE:.3f}", "-i", str(s["png"])]
    for s in segs:
        inputs += ["-i", str(s["wav"])]
    n = len(segs)
    offset, starts, prev = 0.0, [], "[0:v]"
    for k, s in enumerate(segs):
        starts.append(offset)
        if k > 0:
            out = f"[v{k}]"
            vf.append(f"{prev}[{k}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}{out}")
            prev = out
        offset += s["len"]
    total = offset + XFADE
    for k, s in enumerate(segs):
        d = int((starts[k] + LEAD + (XFADE if k else 0)) * 1000)
        af.append(f"[{n + k}:a]adelay={d}|{d}[a{k}]")
    af.append("".join(f"[a{k}]" for k in range(n)) + f"amix=inputs={n}:normalize=0,apad,atrim=0:{total:.3f}[aout]")
    vf.append(f"{prev}fade=t=in:st=0:d=0.6,fade=t=out:st={total - 1:.3f}:d=1,format=yuv420p[vout]")

    mp4 = OUT / "experiment.mp4"
    run("ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(vf + af),
        "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-tune", "stillimage", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(mp4))

    with open(OUT / "experiment.srt", "w") as f:
        for k, s in enumerate(segs):
            t0 = starts[k] + LEAD + (XFADE if k else 0)
            f.write(f"{k + 1}\n{srt_time(t0)} --> {srt_time(t0 + s['audio'])}\n{s['text']}\n\n")
    print(f"done: {mp4}  {total:.1f}s")


if __name__ == "__main__":
    main()
