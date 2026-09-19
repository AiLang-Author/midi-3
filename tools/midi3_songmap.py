#!/usr/bin/env python3
"""SMF → Opcode16 .songmap (importer). Does not guess drums from channel 10.

Reads a Standard MIDI File, lists each MIDI channel that has notes, and
writes a .songmap using Librarys/Media/opcode16.json. Unmapped programs
become comments. Channel 9/10 without a kit name is flagged AMBIGUOUS.

  python3 Applications/SynthKit/tools/midi3_songmap.py song.mid
  python3 Applications/SynthKit/tools/midi3_songmap.py song.mid -o song.mid.songmap

Copyright 2026 Sean Collins, 2 Paws Machine and Engineering. SCSL.
"""
from __future__ import annotations

import argparse, json, os, struct, sys

def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]

def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]

def vlq(data, i):
    v = 0
    while i < len(data):
        c = data[i]
        i += 1
        v = (v << 7) | (c & 0x7F)
        if c < 0x80:
            return v, i
    return v, i

def parse_smf(path):
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        raise SystemExit(f"not SMF: {path}")
    hlen = u32(data, 4)
    fmt, ntr, div = struct.unpack_from(">HHH", data, 8)
    pos = 8 + hlen
    tracks = []
    while pos + 8 <= len(data) and data[pos:pos+4] == b"MTrk":
        ln = u32(data, pos + 4)
        tracks.append(data[pos + 8 : pos + 8 + ln])
        pos += 8 + ln
    chans = {c: {"prog": None, "notes": [], "name": None, "bank": 0} for c in range(16)}
    tnames = []
    for ti, tr in enumerate(tracks):
        i = 0
        run = 0
        tname = ""
        while i < len(tr):
            _, i = vlq(tr, i)
            if i >= len(tr):
                break
            st = tr[i]
            if st < 0x80:
                st = run
            else:
                i += 1
                run = st
            if st == 0xFF:
                mt = tr[i]; i += 1
                ln, i = vlq(tr, i)
                payload = tr[i : i + ln]
                i += ln
                if mt == 0x03:
                    tname = payload.decode("latin1", "replace").split("\x00")[0]
            elif st in (0xF0, 0xF7):
                ln, i = vlq(tr, i)
                i += ln
            else:
                hi, ch = st & 0xF0, st & 0x0F
                if hi == 0xC0:
                    chans[ch]["prog"] = tr[i]
                    i += 1
                elif hi == 0xD0:
                    i += 1
                elif hi == 0xB0:
                    cc, vv = tr[i], tr[i + 1]
                    i += 2
                    if cc == 0:
                        chans[ch]["bank"] = vv
                elif hi == 0x80:
                    n = tr[i]
                    i += 2
                    chans[ch]["notes"].append(n)
                elif hi == 0x90:
                    n, v = tr[i], tr[i + 1]
                    i += 2
                    if v:
                        chans[ch]["notes"].append(n)
                else:
                    i += 2
        tnames.append(tname)
        if tname:
            for c, info in chans.items():
                if info["notes"] and not info["name"]:
                    info["name"] = tname
    return fmt, ntr, div, chans, tnames

def load_reg(path):
    with open(path, encoding="utf-8") as f:
        j = json.load(f)
    gm = {int(e["prog"]): e["name"] for e in j.get("gm", [])}
    kit = {int(e["prog"]): e["name"] for e in j.get("kit", [])}
    names = {e["name"] for e in j.get("registry", [])}
    return gm, kit, names

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mid")
    ap.add_argument("-o", "--output")
    ap.add_argument("--json", default=os.path.join(
        os.path.dirname(__file__), "..", "..", "Librarys", "Media", "opcode16.json"))
    args = ap.parse_args()
    fmt, ntr, div, chans, tnames = parse_smf(args.mid)
    gm, kit, names = load_reg(os.path.abspath(args.json))
    lines = [
        f"# opcode16 songmap for {os.path.basename(args.mid)}",
        f"# SMF format={fmt} tracks={ntr} division={div}",
        "# Channel is SMF transport only. Inst names from opcode16.json.",
        "# AMBIGUOUS = kit vs melody: edit by hand. Do not assume ch 10 = drums.",
        "",
    ]
    for c in range(16):
        info = chans[c]
        if not info["notes"]:
            continue
        lo, hi = min(info["notes"]), max(info["notes"])
        n = len(info["notes"])
        prog = info["prog"]
        bank = info["bank"]
        hint = info["name"] or ""
        inst = None
        tag = ""
        if prog is None:
            tag = "NO_PC"
        elif c in (9,) and prog in kit:
            inst = kit[prog]
            tag = "kit_table"
        elif prog in gm:
            inst = gm[prog]
            tag = "gm_table"
        else:
            tag = f"UNMAPPED_GM_{prog}"
        if c == 9 and inst is None:
            tag = "AMBIGUOUS_CH9 " + tag
        comment = f"# ch={c} notes={n} range={lo}-{hi} pc={prog} bank={bank} {hint} [{tag}]"
        lines.append(comment)
        if inst:
            lines.append(f"track {c} inst={inst}")
        else:
            lines.append(f"# track {c} inst=  NEED_NAME")
        lines.append("")
    text = "\n".join(lines) + "\n"
    out = args.output
    if out:
        open(out, "w", encoding="utf-8").write(text)
        print(f"wrote {out}", file=sys.stderr)
    print(text, end="")

if __name__ == "__main__":
    main()
