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

        # CV modulation (patch graph): add an lfo, cable it onto drone.cutoff so the
        # filter sweeps; the target bar shows as driven and can't be dragged. Then an
        # arp onto drone.freq. Disconnect restores the bar.
        app._apply_ops([{"op": "add", "type": "lfo"}], "add lfo")
        await pilot.pause(); await asyncio.sleep(0.3)
        lfos = [m for m in app.graph.modules if m["type"] == "lfo"]
        assert lfos and lfos[0]["role"] == "cv", "lfo not added as a cv module"
        lkey = lfos[0]["key"]
        assert app.query_one(f"#panel-{lkey}", ModulePanel), "no lfo panel"
        assert app.query_one(f"#row-{lkey}-rate", ParamRow), "lfo has no rate bar"

        cutoff_row = app.query_one("#row-drone-cutoff", ParamRow)
        app._apply_ops([{"op": "connect", "src": lkey, "node": "drone", "param": "cutoff"}], "sweep it")
        await pilot.pause()
        assert app.graph.is_modulated("drone", "cutoff"), "edge not recorded in graph"
        assert lfos[0].get("cvbus") is not None, "lfo never got a control bus"
        assert cutoff_row._mod_src == lkey, "target bar not marked modulated"
        # a modulated param must ignore drag (an /n_set would unmap the cable)
        cutoff_row._value = 999.0
        cutoff_row.on_mouse_down(type("E", (), {"x": 30})())
        assert cutoff_row._value == 999.0, "modulated bar should not respond to drag"
        # the engine must skip pushing a modulated param
        app.engine.push("drone", "cutoff", 123.0)   # no-op while modulated

        app._apply_ops([{"op": "add", "type": "arp"}], "add arp")
        await pilot.pause(); await asyncio.sleep(0.3)
        arps = [m for m in app.graph.modules if m["type"] == "arp"]
        assert arps, "arp not added"
        akey = arps[0]["key"]
        app._apply_ops([{"op": "connect", "src": akey, "node": "drone", "param": "freq"}], "arp pitch")
        await pilot.pause(); await asyncio.sleep(0.6)     # let the arp walk a few notes
        assert app.graph.is_modulated("drone", "freq"), "arp edge not recorded"
        assert app.query_one("#row-drone-freq", ParamRow)._mod_src == akey, "freq not marked"

        app._apply_ops([{"op": "disconnect", "src": lkey, "node": "drone", "param": "cutoff"}], "unpatch")
        await pilot.pause()
        assert not app.graph.is_modulated("drone", "cutoff"), "disconnect left the edge"
        assert cutoff_row._mod_src is None, "target bar still marked after disconnect"
        # removing a cv source pulls its remaining cables
        app._apply_ops([{"op": "remove", "node": akey}], "yank arp")
        await pilot.pause()
        assert not app.graph.is_modulated("drone", "freq"), "removing arp left it modulating"
        assert app.query_one("#row-drone-freq", ParamRow)._mod_src is None, "freq still driven"
        print("OK — cv modulation good")

        # mouse patching: right-click menus emit the SAME connect/disconnect ops. lfo1
        # still exists (unconnected). A right-clicked un-modulated param offers "patch
        # from <src>" + add-and-patch shortcuts; a modulated one offers only "unpatch".
        from tui import ContextMenu
        assert any(m["type"] == "lfo" for m in app.graph.modules), "expected a leftover lfo"
        items = app._param_menu_items("drone", "res")
        labels = [l for l, _ in items]
        assert any(l.startswith("◦ patch from") for l in labels), labels
        assert any("＋" in l and "lfo" in l for l in labels), "no add-and-patch shortcut"
        next(cb for l, cb in items if l.startswith("◦"))()      # pick "patch from lfoN"
        await pilot.pause()
        assert app.graph.is_modulated("drone", "res"), "menu patch did not connect"
        assert app.query_one("#row-drone-res", ParamRow)._mod_src is not None, "bar not marked"
        # a modulated param's menu is unpatch-only (n_map takes one source)
        mitems = app._param_menu_items("drone", "res")
        assert mitems and all(l.startswith("✕ unpatch") for l, _ in mitems), mitems
        mitems[0][1]()                                          # unpatch
        await pilot.pause()
        assert not app.graph.is_modulated("drone", "res"), "menu unpatch did not disconnect"

        # a genuine RIGHT-click on a param bar (button 3) routes to the menu
        fake = type("E", (), {"button": 3, "screen_x": 6, "screen_y": 4,
                              "x": 6, "y": 0, "stop": lambda self: None})()
        app.query_one("#row-drone-res", ParamRow).on_mouse_down(fake)
        await pilot.pause()
        assert app.query(ContextMenu), "right-click did not open a menu"
        app._close_menu()
        await pilot.pause()

        # the menu widget mounts + positions without error, and dismisses
        app.open_param_menu("drone", "cutoff", 6, 4)
        await pilot.pause()
        assert app.query(ContextMenu), "context menu did not mount"
        app._close_menu()
        await pilot.pause()
        assert not app.query(ContextMenu), "menu did not dismiss"

        # add-and-patch in one gesture: a new lfo appears AND drives the param
        n_lfo = len([m for m in app.graph.modules if m["type"] == "lfo"])
        addcb = next(cb for l, cb in app._param_menu_items("drone", "cutoff")
                     if "＋" in l and "lfo" in l)
        addcb()
        await pilot.pause(); await asyncio.sleep(0.2)
        assert len([m for m in app.graph.modules if m["type"] == "lfo"]) == n_lfo + 1, "no new lfo"
        assert app.graph.is_modulated("drone", "cutoff"), "add-and-patch did not connect"

        # module menu: fixed endpoints can't be removed; a real module can
        assert not any("remove" in l for l, _ in app._module_menu_items("drone")), "drone removable!"
        km = [m for m in app.graph.modules if m["type"] == "kick"][0]["key"]
        rm = next(cb for l, cb in app._module_menu_items(km) if "remove" in l)
        rm()
        await pilot.pause()
        assert not any(m["key"] == km for m in app.graph.modules), "menu remove failed"
        print("OK — mouse patching menus good")

        # live meters + step playhead: the master meter reads L/R levels, and an
        # enabled drum lane advances a playhead cursor at its tempo (parked when stopped)
        l, r = app.engine.read_levels()
        assert isinstance(l, float) and isinstance(r, float), "meter did not read levels"
        app._update_meter(0.5, 0.85)                    # renders without error
        app._apply_ops([{"op": "add", "type": "kick"}], "kick for playhead")
        await pilot.pause(); await asyncio.sleep(0.2)
        kp = [m for m in app.graph.modules if m["type"] == "kick"][0]["key"]
        sr = app.query_one(f"#steprow-{kp}", StepRow)
        app._t0 = 0.0
        app._tick_playheads()
        await pilot.pause()
        assert 0 <= sr._play < len(sr.vals), "playhead did not advance on enabled lane"
        app._apply_ops([{"op": "toggle", "node": kp, "value": False}], "stop")
        await pilot.pause()
        app._tick_playheads()
        assert sr._play == -1, "stopped lane should park the playhead"
        print("OK — meters + playhead good")

        # save / load a whole patch: build something distinctive, save, wreck it, reload
        import os as _os
        import tempfile
        app._apply_ops([{"op": "add", "type": "delay"}], "add delay")
        await pilot.pause(); await asyncio.sleep(0.2)
        dkey = [m for m in app.graph.modules if m["type"] == "delay"][0]["key"]
        app._apply_ops([{"op": "set", "node": dkey, "param": "mix", "value": 0.77}], "")
        app._apply_ops([{"op": "set", "node": "drone", "param": "cutoff", "value": 456}], "")
        await pilot.pause()
        n_mods = len(app.graph.modules)
        saved_edges = [dict(e) for e in app.graph.edges]
        tmp = _os.path.join(tempfile.gettempdir(), "soundterm_test_patch.json")
        app.graph.save(tmp)
        app._apply_ops([{"op": "set", "node": "drone", "param": "cutoff", "value": 40}], "wreck")
        app.graph.load(tmp)                             # reload the saved patch
        app.engine.rebuild_from_graph()
        await app._rebuild_rack()
        await pilot.pause(); await asyncio.sleep(0.3)
        assert len(app.graph.modules) == n_mods, "module count changed across save/load"
        assert app.graph.node_params("drone")["cutoff"] == 456.0, "param not restored"
        dk2 = [m for m in app.graph.modules if m["type"] == "delay"][0]["key"]
        assert abs(app.graph.node_params(dk2)["mix"] - 0.77) < 1e-6, "module param not restored"
        assert [dict(e) for e in app.graph.edges] == saved_edges, "edges not restored"
        assert app.query_one("#panel-drone", ModulePanel), "rack not rebuilt after load"
        _os.remove(tmp)
        print("OK — save/load good")


if __name__ == "__main__":
    asyncio.run(main())
