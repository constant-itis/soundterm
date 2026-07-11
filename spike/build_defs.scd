// build_defs.scd — offline SynthDef compiler.
// Runs under sclang WITHOUT booting the server. Writes a compiled .scsyndef
// blob to disk. This IS the real architecture: sclang is a build-time
// compiler, scsynth is a dumb renderer we drive over OSC from another process.

(
var dir = (thisProcess.nowExecutingPath.dirname +/+ "defs");

// A single voice: saw -> resonant low-pass -> ASR env -> stereo out.
// `cutoff` is the param we'll sweep live over OSC to test glitch-free mutation.
SynthDef(\spikeVoice, { |out = 0, freq = 110, cutoff = 400, rq = 0.3, amp = 0.2, gate = 1|
    // sclang requires all `var` declarations at the top of the function.
    var sig, env;
    sig = Saw.ar(freq) * amp;
    sig = RLPF.ar(sig, cutoff.clip(40, 18000), rq);
    env = EnvGen.kr(Env.asr(0.01, 1.0, 0.25), gate, doneAction: 2);
    Out.ar(out, (sig * env).dup);
}).writeDefFile(dir);

("[build] wrote " ++ dir +/+ "spikeVoice.scsyndef").postln;
0.exit;
)
