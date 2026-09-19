# MIDI 3.0 Specification (Opcode16)

**Status:** Draft 0.1  
**Date:** 2026-09-19  
**Author:** Sean Collins, 2 Paws Machine and Engineering  

This specification is dedicated to the public domain under CC0 1.0. Anyone may use, copy, modify, or implement it for any purpose, without asking permission or giving credit.

---

## 0. Summary

MIDI 1.0 and MIDI 2.0 describe music as a timed stream of small events. This specification keeps that approach. What it changes is how instruments are identified.

In earlier versions of MIDI, an instrument is identified indirectly: by a channel number, a program number, and optionally a bank number. These numbers were designed to select sounds on a particular piece of hardware, and they do not reliably mean the same instrument from one device or sound set to another.

MIDI 3.0 identifies instruments by name instead. Each instrument kind has a 16-bit identifier (InstID), each musical part has a 16-bit track identifier (TrackID), and tracks may optionally be placed in a 16-bit group (GroupID).

A song lists the instruments it needs. A sample pack lists the instruments it provides. A song can be played with a pack only if the pack provides every instrument the song needs. If it does not, the player reports which instruments are missing rather than substituting a different sound.

Messages remain small enough to fit in compact packets, such as CAN bus frames (an 8-bit opcode followed by 16-bit fields). The upper 8 bits of an InstID give the instrument family and the lower 8 bits give the member within that family. For example, the flute, a member of the woodwind family, is `0x8080`.

---

## 1. Background

The table below summarizes how instruments are identified in MIDI 1.0 and 2.0, and how those identifiers are commonly used in practice.

| MIDI 1.0 / 2.0 field | Size | Original purpose | Common use in practice |
|---|---|---|---|
| Channel | 4 bits (16 per group) | Selects which device on the cable receives the message | Also used to identify the track and the instrument's role |
| Program Change | 7 bits (128 values) | Selects a sound slot on the receiving device | Assumed to mean the same instrument on every device |
| Bank Select | 7 + 7 bits | Selects additional sound slots | Used for special cases, e.g. SoundFont bank 128 for drum kits |
| SMF track | Unlimited | Groups a series of events | Name and program are both optional and often absent |

Because of this, the same file can sound different, or wrong, depending on where it is played. A valid Type 1 Standard MIDI File (SMF) may place 25 different instruments on channel 1 without naming any of them. Program 25 on a Yamaha DX7 is a different sound from program 25 in the GeneralUser GS sound set. MIDI 2.0 adds 16-bit velocity and 256 channels (16 groups of 16), but it does not add named instruments.

As a result, players typically rely on guesses, such as treating channel 10 as drums, using piano when no program is given, or picking the closest available sample. MIDI 3.0 does not allow players to make these guesses. Older files are handled by a separate importer, which either converts them to MIDI 3.0 documents or reports why it cannot.

---

## 2. Conformance

The keywords MUST, MUST NOT, SHALL, SHALL NOT, SHOULD, and MAY are to be interpreted as described in RFC 2119.

### 2.1 Players

A player that claims MIDI 3.0 conformance:

1. MUST play only documents that conform to this specification.
2. MUST NOT use the MIDI channel to determine which instrument to play.
3. MUST NOT treat program numbers as instrument kinds.
4. MUST NOT substitute a different instrument when a required instrument is unavailable.
5. MUST log each missing instrument (with its TrackID and InstID) instead of producing a substitute sound.

### 2.2 Sample packs

A pack that claims MIDI 3.0 conformance MUST list every InstID it provides. An InstID the pack does not list is treated as unavailable; it MUST NOT be mapped to another instrument.

### 2.3 Importers

An importer converts other formats (such as SMF, SoundFont 2, or General MIDI tables) into MIDI 3.0 documents. An importer is not a player, and MAY use translation tables. After import, the resulting document identifies instruments only by TrackID and InstID.

---

## 3. Identifiers

All identifiers are unsigned 16-bit integers unless stated otherwise.

```
InstID   = (Family << 8) | Member     ; family 1..255, member 1..255; 0 = unset
TrackID  = 0..65535                   ; 0 is a valid track number
GroupID  = 0..65535                   ; 0 = no group
NoteId   = 1..65535                   ; 0 = not a note event
```

### 3.1 InstID (instrument kind)

An InstID identifies a kind of instrument, such as "flute" or "electric bass". It does not identify a manufacturer, a product, or a slot on a device.

- The family is the upper byte. For example, woodwinds are family 128.
- The member is the lower byte. For example, flute is member 128 of the woodwinds, giving InstID `0x8080`.
- Values may be allocated sparsely, leaving gaps for future additions. Packing values densely into the range 0–127 to mimic General MIDI numbering is not permitted.

The table that maps names to InstIDs is a data file (`schemas/opcode16.json` in this repository), not part of player code. Adding a new instrument kind means adding an entry to that file; players do not need to be rebuilt.

### 3.2 TrackID

A TrackID identifies one musical part in a song, such as the melody, the bass line, or the drum kit. It is not a MIDI channel. A song with 25 instruments has 25 tracks. If those parts were all on channel 1 in the original SMF, the channel number is dropped during import.

### 3.3 GroupID

A GroupID is optional. Groups are used for muting, soloing, and exclusive "choke" behavior (for example, a closed hi-hat cutting off an open hi-hat). A value of 0 means the track is not in a group.

### 3.4 NoteId

Each sounding note has its own NoteId, and a note-off message refers to that NoteId rather than to a note number and channel. This means two overlapping notes of the same pitch (for example, two D6s) can be ended independently.

---

## 4. Songs, instrument kinds, and packs

MIDI 3.0 keeps three kinds of information separate:

| Category | Contains | Example |
|---|---|---|
| Instrument kind | InstID and name | `calliope` = `0x1003` |
| Track | TrackID | "sung melody" |
| Realization | A pack and its samples | 48 kHz WAV files that provide `calliope` |

A **song** maps each track to an InstID (a name may be used in source form and converted to its InstID when the song is compiled).  
A **pack** maps each InstID it provides to its regions and samples.  
**Binding** is the step that checks whether the pack provides every InstID the song uses. If it does, the song can play. If it does not, the song does not play and the missing instruments are reported.

```
song  track 4  inst=calliope
pack  GeneralUser provides 0x1003
  → plays

song  track 4  inst=calliope
pack  PTQ (piano, whistle, …) does not provide calliope
  → bind fails; missing instrument reported
```

The same song can be used with different packs, as long as each pack provides the instruments the song needs. Songs do not contain bank or program numbers.

---

## 5. Instrument families (version 1)

The following family numbers are assigned:

| Family | Hex | Description |
|---:|---|---|
| 1 | `0x01` | Piano / acoustic keyboards |
| 2 | `0x02` | Electric keyboards |
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
| 19 | `0x13` | Effects / texture |
| 32 | `0x20` | Tuned percussion |
| 33 | `0x21` | Drum kit (one track; the note number selects the drum) |
| 34 | `0x22` | Single percussion instrument (its own track) |
| 48 | `0x30` | World / traditional |
| 128 | `0x80` | Woodwinds |
| 254 | `0xFE` | Analog oscillator |
| 255 | `0xFF` | Unpitched / noise |

Member number 0 is not allowed in version 1. New families may be added by extending `opcode16.json`; doing so does not change the rules in this document.

---

## 6. Song document

A song is a document that states all of its instruments and events explicitly.

### 6.1 Header

| Field | Type | Description |
|---|---|---|
| `name` | string | Title of the song |
| `rate` | u32 | Sample rate; always 48000 in version 1 |
| `tpqn` | u16 | Ticks per quarter note, if imported from SMF; otherwise 0 |
| `tracks[]` | Track | One entry per instrument |
| `events[]` | Event | Sorted by time, then by TrackID |

### 6.2 Track

| Field | Type | Description |
|---|---|---|
| `id` | TrackID | Numbered consecutively from 0 to N−1 |
| `name` | string | Optional display name |
| `inst` | InstID or name | Required if the track contains notes |
| `group` | GroupID | 0 = no group |
| `smf_ch` | u8 | Original SMF channel, kept for debugging only; ignored by players |

Each track uses exactly one instrument, so two instruments require two tracks. If the source file changes program while notes are still sounding, the importer reports an error. If the program changes during a silence, the importer may split the part into two tracks.

### 6.3 Events

Event times are measured in sample frames at the song's `rate`, so the audio output clock is the timing reference. Tick-based times from the original file may be kept as optional metadata.

| Event | Code | Data |
|---|---:|---|
| NOP | `0x00` | — |
| NOTE_ON | `0x10` | note u16, velocity u16, NoteId u16 |
| NOTE_OFF | `0x11` | NoteId u16 |
| CC | `0x20` | controller u16, value u16 |
| BEND | `0x21` | cents i16 |
| TEMPO | `0x30` | microseconds per quarter note u32 |
| END | `0x3F` | — |

The instrument is set on the track, not on each NOTE_ON.

**Note (u16):** The lower 8 bits (0–127) hold the MIDI note number, which is used to select the sample zone. The upper 8 bits are reserved and must be 0 in version 1.

**Velocity (u16):** 0 means note off.

**TEMPO:** Because event times are already in sample frames, TEMPO does not affect playback timing. It is informational, for editors and for converting back to beats and bars. Players MUST NOT use it to reschedule events.

**BEND:** A BEND event applies to every note currently sounding on its track. It is a signed offset in cents from the written pitch; 0 means no bend. Per-note bend is not part of version 1.

#### 6.3.1 Converting MIDI 1.0 values

Importers convert MIDI 1.0 values to MIDI 3.0 values as follows. Results are rounded to the nearest integer.

| MIDI 1.0 value | MIDI 3.0 value |
|---|---|
| Velocity `v` (7-bit, 1–127) | `round(v × 65535 / 127)`, so 127 becomes 65535 |
| Controller `v` (7-bit, 0–127) | `round(v × 65535 / 127)` |
| Controller pair MSB/LSB `v` (14-bit, 0–16383) | `round(v × 65535 / 16383)` |
| Pitch bend `b` (14-bit, 0–16383, center 8192), with bend range `r` semitones | `round((b − 8192) / 8192 × r × 100)` cents |

The bend range `r` is taken from RPN 0 (Pitch Bend Sensitivity) in the source file. If the file does not set it, `r` is 2 semitones, which is the MIDI 1.0 default.

Controller numbers keep their MIDI 1.0 meaning (for example, CC 7 is volume and CC 64 is sustain). Bank Select (CC 0 and CC 32) and RPN/NRPN messages are used during import and are not written to the song.

### 6.4 Percussion

### 6.4 Percussion

- **Drum kit:** Uses family `0x21`. The whole kit is one track, and the note number selects which drum plays (regions use `pitch_keytrack = 0`). The track names the kit it uses, such as `kit_standard`.
- **Single percussion instrument:** Uses family `0x22`. Each drum has its own track, for example when a snare part is written separately.
- When importing an SMF, notes on channel 10 are not assumed to be drums. If no kit is named (for example, in a songmap file), the import fails. Importers must not map channel 10 to bank 128, and must not set CC0 to 128 (CC0 only accepts 0–127 in MIDI 1.0).

### 6.5 Song file format

In version 1, a song is stored as a UTF-8 JSON file with the extension `.song.json`. A binary format may be defined later; it must carry the same information.

```json
{
  "format": "midi3.song.v1",
  "name": "Example",
  "rate": 48000,
  "tpqn": 480,
  "tracks": [
    { "id": 0, "name": "Bass", "inst": "bass_electric", "group": 0 },
    { "id": 1, "name": "Drums", "inst": "kit_standard", "group": 0 }
  ],
  "events": [
    { "t": 0,     "track": 0, "op": "NOTE_ON",  "note": 40, "vel": 52428, "nid": 1 },
    { "t": 0,     "track": 1, "op": "NOTE_ON",  "note": 36, "vel": 65535, "nid": 2 },
    { "t": 24000, "track": 0, "op": "NOTE_OFF", "nid": 1 },
    { "t": 24000, "track": 1, "op": "NOTE_OFF", "nid": 2 },
    { "t": 24000, "track": 0, "op": "END" }
  ]
}
```

- `t` is the event time in sample frames, as a non-negative integer.
- `op` is the event name from the table in section 6.3. Each event's data fields use the names shown: `note`, `vel`, `nid`, `cc`, `value`, `cents`, and `us_per_quarter` (for TEMPO).
- `inst` may be a name from `opcode16.json` or a numeric InstID. A player resolves names to InstIDs when it loads the song.
- An event may include an optional `tick` field holding its original tick time. Players ignore it.
- `smf_ch` may appear on a track for debugging. Players ignore it.
- Players MUST reject a file whose `format` they do not recognize.

---

## 7. Pack document (samples)

A pack is a directory of 48 kHz audio samples together with a table that maps each InstID to its regions.

Version 1 requires the following:

- **Sample rate:** All samples are 48000 Hz. Players do not resample during playback.
- **Pitch:** Playback pitch is `2^(semitones/12)`, calculated from the declared root note plus a signed cents offset. Cents are always signed; storing −1 cent as a large unsigned 32-bit value is an error.
- **Zone selection:** Which samples play is determined entirely by note number and velocity. Every matching layer plays. If no layer matches, the note is silent and a miss counter is incremented. Players do not fall back to the nearest sample.
- **Loops:** Loop points must be declared in the pack. Placeholder values such as `originalPitch = 60` are used as written; players do not adjust them to fit the key range.

### 7.1 Pack file format

In version 1, the pack's map is a UTF-8 JSON file named `pack.json`, stored in the pack directory. Sample paths are relative to that directory.

```json
{
  "format": "midi3.pack.v1",
  "name": "Example Pack",
  "rate": 48000,
  "instruments": [
    {
      "inst": "calliope",
      "regions": [
        {
          "sample": "calliope/C4.wav",
          "root": 60, "cents": 0,
          "lokey": 48, "hikey": 71,
          "lovel": 1, "hivel": 65535,
          "keytrack": 100,
          "loop": { "mode": "forward", "start": 1200, "end": 38400 }
        }
      ]
    }
  ]
}
```

| Region field | Meaning |
|---|---|
| `sample` | Path to a 48 kHz WAV file |
| `root` | MIDI note at which the sample plays at its recorded pitch |
| `cents` | Signed tuning offset in cents |
| `lokey`, `hikey` | Note range this region covers, inclusive |
| `lovel`, `hivel` | Velocity range this region covers, inclusive, in 16-bit velocity units |
| `keytrack` | Cents of pitch change per note away from `root`. 100 for normal pitched instruments, 0 for drum kits (the `pitch_keytrack = 0` case in section 6.4) |
| `loop` | Optional. `mode` is `none` or `forward`; `start` and `end` are sample frames |

The pack lists exactly the instruments it provides (section 2.2).

SoundFont 2 files, and other formats such as SFZ, may be converted into packs. After conversion, only `pack.json` and its samples are used at runtime.

---

## 8. Live messages (optional)

For live use, messages keep MIDI's compact, opcode-based layout. The following shows one way to fit them into a CAN frame:

```
29-bit ID:  priority:3 | TrackID:16 | op:8 | 0:2
8-byte data (NOTE_ON): note u16 | velocity u16 | NoteId u16 | reserved u16
```

Live note messages do not carry the instrument family or member. The receiver associates each TrackID with its InstID when the session starts. To change a track's instrument, start a new track rather than changing it mid-note.

---

## 9. Importing MIDI 1.0 files (informative)

This section describes a recommended import process. It is not a requirement.

1. Read the SMF (Type 0 or Type 1).
2. Split the file into parts: first by file track, then by channel within each file track. (A Type 0 file has one file track, so this splits it by channel.)
3. Split a part again wherever a Program Change occurs after the part has played notes and all its notes have ended. A Program Change while notes are still sounding is an error (section 6.2).
4. Number the resulting parts 0, 1, 2, and so on, in the order their first note appears. These are the TrackIDs. They are not channel numbers.
5. Choose each track's instrument. Use the name given in a songmap file if there is one. Otherwise, look up the part's Program Change in the `gm` table of `opcode16.json`. If neither is available, the import fails for that track.
6. Write a MIDI 3.0 song file (section 6.5). The original `.mid` file is treated as source material, not as something players read directly.

The `tools/midi3_songmap.py` script in this repository performs steps 1 to 4 and writes a songmap for a person to review and complete.

### 9.1 Songmap files

A songmap file states instrument assignments explicitly. Each line gives a TrackID, the part of the source file it came from, and its instrument:

```
# songmap v1
track 0  src=1:2  inst=bass_electric
track 1  src=2:1  inst=calliope
track 2  src=3:10  inst=kit_electronic
track 3  src=4:1@1920  inst=flute
```

`src` is written as `FILETRACK:CHANNEL`, where the file track is counted from 0 and the channel is the MIDI channel number from 1 to 16. When a part was split at a Program Change, `@TICK` gives the tick where that part starts. Lines beginning with `#` are comments.

### 9.2 The gm and kit tables

`opcode16.json` contains two tables that only importers use. Program numbers in both tables count from 0.

- The `gm` table maps a General MIDI program number to an instrument name.
- The `kit` table maps a GS drum-kit program number to a kit name. It is used only for a part that a person, or a songmap, has already identified as a drum kit. It is never used to decide that a part is a drum kit.

It is acceptable for these tables to be incomplete. If a General MIDI program (for example, program 4) has no entry, the track gets InstID 0 and is reported as `BIND_MISS`; it does not default to piano.

---

## 10. Diagnostics

A player SHALL report the following:

- `BIND_MISS track=N` — once for each track that has notes but no InstID.
- `BIND_EMPTY track=N inst=X` — when the loaded pack does not provide instrument X.

By default, a player SHALL NOT log details for every individual note or sample.

An importer SHALL report the following:

- `PC_UNMAPPED track=N prog=P` — when a part's Program Change has no entry in the `gm` table.
- `PC_WHILE_SOUNDING src=S tick=T prog=P` — when a Program Change occurs while notes are still sounding.
- `NO_KIT_NAME track=N` — when a part on MIDI channel 10 has no instrument named in a songmap.

---

## 11. Versioning

- This document is version 0.1. InstID `0x0000` remains reserved.
- The family numbers in Section 5 become permanent when version 1.0 is published.
- The `format` field of `opcode16.json` is `opcode16.v1`. Song files use `midi3.song.v1` and pack files use `midi3.pack.v1`.

---

## 12. References

- MIDI 1.0 Detailed Specification (MIDI Manufacturers Association)
- MIDI 2.0 and the Universal MIDI Packet (MIDI Manufacturers Association). Used here as a message format only, not for identifying instruments.
- SoundFont 2.04 (E-mu Systems). Used only as a source format for conversion into packs.
- Opcode16 data file: `schemas/opcode16.json` in this repository
