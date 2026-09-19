# MIDI 3.0 (Opcode16)

**MIDI 1.0/2.0 kept a good event shape and a bad identity model.** This repository is the specification for a 16-bit named instrument space: tracks declare instruments by name, sample packs implement those names, bind is set intersection, missing bind fails instead of playing piano.

- **[SPEC.md](SPEC.md)** — MIDI 3.0 draft 0.1  
- **[schemas/opcode16.json](schemas/opcode16.json)** — family / kind / GM-import tables (data, not code)  
- **[tools/midi3_songmap.py](tools/midi3_songmap.py)** — SMF → `.songmap` importer helper  

Author: Sean Collins, 2 Paws Machine and Engineering.  
Specification text: [CC BY 4.0](LICENSE).

This is not a player. AILANG SynthKit is one implementation (separate repo).
