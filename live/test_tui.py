#!/usr/bin/env python3
"""Headless check of the TUI wiring: boot, panels mount, a click adds a module, a
simulated agent op applies. Textual's run_test drives the app without a real term.
Makes a few seconds of audio."""
import asyncio
from tui import Soundterm, ModulePanel, ParamRow


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


if __name__ == "__main__":
    asyncio.run(main())
