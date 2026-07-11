# foundry

A prompt-driven modular audio foundry that lives in your terminal. You patch
blocks of sound together by talking; an agent wires the cables, forges new
instruments and effects, and mixes with its ears open — over a signal graph
you can diff, branch, and version like code.

> **Working name.** `foundry` collides with the Ethereum toolkit of the same
> name — pick a distinct name before publishing.

## Thesis

- **State is truth.** The session is a serializable node graph. The agent
  mutates the *graph*, never the audio; the engine reconciles to match it.
- **Borrow the muscle.** SuperCollider's `scsynth` is a headless audio server
  whose node graph is mutated live over OSC. We don't build DSP.
- **The agent is a peer editor.** It emits the same graph-ops your keyboard
  does, so every change is a visible diff.
- **Git for mixes.** Diffable text sessions → branch, log, review the AI's work.
- **Everything is a semantic token.** No hardcoded colors/glyphs in render code
  — every visual references a themeable token ("CSS for the TUI").

Full design brief and phased roadmap: see mycelium `#1783` / `#1784`.

## Phase 0 — the spike (this dir)

Proves the one load-bearing assumption: *can a non-sclang process drive scsynth
over OSC to make sound and mutate a running node's parameter live, glitch-free?*

### Prereqs

```bash
sudo apt install supercollider          # ships scsynth + sclang
# PipeWire already provides the JACK layer scsynth needs (no jackd required)
```

### Run

```bash
./spike/run_spike.sh
```

You should hear a saw voice with a smooth filter sweep — no clicks. If so,
Phase 0 passes and the whole architecture is green-lit.

### What's here

| file | role |
|------|------|
| `spike/build_defs.scd` | sclang **offline compiler** — writes `spikeVoice.scsyndef` |
| `spike/osc.py`         | pure-stdlib OSC 1.0 client (no pip deps) |
| `spike/drive.py`       | loads the def, starts a voice, sweeps cutoff live over OSC |
| `spike/run_spike.sh`   | compile → boot scsynth (via `pw-jack`) → drive → tear down |

The split — sclang compiles defs to disk, an external process drives scsynth —
is not throwaway: it's the real architecture in miniature.

## License

TBD (FOSS — MIT or GPL-3; scsynth itself is GPL-3).
