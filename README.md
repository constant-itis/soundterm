# soundterm

**A prompt-driven modular synth that lives in your terminal.** A living sound is
already playing when you open it; you reshape it by *talking*. An agent wires the
patch — sets params, adds voices and effects — by emitting the same graph-ops your
keyboard would, over OSC, to a headless [SuperCollider](https://supercollider.github.io/)
engine. The patch is plain state you can diff, save, and version like code.

```
> darker and more space
  darkening and widening the space
    drone.cutoff 700 → 400   reverb.mix 0.32 → 0.6
> add a drum beat around 100 bpm
  + added drum1 (drum)
> play a little minor riff on a sequencer
  + added seq1 (seq)
    seq1.step0 48 → 59   seq1.step2 55 → 52   seq1.cutoff 2000 → 800
```

## Why it's built this way

- **State is the source of truth.** The patch is a serializable node graph. The
  agent mutates the *graph*, never the audio; the engine reconciles the running
  sound to match. (Let the agent touch audio directly and you've built a demo.)
- **Borrow the muscle.** `scsynth` is a headless audio server whose node graph is
  mutated live over OSC — patching a running sound is its native mode. We don't
  write DSP.
- **The agent is a peer editor.** It emits the same ops the keyboard does, so every
  change is visible and reversible.
- **The engine owns time.** The sound never waits on the model; edits land live.
- **Swappable brain.** A local model (fast, free) or Claude via your subscription —
  no code change, switch it mid-session.

## Chain

```
drone ─▶ [ source voices: drum · seq ] ─▶ [ effects: delay · tremolo · drive ] ─▶ reverb ─▶ out
```

`drone` and `reverb` are fixed endpoints; everything between is added and removed by
conversation. Source voices add signal onto the bus; effects process it in place.

## Run it

```bash
sudo apt install supercollider          # ships scsynth + sclang
# PipeWire already provides the JACK layer scsynth needs (no jackd required)

cd live
./run.sh                                # local model (default)
SOUNDTERM_MODEL=haiku ./run.sh          # or drive it with Claude (subscription auth)
```

Then talk to it. `/help` lists commands.

| command | does |
|---|---|
| `<anything>` | describe how the sound should change → the agent |
| `/model <m>` | switch brain: `local` · `haiku` · `sonnet` · `opus` |
| `/state` | show the patch + chain |
| `/save [f]` | save the patch to JSON |
| `/panic` | duck to silence · `/quit` to leave |

Notes are MIDI numbers in the sequencer (c3 = 48, c4 = 60); Claude translates note
names reliably, the local model less so — use `/model haiku` for precise melodies.

## Layout

| path | role |
|---|---|
| `live/soundterm.py` | the REPL |
| `live/engine.py` | boots scsynth, wires the chain, reconciles params over OSC |
| `live/graph.py` | the patch state — single source of truth (params, modules, ranges) |
| `live/agent.py` | prompt → graph-ops; local-model or Claude-CLI backend |
| `live/osc.py` | pure-stdlib OSC 1.0 client (no dependencies) |
| `live/drone.scd` | the SynthDefs (drone, drum, seq, delay, tremolo, drive, reverb) |
| `spike/` | the Phase-0 proof: a bare process making + live-mutating sound over OSC |

No third-party Python packages — stdlib only.

## Status

Early. The drone + verbal control + drum + sequencer + effect chain all work. No TUI
yet (the REPL is the interface for now); no arrangement/song layer yet. The roadmap
is: a `ratatui` rack view, an agent that *builds* new SynthDefs, and an analysis loop
that gives the agent ears.

## License

TBD — MIT for this code is the intent. Note `scsynth` itself is GPL-3.
