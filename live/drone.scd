// drone.scd — offline compile of the drone voice, a set of insertable effects,
// and a reverb send. Signal chain lives on one private bus:
//   droneVoice -> [ fx... ] -> fxReverb -> out 0
// The drone REPLACES the bus each block (clean chain source); every effect reads
// the bus and REPLACES it in place; reverb reads the final bus and writes hardware.
// All `var` declarations sit at the top of each function (sclang requires it).

(
var dir = (thisProcess.nowExecutingPath.dirname +/+ "defs");

// --- source: a breathing drone -------------------------------------------------
SynthDef(\droneVoice, { |out = 16, freq = 55, detune = 0.1, cutoff = 800, res = 0.3,
        sub = 0.3, noise = 0.05, drive = 1.0, lfoRate = 0.1, lfoDepth = 0.2,
        amp = 0.3, gate = 1|
    var lfo, osc, subosc, nz, sig, env;
    lfo = SinOsc.kr(lfoRate).range(1.0 - lfoDepth, 1.0);
    osc = Mix(Saw.ar(freq * [1.0, 1.0 + detune, 1.0 - detune])) * 0.33;
    subosc = SinOsc.ar(freq * 0.5) * sub;
    nz = PinkNoise.ar(noise);
    sig = osc + subosc + nz;
    sig = (sig * drive).tanh;
    sig = RLPF.ar(sig, (cutoff * lfo).clip(40, 18000), res.clip(0.05, 1.0));
    env = EnvGen.kr(Env.asr(2.0, 1.0, 3.0), gate, doneAction: 2);
    ReplaceOut.ar(out, (sig * env * amp).dup);   // REPLACE = fresh chain source
}).writeDefFile(dir);

// --- insert effects: read `bus`, process, ReplaceOut same `bus` ----------------
SynthDef(\fxDelay, { |bus = 16, time = 0.3, fb = 0.4, mix = 0.4|
    var dry, wet, dt;
    dry = In.ar(bus, 2);
    dt = fb.clip(0.0, 0.9).linlin(0.0, 0.9, 0.06, 6.0);   // feedback -> comb decay
    wet = CombC.ar(dry, 1.0, time.clip(0.001, 1.0), dt);
    ReplaceOut.ar(bus, (dry * (1.0 - mix)) + (wet * mix));
}).writeDefFile(dir);

SynthDef(\fxTremolo, { |bus = 16, rate = 5.0, depth = 0.5|
    var sig, m;
    sig = In.ar(bus, 2);
    m = SinOsc.kr(rate).range(1.0 - depth.clip(0.0, 1.0), 1.0);
    ReplaceOut.ar(bus, sig * m);
}).writeDefFile(dir);

SynthDef(\fxDrive, { |bus = 16, amount = 4.0, mix = 0.5|
    var dry, wet;
    dry = In.ar(bus, 2);
    wet = (dry * amount).tanh;
    ReplaceOut.ar(bus, (dry * (1.0 - mix)) + (wet * mix));
}).writeDefFile(dir);

// --- source voices: add signal (Out.ar) after the drone, before the effects ----
// A rhythmic drum voice: kick on the beat, hats on the offbeat, engine-timed.
SynthDef(\drumVoice, { |out = 16, bpm = 120, tone = 55, decay = 0.35, level = 0.5, hat = 0.3|
    var beat, clk, hatTrig, kfreq, kick, hh, sig;
    beat = bpm / 60;
    clk = Impulse.kr(beat);
    kfreq = EnvGen.ar(Env([tone * 4.0, tone], [0.07], \exp), clk);
    kick = SinOsc.ar(kfreq) * EnvGen.ar(Env.perc(0.005, decay), clk);
    hatTrig = Impulse.kr(beat * 2.0, 0.5);
    hh = HPF.ar(WhiteNoise.ar, 8000) * EnvGen.ar(Env.perc(0.001, 0.04), hatTrig) * hat;
    sig = (kick.tanh + hh) * level;
    Out.ar(out, sig.dup);
}).writeDefFile(dir);

// An 8-step note sequencer. Each stepN is a MIDI note (0 = rest); set them to
// "play notes". Runs at 8ths of bpm through its own saw + filter.
SynthDef(\seqVoice, { |out = 16, bpm = 120, cutoff = 2000, res = 0.3, amp = 0.3, decay = 0.25,
        step0 = 48, step1 = 0, step2 = 55, step3 = 0, step4 = 60, step5 = 0, step6 = 55, step7 = 0|
    var beat, clk, idx, notes, note, gate, freq, env, sig;
    beat = bpm / 60;
    clk = Impulse.kr(beat * 2.0);
    idx = Stepper.kr(clk, 0, 0, 7);
    notes = [step0, step1, step2, step3, step4, step5, step6, step7];
    note = Select.kr(idx, notes);
    gate = note > 0;                       // a step of 0 is a rest
    freq = note.max(1).midicps;
    env = EnvGen.ar(Env.perc(0.005, decay), Trig1.kr(clk * gate, 0.001));
    sig = Saw.ar(freq) * env;
    sig = RLPF.ar(sig, cutoff.clip(60, 12000), res.clip(0.05, 1.0));
    Out.ar(out, (sig * amp).dup);
}).writeDefFile(dir);

// --- stepped drum voices: each its own module, 16-step on/off pattern -----------
// Every voice self-clocks at bpm (16th notes), walks a 16-step gate, and triggers
// its drum sound on steps set to 1. Free-running by design — each voice on its own
// clock. step0..step15 are set individually via /n_set.
SynthDef(\kickVoice, { |out = 16, bpm = 120, tone = 50, decay = 0.3, level = 0.9,
        step0=1,step1=0,step2=0,step3=0,step4=1,step5=0,step6=0,step7=0,
        step8=1,step9=0,step10=0,step11=0,step12=1,step13=0,step14=0,step15=0|
    var clk, idx, steps, cur, trig, kfreq, env, sig;
    clk = Impulse.kr(bpm / 60 * 4);
    idx = Stepper.kr(clk, 0, 0, 15);
    steps = [step0,step1,step2,step3,step4,step5,step6,step7,
             step8,step9,step10,step11,step12,step13,step14,step15];
    cur = Select.kr(idx, steps);
    trig = clk * (cur > 0);
    kfreq = EnvGen.ar(Env([tone * 6, tone], [0.06], \exp), trig);
    env = EnvGen.ar(Env.perc(0.002, decay), trig);
    sig = (SinOsc.ar(kfreq) * env * 1.6).tanh;
    Out.ar(out, (sig * level).dup);
}).writeDefFile(dir);

SynthDef(\snareVoice, { |out = 16, bpm = 120, tone = 220, decay = 0.18, level = 0.7,
        step0=0,step1=0,step2=0,step3=0,step4=1,step5=0,step6=0,step7=0,
        step8=0,step9=0,step10=0,step11=0,step12=1,step13=0,step14=0,step15=0|
    var clk, idx, steps, cur, trig, env, body, noise, sig;
    clk = Impulse.kr(bpm / 60 * 4);
    idx = Stepper.kr(clk, 0, 0, 15);
    steps = [step0,step1,step2,step3,step4,step5,step6,step7,
             step8,step9,step10,step11,step12,step13,step14,step15];
    cur = Select.kr(idx, steps);
    trig = clk * (cur > 0);
    env = EnvGen.ar(Env.perc(0.002, decay), trig);
    body = SinOsc.ar(tone) * env * 0.5;
    noise = HPF.ar(WhiteNoise.ar, 1200) * env * 0.8;
    sig = (body + noise).tanh;
    Out.ar(out, (sig * level).dup);
}).writeDefFile(dir);

SynthDef(\hatVoice, { |out = 16, bpm = 120, tone = 9000, decay = 0.05, level = 0.4,
        step0=1,step1=0,step2=1,step3=0,step4=1,step5=0,step6=1,step7=0,
        step8=1,step9=0,step10=1,step11=0,step12=1,step13=0,step14=1,step15=0|
    var clk, idx, steps, cur, trig, env, sig;
    clk = Impulse.kr(bpm / 60 * 4);
    idx = Stepper.kr(clk, 0, 0, 15);
    steps = [step0,step1,step2,step3,step4,step5,step6,step7,
             step8,step9,step10,step11,step12,step13,step14,step15];
    cur = Select.kr(idx, steps);
    trig = clk * (cur > 0);
    env = EnvGen.ar(Env.perc(0.001, decay), trig);
    sig = HPF.ar(WhiteNoise.ar, tone.clip(2000, 16000)) * env;
    Out.ar(out, (sig * level).dup);
}).writeDefFile(dir);

SynthDef(\clapVoice, { |out = 16, bpm = 120, tone = 1500, decay = 0.2, level = 0.6,
        step0=0,step1=0,step2=0,step3=0,step4=1,step5=0,step6=0,step7=0,
        step8=0,step9=0,step10=0,step11=0,step12=1,step13=0,step14=0,step15=0|
    var clk, idx, steps, cur, trig, env, sig;
    clk = Impulse.kr(bpm / 60 * 4);
    idx = Stepper.kr(clk, 0, 0, 15);
    steps = [step0,step1,step2,step3,step4,step5,step6,step7,
             step8,step9,step10,step11,step12,step13,step14,step15];
    cur = Select.kr(idx, steps);
    trig = clk * (cur > 0);
    env = EnvGen.ar(Env.perc(0.003, decay), trig);
    sig = BPF.ar(WhiteNoise.ar, tone.clip(600, 3000), 0.6) * env * 2.0;
    Out.ar(out, (sig * level).dup);
}).writeDefFile(dir);

// --- sampling: rip a chunk of the live output, play it back as a looping voice --
// `capture` records the stereo master (bus `in` = 0) into `buf`, then frees itself
// when the buffer is full. `sampler` is a source voice that loops a captured buffer
// back onto the chain — the bridge from the free-running rack into fixed chunks.
SynthDef(\capture, { |buf = 0, in = 0|
    RecordBuf.ar(In.ar(in, 2), buf, loop: 0, doneAction: 2);
}).writeDefFile(dir);

SynthDef(\sampler, { |out = 16, buf = 0, rate = 1.0, amp = 0.5|
    var sig;
    sig = PlayBuf.ar(2, buf, rate * BufRateScale.kr(buf), loop: 1);
    Out.ar(out, (sig * amp));
}).writeDefFile(dir);

// --- CV modulators: control-rate sources for the patch graph --------------------
// These make NO audio. Each writes a control signal to a control bus (`out`); a
// target module then /n_maps one of its params to that bus, so the param moves on
// its own. This is the bridge from the fixed audio chain to a rewirable patch graph.
// They sit at the HEAD of the root group so their bus is fresh before anyone reads it.

// An LFO: a sine sweeping between lo..hi. On connect the engine sets lo/hi from the
// target param's range (a musical window around its current value), so mapping it
// onto e.g. drone.cutoff sweeps the filter without the user computing Hz.
SynthDef(\cvLfo, { |out = 0, rate = 1.0, lo = 0.0, hi = 1.0|
    Out.kr(out, SinOsc.kr(rate.clip(0.001, 60.0)).range(lo, hi));
}).writeDefFile(dir);

// An arpeggiator: walks a maj7 arpeggio (root, +4, +7, +12) at bpm and outputs the
// note as frequency (Hz). Map it onto a pitch param (drone.freq / seq is stepped)
// to turn a static voice into a moving line.
SynthDef(\cvArp, { |out = 0, bpm = 120, root = 48|
    var clk, idx, note;
    clk = Impulse.kr(bpm / 60 * 2);            // 8th-note steps
    idx = Stepper.kr(clk, 0, 0, 3);
    note = root + Select.kr(idx, [0, 4, 7, 12]);
    Out.kr(out, note.midicps);
}).writeDefFile(dir);

// --- master: stereo reverb + safety limiter ------------------------------------
SynthDef(\fxReverb, { |in = 16, out = 0, mix = 0.3, room = 0.7, damp = 0.5, amp = 0.9|
    var dry, wet;
    dry = In.ar(in, 2);
    wet = FreeVerb2.ar(dry[0], dry[1], mix, room, damp);
    wet = Limiter.ar(wet, 0.95);
    Out.ar(out, wet * amp);
}).writeDefFile(dir);

"[build] wrote drone + drum + kick + snare + hat + clap + seq + delay + tremolo + drive + capture + sampler + cvLfo + cvArp + reverb".postln;
0.exit;
)
