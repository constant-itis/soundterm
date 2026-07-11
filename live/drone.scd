// drone.scd — offline compile of the live-drone voice + a reverb send.
// Two nodes wired through a private bus: droneVoice -> bus 16 -> fxReverb -> out 0.
// All `var` declarations sit at the top of each function (sclang requires it).

(
var dir = (thisProcess.nowExecutingPath.dirname +/+ "defs");

// A breathing drone: three detuned saws + sub sine + air, saturated, then a
// resonant low-pass whose cutoff is gently swept by an LFO so it never sits still.
SynthDef(\droneVoice, { |out = 16, freq = 55, detune = 0.1, cutoff = 800, res = 0.3,
        sub = 0.3, noise = 0.05, drive = 1.0, lfoRate = 0.1, lfoDepth = 0.2,
        amp = 0.3, gate = 1|
    var lfo, osc, subosc, nz, sig, env;
    lfo = SinOsc.kr(lfoRate).range(1.0 - lfoDepth, 1.0);
    osc = Mix(Saw.ar(freq * [1.0, 1.0 + detune, 1.0 - detune])) * 0.33;
    subosc = SinOsc.ar(freq * 0.5) * sub;
    nz = PinkNoise.ar(noise);
    sig = osc + subosc + nz;
    sig = (sig * drive).tanh;                                   // saturation
    sig = RLPF.ar(sig, (cutoff * lfo).clip(40, 18000), res.clip(0.05, 1.0));
    env = EnvGen.kr(Env.asr(2.0, 1.0, 3.0), gate, doneAction: 2);  // slow fade in/out
    Out.ar(out, (sig * env * amp).dup);
}).writeDefFile(dir);

// Stereo reverb send with a safety limiter on the master.
SynthDef(\fxReverb, { |in = 16, out = 0, mix = 0.3, room = 0.7, damp = 0.5, amp = 0.9|
    var dry, wet;
    dry = In.ar(in, 2);
    wet = FreeVerb2.ar(dry[0], dry[1], mix, room, damp);
    wet = Limiter.ar(wet, 0.95);
    Out.ar(out, wet * amp);
}).writeDefFile(dir);

"[build] wrote droneVoice + fxReverb".postln;
0.exit;
)
