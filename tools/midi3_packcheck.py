#!/usr/bin/env python3
"""Check a MIDI 3.0 sample pack against SPEC.md section 7.

Scans a pack directory and reports:

  errors    anything that breaks the spec (the player would refuse to load
            the instrument, or some notes could never play)
  warnings  things that load but will probably sound wrong, such as a held
            loop that clicks or is not a whole number of cycles
  summary   what each instrument covers: note range, missing notes inside
            that range, velocity layers, round-robin takes

  python3 tools/midi3_packcheck.py path/to/MyPack
  python3 tools/midi3_packcheck.py path/to/MyPack --strict     (warnings fail too)
  python3 tools/midi3_packcheck.py path/to/MyPack --no-audio   (names only; fast)

Exit status is 0 when the pack passes, 1 when it does not.
Needs only the Python standard library.

Public domain (CC0 1.0).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import struct
import sys
from collections import defaultdict

# --- SPEC.md 7.2 --------------------------------------------------------------

NAME_RE = re.compile(
    r"^([A-G]s?)(-1|[0-9])\.(attack|held|release|hit)\.v(\d{3})"
    r"(\.r([1-9]\d*))?(\.c([+-]\d{1,3}))?(\.d([1-9]\d{0,5}))?\.wav$")
SEMITONE = {"C": 0, "Cs": 1, "D": 2, "Ds": 3, "E": 4, "F": 5, "Fs": 6,
            "G": 7, "Gs": 8, "A": 9, "As": 10, "B": 11}
NOTE_NAMES = ["C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"]
HEX_INST_RE = re.compile(r"^0x([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})$")

RATE = 48000
MAX_DECAY_MS = 600000         # 7.3.1: DECAY is 1-600000 ms
HELD_TOLERANCE_FRAMES = 0.5      # 7.3: whole cycles, rounded to the nearest frame
CLICK_RATIO = 4.0                # a join is a click if its step is this many
                                 # times bigger than the file's typical large step


FLAT_TO_SHARP = {"Db": "Cs", "Eb": "Ds", "Gb": "Fs", "Ab": "Gs", "Bb": "As"}


def suggest_name(fn: str) -> str | None:
    """Guess the correctly spelled name for a common misspelling, or None."""
    m = re.match(r"^([A-Ga-g])([#sb]?)(.*)$", fn)
    if not m:
        return None
    letter, acc, rest = m.group(1).upper(), m.group(2), m.group(3)
    if acc == "b":
        pitch = FLAT_TO_SHARP.get(letter + "b")
        if pitch is None:
            return None  # Cb and Fb change octave or letter; leave to a person
    else:
        pitch = letter + ("s" if acc in ("#", "s") else "")
    fixed = pitch + rest
    fixed = re.sub(r"\.v(\d{1,2})(?=\.)", lambda v: f".v{int(v.group(1)):03d}", fixed)
    if fixed != fn and NAME_RE.match(fixed):
        return fixed
    return None


def note_name(n: int) -> str:
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


# --- WAV reading --------------------------------------------------------------

class WavError(Exception):
    pass


def read_wav(path: str, want_samples: bool):
    """Return (channels, bits, is_float, frames, first, last) where first and
    last are lists of (mono-mixed) sample values scaled to -1..1, or None."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise WavError("not a WAV file")
    pos = 12
    fmt = None
    pcm = None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            pcm = body
        pos += 8 + size + (size & 1)
    if fmt is None or len(fmt) < 16:
        raise WavError("missing fmt chunk")
    if pcm is None:
        raise WavError("missing data chunk")

    tag, channels, rate, _, block, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    if tag == 0xFFFE and len(fmt) >= 26:  # WAVE_FORMAT_EXTENSIBLE
        tag = struct.unpack_from("<H", fmt, 24)[0]
    if tag == 1 and bits in (16, 24):
        is_float = False
    elif tag == 3 and bits == 32:
        is_float = True
    else:
        raise WavError(f"unsupported encoding (format {tag}, {bits}-bit); "
                       "use PCM 16-bit, PCM 24-bit, or 32-bit float")
    if rate != RATE:
        raise WavError(f"sample rate is {rate} Hz; must be {RATE}")
    if channels not in (1, 2):
        raise WavError(f"{channels} channels; must be mono or stereo")
    if block != channels * bits // 8:
        raise WavError("fmt block size does not match channels and bit depth")

    frames = len(pcm) // block
    if frames == 0:
        raise WavError("no audio")
    if not want_samples:
        return channels, bits, is_float, frames, None

    width = bits // 8

    def sample(frame: int) -> float:
        total = 0.0
        for c in range(channels):
            o = frame * block + c * width
            if is_float:
                v = struct.unpack_from("<f", pcm, o)[0]
            elif bits == 16:
                v = struct.unpack_from("<h", pcm, o)[0] / 32768.0
            else:
                b = pcm[o:o + 3]
                v = int.from_bytes(b, "little", signed=True) / 8388608.0
            total += v
        return total / channels

    samples = [sample(i) for i in range(frames)]
    return channels, bits, is_float, frames, samples


def typical_step(samples: list[float]) -> float:
    """The 99th-percentile step between neighbouring samples."""
    steps = sorted(abs(samples[i + 1] - samples[i]) for i in range(len(samples) - 1))
    if not steps:
        return 0.0
    return steps[min(len(steps) - 1, int(len(steps) * 0.99))]


# --- Checking -----------------------------------------------------------------

class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.summary: list[str] = []

    def err(self, where: str, msg: str):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str):
        self.warnings.append(f"{where}: {msg}")


def load_registry(path: str) -> dict[str, int]:
    with open(path, encoding="utf-8") as f:
        j = json.load(f)
    return {e["name"]: (e["family"] << 8) | e["member"] for e in j.get("registry", [])}


def check_pack_json(pack: str, inst_dirs: set[str], rep: Report):
    """Returns (a4, {instrument: default decay_ms})."""
    path = os.path.join(pack, "pack.json")
    a4 = 440.0
    decays: dict[str, int] = {}
    if not os.path.exists(path):
        return a4, decays
    try:
        with open(path, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError) as e:
        rep.err("pack.json", f"cannot be read: {e}")
        return a4, decays
    if j.get("format") != "midi3.pack.v1":
        rep.err("pack.json", f"format is {j.get('format')!r}; expected 'midi3.pack.v1'")
    if "a4" in j:
        if isinstance(j["a4"], (int, float)) and 400 <= j["a4"] <= 480:
            a4 = float(j["a4"])
        else:
            rep.err("pack.json", f"a4 = {j['a4']!r} is not a tuning reference in Hz")
    insts = j.get("instruments", {})
    if not isinstance(insts, dict):
        rep.err("pack.json", "instruments must be an object keyed by instrument name")
        insts = {}
    for name, cfg in insts.items():
        if name not in inst_dirs:
            rep.err("pack.json", f"names instrument '{name}', which has no directory")
        if not isinstance(cfg, dict):
            rep.err("pack.json", f"instruments.{name} must be an object")
            continue
        for key, val in cfg.items():
            if key == "decay_ms":
                if isinstance(val, int) and not isinstance(val, bool) and 1 <= val <= MAX_DECAY_MS:
                    decays[name] = val
                else:
                    rep.err("pack.json", f"instruments.{name}.decay_ms must be a whole number "
                                         f"from 1 to {MAX_DECAY_MS}")
            elif key == "decay_s":
                rep.err("pack.json", f"instruments.{name}.decay_s was renamed decay_ms "
                                     "(milliseconds, whole number)")
            else:
                rep.warn("pack.json", f"instruments.{name}.{key} is not a known setting")
    for key in j:
        if key not in ("format", "name", "a4", "instruments"):
            rep.warn("pack.json", f"'{key}' is not a known field")
    return a4, decays


def check_instrument(pack: str, inst: str, registry: dict[str, int], a4: float,
                     default_decay: int | None, audio: bool, rep: Report):
    where = inst
    m = HEX_INST_RE.match(inst)
    if m:
        fam, mem = int(m.group(1), 16), int(m.group(2), 16)
        if fam == 0 or mem == 0:
            rep.err(where, "InstID family and member must both be non-zero")
    elif inst not in registry:
        rep.err(where, "directory name is not an instrument in opcode16.json "
                       "and not a hex InstID like 0x1003")

    # (note, vel, round) -> {part: (filename, cents)}
    groups: dict[tuple[int, int, int], dict[str, tuple[str, int]]] = defaultdict(dict)
    decay_of: dict[tuple[int, int, int], int] = {}   # held files with a DECAY field
    bad_names = 0
    folder = os.path.join(pack, inst)

    for fn in sorted(os.listdir(folder)):
        if fn.startswith("."):
            continue  # hidden files (.DS_Store and similar) are ignored
        path = os.path.join(folder, fn)
        if os.path.isdir(path):
            rep.err(f"{where}/{fn}", "subdirectories are not allowed inside an instrument")
            continue
        m = NAME_RE.match(fn)
        if not m:
            fix = suggest_name(fn)
            hint = f" (did you mean {fix}?)" if fix else ""
            rep.err(f"{where}/{fn}", "name does not follow "
                                     "NOTE.PART.vVELOCITY[.rROUND][.cCENTS][.dDECAY].wav" + hint)
            bad_names += 1
            continue
        letter, octave, part, vel, _, rnd, _, cents, _, decay = m.groups()
        note = 12 * (int(octave) + 1) + SEMITONE[letter]
        vel = int(vel)
        rnd = int(rnd) if rnd else 1
        cents = int(cents) if cents else 0
        if not 0 <= note <= 127:
            rep.err(f"{where}/{fn}", f"note {note} is outside 0-127")
            bad_names += 1
            continue
        if not 1 <= vel <= 127:
            rep.err(f"{where}/{fn}", "velocity must be v001-v127")
            bad_names += 1
            continue
        if decay is not None:
            decay = int(decay)
            if part != "held":
                rep.err(f"{where}/{fn}", "only held files may have a DECAY field")
                bad_names += 1
                continue
            if decay > MAX_DECAY_MS:
                rep.err(f"{where}/{fn}", f"decay must be 1-{MAX_DECAY_MS} ms")
                bad_names += 1
                continue
        if abs(cents) > 50:
            rep.warn(f"{where}/{fn}", f"{cents:+d} cents is closer to another note; "
                                      "name it as that note instead")
        key = (note, vel, rnd)
        if part in groups[key]:
            other = groups[key][part][0]
            rep.err(f"{where}/{fn}", f"same note, layer, round, and part as {other} "
                                     "(a file with no .r counts as r1)")
            continue
        groups[key][part] = (fn, cents)
        if decay is not None:
            decay_of[key] = decay

    if bad_names:
        rep.err(where, f"{bad_names} misnamed file(s); a player will not load this instrument")

    if not groups:
        rep.err(where, "no valid sample files; this directory does not provide the instrument")
        return

    # 7.3: which parts may appear together
    for (note, vel, rnd), parts in sorted(groups.items()):
        tag = f"{where}/{note_name(note)} v{vel:03d} r{rnd}"
        if "hit" in parts and len(parts) > 1:
            rep.err(tag, "a hit file cannot be combined with attack, held, or release")
        if "hit" not in parts and "attack" not in parts:
            rep.err(tag, "held or release file without an attack file")
        cset = {c for _, c in parts.values()}
        if len(cset) > 1:
            rep.warn(tag, "parts of one note give different cents corrections")

    # 7.4: layers per note, rounds per layer
    by_note: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    for note, vel, rnd in groups:
        by_note[note][vel].add(rnd)
    for note, layers in sorted(by_note.items()):
        if max(layers) != 127:
            rep.err(f"{where}/{note_name(note)}",
                    f"highest velocity layer is v{max(layers):03d}; must be v127, "
                    f"or velocities {max(layers) + 1}-127 play nothing")
        for vel, rounds in sorted(layers.items()):
            if sorted(rounds) != list(range(1, max(rounds) + 1)):
                missing = sorted(set(range(1, max(rounds) + 1)) - rounds)
                rep.err(f"{where}/{note_name(note)} v{vel:03d}",
                        "round-robin takes have gaps; missing " +
                        ", ".join(f"r{r}" for r in missing))

    # 7.3.1: decay consistency
    held_keys = [k for k, parts in groups.items() if "held" in parts]
    with_d = [k for k in held_keys if k in decay_of]
    if with_d and len(with_d) < len(held_keys) and default_decay is None:
        without = sorted(set(held_keys) - set(with_d))
        shown = ", ".join(f"{note_name(n)} v{v:03d} r{r}" for n, v, r in without[:6])
        more = f" and {len(without) - 6} more" if len(without) > 6 else ""
        rep.warn(where, f"{len(with_d)} held file(s) have a decay but {len(without)} do not "
                        f"({shown}{more}), and pack.json sets no default; those notes "
                        "will sustain forever")

    # Audio checks
    if audio:
        for (note, vel, rnd), parts in sorted(groups.items()):
            tag = f"{where}/{note_name(note)} v{vel:03d} r{rnd}"
            info = {}
            for part, (fn, cents) in parts.items():
                need = part in ("attack", "held")
                try:
                    info[part] = read_wav(os.path.join(folder, fn), need)
                except (WavError, OSError, struct.error) as e:
                    rep.err(f"{where}/{fn}", str(e))
            chans = {v[0] for v in info.values()}
            if len(chans) > 1:
                rep.err(tag, "attack, held, and release have different channel counts")

            if "held" in info:
                _, _, _, frames, held = info["held"]
                cents = parts["held"][1]
                freq = a4 * 2 ** ((note - 69) / 12) * 2 ** (cents / 1200)
                period = RATE / freq
                cycles = max(1, round(frames / period))
                off = frames - cycles * period
                if abs(off) > HELD_TOLERANCE_FRAMES:
                    rep.warn(tag, f"held is {frames} frames = {frames / period:.2f} cycles; "
                                  f"should be {round(cycles * period)} frames "
                                  f"({cycles} whole cycles) or it will drift out of tune")
                if cycles < 4:
                    rep.warn(tag, f"held holds only {cycles} cycle(s) of the note; "
                                  "it will sound buzzy, use a longer held file")
                step = typical_step(held)
                wrap = abs(held[0] - held[-1])
                if step > 0 and wrap > CLICK_RATIO * step:
                    rep.warn(tag, "held loop jumps from its last frame back to its first; "
                                  "it will click on every repeat")
                if "attack" in info:
                    attack = info["attack"][4]
                    join = abs(attack[-1] - held[0])
                    if step > 0 and join > CLICK_RATIO * step:
                        rep.warn(tag, "attack does not flow into held; the splice will click")

    # Summary
    notes = sorted(by_note)
    lo, hi = notes[0], notes[-1]
    gaps = [n for n in range(lo, hi + 1) if n not in by_note]
    layer_counts = sorted({len(l) for l in by_note.values()})
    max_rounds = max(max(r) for l in by_note.values() for r in l.values())
    kinds = sorted({p for parts in groups.values() for p in parts})
    layers_text = (str(layer_counts[0]) if len(layer_counts) == 1
                   else f"{layer_counts[0]} to {layer_counts[-1]}")
    line = (f"{inst}: {len(notes)} notes, {note_name(lo)}-{note_name(hi)}, "
            f"{layers_text} velocity layer(s), "
            f"up to {max_rounds} round(s), parts: {', '.join(kinds)}")
    if held_keys:
        if decay_of:
            ds = sorted(decay_of.values())
            line += (f"\n    held decay: {ds[0]}-{ds[-1]} ms from file names"
                     + (f", {default_decay} ms default" if default_decay else ""))
        elif default_decay:
            line += f"\n    held decay: {default_decay} ms (pack.json default)"
        else:
            line += "\n    held decay: none (held sounds sustain at a constant level)"
    if gaps:
        shown = ", ".join(note_name(n) for n in gaps[:12])
        more = f" and {len(gaps) - 12} more" if len(gaps) > 12 else ""
        line += f"\n    missing inside that range (these notes will be silent): {shown}{more}"
    rep.summary.append(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check a MIDI 3.0 sample pack (SPEC.md section 7).")
    ap.add_argument("pack", help="pack directory")
    ap.add_argument("--json", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "schemas", "opcode16.json"),
        help="path to opcode16.json")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--no-audio", action="store_true",
                    help="check names and structure only; do not open the WAV files")
    args = ap.parse_args()

    if not os.path.isdir(args.pack):
        print(f"error: {args.pack} is not a directory", file=sys.stderr)
        return 1
    registry = load_registry(args.json)
    rep = Report()

    entries = sorted(os.listdir(args.pack))
    inst_dirs = {e for e in entries
                 if os.path.isdir(os.path.join(args.pack, e)) and not e.startswith(".")}
    for e in entries:
        if e.startswith(".") or e in inst_dirs or e == "pack.json":
            continue
        rep.warn(e, "loose file at the top of the pack is ignored; samples go in an instrument directory")

    a4, decays = check_pack_json(args.pack, inst_dirs, rep)
    if not inst_dirs:
        rep.err(args.pack, "no instrument directories")
    for inst in sorted(inst_dirs):
        check_instrument(args.pack, inst, registry, a4, decays.get(inst),
                         not args.no_audio, rep)

    for title, items in (("Errors", rep.errors), ("Warnings", rep.warnings),
                         ("Instruments", rep.summary)):
        if items:
            print(f"{title} ({len(items)})" if title != "Instruments" else title)
            for item in items:
                print(f"  {item}")
            print()

    failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
    print(f"{'FAIL' if failed else 'PASS'}: {len(rep.errors)} error(s), "
          f"{len(rep.warnings)} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
