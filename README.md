# MIDI 3.0 (Opcode16)

This repository contains the draft MIDI 3.0 Opcode16 specification.

In earlier versions of MIDI, instruments are chosen by channel, program, and bank numbers, which can mean different sounds on different devices. MIDI 3.0 instead identifies each instrument by name, using a 16-bit ID. A song lists the instruments it needs, and a sample pack lists the instruments it provides. If the pack is missing an instrument the song needs, the player reports it instead of substituting another sound.

## Contents

- [SPEC.md](SPEC.md): the specification (draft 0.1)
- [schemas/opcode16.json](schemas/opcode16.json): instrument families, instrument names and IDs, and tables for importing General MIDI files
- [tools/midi3_songmap.py](tools/midi3_songmap.py): a helper script that reads a Standard MIDI File and creates a `.songmap` file listing the instrument for each track

This repository contains the specification only, not a player. AILANG SynthKit, a separate project, is one implementation.

## Author

Sean Collins, 2 Paws Machine and Engineering.

Everything in this repository (the spec, the data file, and the tool) is public domain under [CC0 1.0](LICENSE). Use it however you like.
