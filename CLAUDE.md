# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`phonotaxis` is a Python framework for building and running behavioral
experiments (called **paradigms**) that combine a finite-state machine,
hardware I/O (Arduino), video tracking, and sound playback, with a PyQt6 GUI.
A paradigm is a single script that defines the experiment's trial logic; the
framework supplies the controller, GUI widgets, state machine, and hardware
modules around it.

## Setup

See `README.md` for installation instructions (conda on Windows;
virtualenvwrapper or uv on Linux). After installing, copy
`config_template.py` to `config.py` and edit rig settings (camera, Arduino
port, data path, etc.). For development without physical hardware, set
`HARDWARE_INTERFACE = 'emulator'` in `config.py` (see `phonotaxis/emulator.py`).

## Common commands

```bash
pytest tests/                       # run all unit tests
pytest tests/test_statemachine.py   # run tests for one module
pytest tests/ -v                    # verbose

python examples/example_gui_minimal.py   # sanity check the install
```

`examples/` contains runnable demonstrations of individual features
(state matrices, Arduino I/O, video tracking, sounds) and of full paradigms;
see `examples/README.md` for an index. `devel/` contains lower-level scripts
for exercising external libraries/devices directly (Arduino, cameras, sound)
during development of the framework itself — not part of the public API.
`old/` is legacy/superseded code kept for reference only; do not build on it.

## Architecture

### Core control flow

A paradigm script defines a `Paradigm(QMainWindow)` subclass with a fixed set
of lifecycle methods, wired up to a `SessionController`
(`phonotaxis/controller.py`):

```
start_session()
  -> prepare_next_trial(0)        builds the StateMatrix for trial 0
  -> controller runs the trial    state machine drives hardware/video per the matrix
  -> trial reaches an END state
  -> process_results()            classify the just-finished trial
  -> prepare_next_trial(n+1)      build the next trial's matrix
  -> ... repeat until max trials or stop_session()
  -> save_to_file()               write session data to HDF5
```

`SessionController` (in `controller.py`) intentionally merges what used to be
a separate model/controller split into one class: it owns trial bookkeeping,
timing, event logging, and data persistence, and is the single point of
control for start/stop (to avoid race conditions). `ControllerGUI` is the pure
view layer. The controller can be used headless (`create_gui=False`), which is
how it's exercised in `tests/test_controller.py`.

### State machine and state matrix

- `phonotaxis/statematrix.py` — `StateMatrix`: declarative definition of
  states for one trial. Each state has transitions (event -> next state),
  a timer ("Tup" event on expiry), outputs to turn on/off, and an optional
  integer output code (used to trigger sounds in other modules).
- `phonotaxis/statemachine.py` — `StateMachine`: executes a `StateMatrix`,
  consuming events and driving transitions/outputs in real time.
- Every declared input (video zone or Arduino pin) automatically produces two
  events: `{name}in` and `{name}out`. Event indices are ordered: video
  events, then Arduino events, then `Tup`, then any extra-timer events.
- See `docs/state_matrix_guide.md` for the full event/transition model and
  `docs/paradigm_guide.md` for how to structure a new paradigm file end to
  end (this is the canonical reference when adding a new paradigm).

### Hardware/IO modules

- `phonotaxis/arduinomodule.py` — Arduino-based digital/analog I/O (ports,
  valves, threshold-crossing detection on analog inputs).
- `phonotaxis/videomodule.py` — video tracking (e.g. via OpenCV) producing
  zone-entry/exit events for the state matrix.
- `phonotaxis/soundmodule.py` — sound stimulus generation/playback, typically
  triggered by a state's integer output code.
- `phonotaxis/emulator.py` — software stand-in for physical hardware, used
  when `config.HARDWARE_INTERFACE = 'emulator'`, so paradigms can be
  developed/tested without a rig.
- `phonotaxis/savedata.py` — writes session/trial/results data to HDF5.

### GUI layer

- `phonotaxis/gui.py` — generic, parameter-driven GUI building blocks: a
  `Container` that auto-detects whether a parameter should be tracked across
  trials (`history=True`, saved to `resultsData`) or just once
  (`history=False`, saved to `sessionData`); parameter widgets
  (`StringParam`, `NumericParam`, `MenuParam`); `Messenger` for Qt-signal-based
  logging; `create_app()` to bootstrap the PyQt6 application.
- `phonotaxis/widgets/` — higher-level reusable widgets built on top of `gui.py`
  (Arduino control panel, video display, sliders, session-info display).

### Paradigm file shape

Per `docs/paradigm_guide.md`, a paradigm file is structured as: imports and
constants -> sound ID constants -> input/output name lists -> a
`Paradigm(QMainWindow)` class implementing `__init__`, `start_session`,
`stop_session`, `prepare_next_trial`, `process_results`, `save_to_file`,
`closeEvent` -> `if __name__ == '__main__': create_app(Paradigm)`.
`examples/example_initzone_and_ports.py` is a worked example of a full state
matrix; `examples/example_gui_minimal.py` is the minimal smoke test for a GUI.
