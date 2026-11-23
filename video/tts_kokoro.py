"""Kokoro TTS helper, run by build.py through:
uv run --python 3.12 --with kokoro --with soundfile video/tts_kokoro.py <jobs.json>
jobs.json: {"voice": "af_heart", "speed": 0.95, "items": [{"text": "...", "out": "/path.wav"}]}
Runs fully offline after the first model download.
"""
import json, sys
import numpy as np
import soundfile as sf
from kokoro import KPipeline

jobs = json.load(open(sys.argv[1]))
pipe = KPipeline(lang_code="a" if jobs["voice"][0] == "a" else "b")
for item in jobs["items"]:
    audio = np.concatenate([a for _, _, a in pipe(item["text"], voice=jobs["voice"], speed=jobs["speed"])])
    sf.write(item["out"], audio, 24000)
