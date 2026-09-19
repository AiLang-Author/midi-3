# MIDI 3.0 (Opcode16)

This repository contains the MIDI 3.0 Opcode16 specification. It defines a 16-bit named instrument space in which tracks identify instruments by name, and sample packs provide the corresponding definitions.

- [SPEC.md](SPEC.md) — MIDI 3.0 draft 0.1
- [schemas/opcode16.json](schemas/opcode16.json) — family, kind, and GM-import tables (data, not code)
- [tools/midi3_songmap.py](tools/midi3_songmap.py) — helper for importing SMF files into the `.songmap` format

Author: Sean Collins, 2 Paws Machine and Engineering.
Specification text: [CC BY 4.0](LICENSE).

This repository is not a player. AILANG SynthKit is a separate implementation in another repository.
