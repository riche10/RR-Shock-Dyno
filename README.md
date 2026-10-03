# Rebel Racing Shock Dyno

This repository preserves my UNLV Rebel Racing shock-dyno software prototype, saved development data, dependency records, and technical handoff.

## Status

I left this at a Python simulation and offline-analysis prototype. GUI recording, raw/processed CSVs, plotting, MoTeC import, and offline software checks work. The supplied app has no implemented Teensy DAQ or motor/VFD interface, completed hardware calibration, or packaged `.exe`.

Saved dyno data is consistent with the simulator, not evidence of completed physical shock testing. The physical concept included a three-phase motor, GS20 VFD, reduction/crank/yoke, Teensy DAQ, Hall RPM, and force/position sensors; those hardware interfaces are not implemented here.

**First next step: decide whether the test program is still wanted.** If it is, establish hardware ownership/readiness and acquisition/calibration requirements before resuming development or commissioning the rig.

## Start here

- [Technical handoff and run instructions](HANDOFF.txt)
- [Preserved Python project](RR%20ShockDyno)
- [Original data and plots](RR%20ShockDyno/data)
- [Source inventory, dependency versions and offline checks](Verification)
- [Packaged Drive handoff](https://drive.google.com/drive/folders/1oOemWlCo05pJy6oL6FYz54XSMOxjRJGe)
- [Master archive README](https://docs.google.com/document/d/1wWvU6Ll4SLVT-M2jH4OgtgGK3EwZ3h_DStmwN0HF24g/edit)

```text
git clone https://github.com/riche10/RR-Shock-Dyno.git
```

Work on a copy or fork and record subsequent changes and test results. Original project files, including empty placeholders and saved development outputs, remain preserved. Local virtual environments are inventoried, not shipped as portable apps. This repository starts with the supplied handoff snapshot, not reconstructed development commits. No additional project-wide license has been added.

My other Baja projects: [ECVT](https://github.com/riche10/RR-ECVT) · [RR LoRa](https://github.com/riche10/RR-LoRa).
