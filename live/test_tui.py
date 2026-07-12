#!/usr/bin/env python3
"""Headless check of the TUI wiring: boot, panels mount, a click adds a module, a
simulated agent op applies. Textual's run_test drives the app without a real term.
Makes a few seconds of audio."""
import asyncio
from tui import Soundterm, ModulePanel, ParamRow, StepRow


async def main():
    app = Soundterm(model="local")
    async with app.run_test() as pilot:
        for _ in range(40):                       # wait for the boot worker + panels
            await pilot.pause()
            await asyncio.sleep(0.3)
            if len(app.query(ModulePanel)) >= 2:
                break
        base = len(app.query(ModulePanel))
        print("panels after boot:", base)

        await pilot.click("#add-drum")            # clickable add
        await pilot.pause(); await asyncio.sleep(0.4)
        print("panels after +drum:", len(app.query(ModulePanel)))

        app._apply_ops([{"op": "set", "node": "drone", "param": "cutoff", "value": 300}], "darker")
        await pilot.pause()
        print("status:", app.last_status)
        row = app.query_one("#row-drone-cutoff", ParamRow)
        print("drone.cutoff now:", row._value)
        assert base >= 2 and len(app.query(ModulePanel)) == base + 1, "wiring check failed"
        assert row._value == 300, "param set did not reflect in the bar"
        print("OK — TUI wiring good")

        # start/stop: stop the drum then start it; enabled flips, panel restyles,
        # the bar keeps its stored value (non-destructive)
        drum_panel = app.query_one("#panel-drum1", ModulePanel)
        level_row = app.query_one("#row-drum1-level", ParamRow)
        stored = level_row._value
        app._apply_ops([{"op": "toggle", "node": "drum", "value": False}], "stop drum")
        await pilot.pause()
        assert app.graph.is_enabled("drum1") is False, "toggle off did not take"
        assert drum_panel.has_class("stopped"), "stopped panel not restyled"
        assert level_row._value == stored, "stop must not change the stored value"
        app._apply_ops([{"op": "toggle", "node": "drum1", "value": True}], "start drum")
        await pilot.pause()
        assert app.graph.is_enabled("drum1") is True, "toggle on did not take"
        assert not drum_panel.has_class("stopped"), "started panel still styled stopped"
        # space on a focused ParamRow toggles its module
        level_row.focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert app.graph.is_enabled("drum1") is False, "space did not stop the module"
        print("OK — start/stop toggle good")

        # sampling: rip a short chunk -> a looping sampler module appears, bound to a buffer
        before = len(app.query(ModulePanel))
        app._apply_ops([{"op": "sample", "seconds": 0.4}], "sampling")
        for _ in range(25):                       # wait out the record + the finish timer
            await pilot.pause()
            await asyncio.sleep(0.1)
            if len(app.query(ModulePanel)) > before:
                break
        assert len(app.query(ModulePanel)) == before + 1, "sampler module did not appear"
        samp = [m for m in app.graph.modules if m["type"] == "sampler"]
        assert samp and samp[0].get("buf") is not None, "sampler not bound to a buffer"
        assert app.query_one(f"#panel-{samp[0]['key']}", ModulePanel), "no sampler panel"
        print("OK — sampling good")

        # granular drums: a kick voice with a compact 16-step lane, agent edits a step
        app._apply_ops([{"op": "add", "type": "kick"}], "add kick")
        await pilot.pause(); await asyncio.sleep(0.3)
        kv = [m for m in app.graph.modules if m["type"] == "kick"]
        assert kv, "kick voice not added"
        kk = kv[0]["key"]
        assert app.query_one(f"#steprow-{kk}", StepRow), "no compact step lane for kick"
        assert app.graph.node_params(kk)["step0"] == 1.0, "default four-on-floor missing"
        app._apply_ops([{"op": "set", "node": kk, "param": "step2", "value": 1}], "add a hit")
        await pilot.pause()
        assert app.graph.node_params(kk)["step2"] == 1.0, "agent step edit did not take"
        print("OK — granular drums good")


if __name__ == "__main__":
    asyncio.run(main())
