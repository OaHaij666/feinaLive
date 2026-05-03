"""精确模拟 game_graph _llm_decide + _build_prompt"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.ai.game_graph import build_game_system_prompt
from apps.ai.client import ChatMessage, ChatRequest, get_game_ai_client
from apps.config import config

async def main():
    ai = get_game_ai_client()
    print(f"client: url={ai._api_url} model={ai._default_model} thinking={ai._disable_thinking}")

    # 模拟真实的 _build_prompt
    from apps.ai.mcp.client import MCPClient
    mcp = MCPClient(base_url=config.game_mcp_url)
    tools_raw = await mcp.get_tools()
    mcp_tools_list = tools_raw.get("tools", []) if isinstance(tools_raw, dict) else (tools_raw if isinstance(tools_raw, list) else [])

    # 构建 MCP 工具说明
    mcp_tool_lines = []
    for t in mcp_tools_list:
        fn = t.get("function", t)
        name = fn.get("name", t.get("name","?"))
        if name in ("request_host_commentary", "request_memory_update"):
            continue
        params = fn.get("parameters", fn.get("inputSchema", {}))
        props = params.get("properties", {})
        required = params.get("required", [])
        parts = []
        for pn, pi in props.items():
            desc = pi.get("description", "")
            if "enum" in pi:
                desc = "/".join(pi["enum"])
            m = "*" if pn in required else "?"
            parts.append(f"{m}{pn}={desc}")
        mcp_tool_lines.append(f"{name}: {', '.join(parts)}")

    # 获取真实游戏状态
    state_result = await mcp.call("tools/call", {"name": "get_screen_state", "arguments": {}})
    raw_state = {}
    if state_result and "content" in state_result:
        for item in state_result["content"]:
            if item.get("type") == "text":
                try:
                    raw_state = __import__('json').loads(item["text"])
                except:
                    pass

    # 模拟 _format_game_state
    from apps.ai.game_graph import GameGraph
    gs_text = GameGraph._format_game_state(raw_state, "")

    prompt = build_game_system_prompt(
        game_state=gs_text,
        commentary_eagerness=config.game_commentary_eagerness,
        memory_eagerness=config.game_memory_eagerness,
    )
    if mcp_tool_lines:
        prompt += "\n\n【可用MCP工具】\n" + "\n".join(mcp_tool_lines)

    print(f"prompt: {len(prompt)} chars")
    print(f"screen={raw_state.get('screen_type')} floor={raw_state.get('floor')}")

    # 发请求
    r = await ai.chat(ChatRequest(
        messages=[ChatMessage(role="system", content=prompt), ChatMessage(role="user", content="请返回JSON格式的决策，不要加任何解释。")],
        temperature=config.game_temperature, max_tokens=config.game_max_tokens
    ))
    if r and r.content:
        print(f"OK: {r.content[:150]}")
    else:
        print("FAIL: response is None/empty")
        # 试试无额外参数
        import httpx
        payload = {
            "model": ai._default_model,
            "messages": [{"role": "system", "content": "say ok"}, {"role": "user", "content": "ok"}],
            "temperature": 0.4,
            "max_tokens": 50,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ai._api_key}"}
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(f"{ai._api_url}/chat/completions", json=payload, headers=headers)
            print(f"bare status={resp.status_code} body={resp.text[:200]}")

asyncio.run(main())
