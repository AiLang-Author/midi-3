# MIDI 3.0 Specification (Opcode16)

**Status:** Draft 0.1  
**Date:** 2026-09-19  
**Author:** Sean Collins, 2 Paws Machine and Engineering  

Copyright © 2026 Sean Collins, 2 Paws Machine and Engineering.

This document is the specification. Implementations may use any license. The text of this specification is licensed under Creative Commons Attribution 4.0 International (CC BY 4.0).

---

## 0. Abstract

MIDI 1.0 and MIDI 2.0 describe a timed stream of small events. That *shape* is good. The *identity* model is not: 4-bit channel, 7-bit program, bank select, and “channel 10 is drums” are conventions for 1983 outboard hardware, not for named sample instruments.

MIDI 3.0 keeps the stream. It replaces patch numbers with a **16-bit named instrument space**, a **16-bit track id**, and an optional **16-bit group**. A song declares what it needs by name. A sample pack declares what it implements. Bind is set intersection. Missing bind is a failed load, never a silent piano.

Wire encoding still fits in small packets (CAN-like: 8-bit opcode + 16-bit fields). Family occupies the high 8 bits of InstID; member the low 8 bits. Example: woodwinds/flute = `0x8080`.

---

## 1. Problem

| MIDI 1.0 / 2.0 object | Width | Meant for | Abuse |
|---|---|---|---|
| Channel | 4 bits (16 per group) | Which *box* on the cable | Treated as track *and* instrument role |
| Program Change | 7 bits (128) | Slot on *that* box this week | Treated as a universal flute |
| Bank Select | 7+7 bits | More slots on the box | SoundFont bank 128 for kits because 0–127 was “melody” |
| SMF track | unbounded | A pile of events | Optional name, optional program, often neither |

A legal Type 1 SMF can put 25 instruments on “channel 1” with no names. Program `25` on a DX7 is not program `25` in GeneralUser GS. MIDI 2.0 adds 16-bit velocity and 256 channels (16 groups × 16 channels). It does **not** add named instruments.

If a player needs a heuristic (channel 10 = drums, missing program = piano, nearest sample), the format is incomplete. MIDI 3.0 forbids those heuristics in the player. Importers may translate old files into MIDI 3.0 documents, or fail with a diagnostic.

---

## 2. Conformance

A **player** that claims MIDI 3.0:

1. Plays only documents that satisfy this spec.
2. Does not interpret MIDI channel as instrument identity.
3. Does not treat program numbers as kinds.
4. Does not fall back to another instrument when bind fails.
5. Logs bind failure (track id, missing InstID) instead of inventing sound.

A **pack** that claims MIDI 3.0 lists every InstID it implements. Unknown opcodes are absent, not remapped.

An **importer** (SMF, SoundFont 2, GM tables) is not a player. It may use translation tables. After import, the runtime document contains TrackID + InstID only.

---

## 3. Identifiers

All identifiers are unsigned 16-bit integers unless noted. Zero is reserved in every field (unset / none).

```
InstID   = (Family << 8) | Member     ; family 1..255, member 1..255
TrackID  = 0..65535                   ; 0 is a valid first track
GroupID  = 0..65535                   ; 0 = no group
NoteId   = 1..65535                   ; 0 = not a note event
```

### 3.1 InstID

InstID names a **kind**, not a brand and not a hardware slot.

- Family is the high byte (woodwinds = 128).
- Member is the low byte (flute = 128 → InstID `0x8080`).
- Sparse allocation is allowed and preferred (CAN-style). Dense 0–127 packing is forbidden as a compatibility trick.

The canonical name ↔ InstID table is data (`opcode16.json` in this repository), not code. Adding a kind is appending JSON, not recompiling a player.

### 3.2 TrackID

TrackID is the identity of a line in the song (sung melody, bass, kit). It is not a MIDI channel. A song with 25 instruments has 25 tracks. If those events arrived on SMF channel 1, that channel is discarded at import.

### 3.3 GroupID

Optional. Mute, solo, exclusive choke (open hat vs closed hat). 0 = none.

### 3.4 NoteId

Note-off addresses a sounding voice by NoteId, not by (note number, channel). Two overlapping D6s have two NoteIds.

---

## 4. Three namespaces (do not collapse)

| Namespace | Holds | Example |
|---|---|---|
| Kind | InstID + name | `calliope` / `0x1003` |
| Track | TrackID | “sung melody” |
| Realization | pack + samples | 48 kHz WAVs that implement `calliope` |

**Song** lists tracks → InstID (or name interned at compile).  
**Pack** lists InstID → regions/samples.  
**Bind:** every InstID in the song exists in the loaded pack, or the song does not arm.

```
song  track 4  inst=calliope
pack  GeneralUser implements 0x1003
  → play

song  track 4  inst=calliope
pack  PTQ (piano, whistle, …) no calliope
  → BIND FAIL
```

Same song, different pack: bind succeeds only if that pack implements the kinds. There is no `{bank}/{program}` in the song.

---

## 5. Family table (v1)

These are kinds. Assigned values:

| Family | Hex | Kind |
|---:|---|---|
| 1 | `0x01` | Piano / acoustic keys |
| 2 | `0x02` | Electric keys |
| 3 | `0x03` | Organ |
| 4 | `0x04` | Guitar |
| 5 | `0x05` | Bass |
| 6 | `0x06` | Bowed strings |
| 7 | `0x07` | Ensemble / choir |
| 8 | `0x08` | Brass |
| 9 | `0x09` | Reed |
| 10 | `0x0A` | Pipe |
| 16 | `0x10` | Synth lead |
| 17 | `0x11` | Synth pad |
| 18 | `0x12` | Synth bass |
| 19 | `0x13` | FX / texture |
| 32 | `0x20` | Tuned percussion |
| 33 | `0x21` | Kit (one track; note selects piece) |
| 34 | `0x22` | Percussion piece (own track) |
| 48 | `0x30` | Ethnic / traditional |
| **128** | **`0x80`** | **Woodwinds** |
| 254 | `0xFE` | Analog oscillator |
| 255 | `0xFF` | Unpitched / noise |

Member `0` is illegal in v1. New families may be added by extending `opcode16.json` without changing this document’s laws.

---

## 6. Song document

A song is an explicit document.

### 6.1 Header

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Human title |
| `rate` | u32 | Sample clock, always 48000 in v1 |
| `tpqn` | u16 | Ticks per quarter if imported from SMF; 0 if unused |
| `tracks[]` | Track | One instrument each |
| `events[]` | Event | Sorted by time, then TrackID |

### 6.2 Track

| Field | Type | Meaning |
|---|---|---|
| `id` | TrackID | Stable 0..N-1 |
| `name` | string | Optional human name |
| `inst` | InstID or name | **Required** if the track has notes |
| `group` | GroupID | 0 = none |
| `smf_ch` | u8 | Import debug only; not used by the player |

Two instruments ⇒ two tracks. A mid-track program change while notes sound is an import **error**. Consecutive programs with a silent gap may split into two tracks.

### 6.3 Events

Time is **sample frames** at `rate` (DAC is the clock). Authoring ticks are optional metadata.

| Op | Code | Payload |
|---|---:|---|
| NOP | `0x00` | — |
| NOTE_ON | `0x10` | note u16, vel u16, nid u16 |
| NOTE_OFF | `0x11` | nid u16 |
| CC | `0x20` | cc u16, value u16 |
| BEND | `0x21` | cents i16 |
| TEMPO | `0x30` | microseconds per quarter u32 |
| END | `0x3F` | — |

Instrument is **not** on NOTE_ON. It is on the track.

**Note** u16: low 8 bits 0–127 are the musician’s MIDI note for zone match. High 8 bits reserved (0 in v1).

**Vel** u16: 0 = off. MIDI 1.0 7-bit maps by left-shift (`v << 9` with the existing UMP 7→16 scale is acceptable).

### 6.4 Percussion

- **Kit:** InstID family `0x21`. One track. Note number selects the piece (`pitch_keytrack = 0` on regions). The track *declares* `kit_standard` (or another kit name).
- **Piece:** family `0x22`. One track per drum if a snare line is its own part.
- SMF channel 10 with no declaration is an **import fail** unless a sidecar names a kit. Never `channel == 9 → bank 128`. Never `CC0 = 128` (CC0 is 0–127 in MIDI 1.0).

---

## 7. Pack document (samples)

A pack is a directory of 48 kHz samples plus a map InstID → regions.

v1 requires:

- Sample rate **48000**. No live resample in the player.
- Pitch = `2^(semitones/12)` from declared root + signed cents. Cents are signed. Unsigned 32-bit “−1 cent” is a bug.
- Zone match is a **total function** of (note, velocity): all matching layers play; zero matches = silence + miss counter. No nearest-sample.
- Loop points are declared. Dummy `originalPitch = 60` is data; the player does not clamp it into the key range.

Authoring text for regions may be a **closed SFZ subset** (separate document). SoundFont 2 may **compile** into a pack. After compile, SF2 generators are not the runtime.

---

## 8. Live packet (optional)

Keep MIDI’s small-opcode shape. Example CAN-sized frame:

```
29-bit ID:  priority:3 | TrackID:16 | op:8 | 0:2
8-byte data (NOTE_ON): note u16 | vel u16 | nid u16 | reserved u16
```

Family/member are **not** in the live note packet. The receiver bound TrackID → InstID at session start. Re-patch mid-note is a new track.

---

## 9. Import from MIDI 1.0 / SMF (non-normative)

Importers:

1. Parse SMF (Type 0/1).
2. Split Type 0 by channel; Type 1 by file track, then by channel if mixed.
3. Assign TrackID 0,1,2,…
4. Instrument: sidecar name **preferred**. Else a declared Program Change through `opcode16.json` `gm[]`. Else **fail**.
5. Write a MIDI 3.0 song (headers + events). The `.mid` is source, not runtime.

Sidecar (data, not a heuristic):

```
# songmap v1
track 0  inst=bass_electric
track 2  inst=calliope
track 9  inst=kit_electronic
```

A translation table that is incomplete is correct. Unmapped GM program 4 is InstID 0 (`BIND_MISS`), not piano.

---

## 10. Observability

A player SHALL emit:

- `BIND_MISS track=N` once per track that sounds without an InstID.
- `BIND_EMPTY track=N inst=X` if the pack does not implement X.
- `PC_UNMAPPED track=N prog=P` if a Program Change has no `gm[]` row.

It SHALL NOT flood per-note sample dumps in the default log.

---

## 11. Versioning

- This document is **0.1**. InstID `0x0000` remains reserved.
- Family assignments in §5 are stable once a numbered 1.0 is cut.
- JSON `format` field is `opcode16.v1`.

---

## 12. References

- MIDI 1.0 Detailed Specification (MMA)
- MIDI 2.0 and Universal MIDI Packet (MMA) — used here as an *event wire*, not as the identity model
- SoundFont 2.04 (EMU) — compile target only
- Opcode16 JSON schema: `schemas/opcode16.json` in this repository
