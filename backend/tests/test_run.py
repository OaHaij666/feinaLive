"""GameGraph 游玩测试"""

import asyncio, sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.ai.game_graph import GameGraph
from apps.ai.mcp.adapters.slay_the_spire import SlayTheSpireAdapter
from apps.ai.shared_context import SharedContext
from apps.config import config

async def main():
    print(f"model={config.game_model} 解说={config.game_commentary_eagerness} 记忆={config.game_memory_eagerness} 步间隔={config.game_min_step_interval}s")
    adapter = SlayTheSpireAdapter()
    shared = SharedContext()
    graph = GameGraph(adapter=adapter, shared_context=shared)
    if not await adapter.health_check():
        print("MCP 不可用"); return

    last_sig, stuck = "", 0
    for r in range(1, 51):
        t0 = time.time()
        s = await graph.run_once()
        el = time.time() - t0
        if not s or not s.game_state:
            await asyncio.sleep(1); continue

        raw = s.game_state.raw_state
        screen = raw.get("screen_type","?")
        floor = raw.get("floor","?")
        hp = raw.get("current_hp","?")
        turn = adapter.is_my_turn(s.game_state)
        phase = raw.get("room_phase","")

        print(f"R{r:2d} {screen:15s} flr={str(floor):3s} HP={hp} turn={turn} phase={phase} {el:.1f}s")

        if s.llm_response:
            print(f"    🤖 {s.llm_response.replace(chr(10),' ')[:120]}")
        if s.tool_calls and turn:
            names = [tc.get("name","?") for tc in s.tool_calls]
            special = [n for n in names if n in ("request_host_commentary","request_memory_update")]
            print(f"    🎮 {names}" + (f"  ⭐ {special}" if special else ""))

        mem = await shared.get_memory()
        if mem.core or mem.important:
            print(f"    🧠 core={mem.core[:50] if mem.core else '∅'}  important={mem.important[:50] if mem.important else '∅'}")

        sig = f"{screen}:{floor}:{phase}:{turn}"
        if sig == last_sig:
            stuck += 1
        else:
            stuck = 0
        last_sig = sig
        if stuck >= 15:
            print(f"    同状态持续{stuck}轮,退出")
            break

        await asyncio.sleep(1.5)

    print(f"结束: R{r} {screen} flr={floor}")

asyncio.run(main())
