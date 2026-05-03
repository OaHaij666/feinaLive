"""测试杀戮尖塔 MCP - 完整打一关"""

import httpx
import json
import time

URL = "http://127.0.0.1:8080/mcp"
request_counter = 0


def send_request(method: str, params: dict = None):
    global request_counter
    request_counter += 1
    request = {
        "jsonrpc": "2.0",
        "id": request_counter,
        "method": method,
        "params": params or {},
    }
    with httpx.Client(timeout=15) as client:
        response = client.post(URL, json=request, headers={"Content-Type": "application/json"})
        return response.json()


def call_tool(name: str, arguments: dict = None):
    result = send_request("tools/call", {"name": name, "arguments": arguments or {}})
    if "result" in result:
        content = result["result"].get("content", [])
        for item in content:
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except:
                    return item["text"]
    return result


def get_state():
    return call_tool("get_screen_state")


def wait(delay: float = 1.5):
    time.sleep(delay)
    return get_state()


def print_state(state):
    print(f"\n屏幕: {state.get('screen_type')} | 楼层: {state.get('floor')} | HP: {state.get('current_hp')}/{state.get('max_hp')} | 金币: {state.get('gold')}")


def handle_combat():
    print("\n" + "=" * 50)
    print("进入战斗!")
    print("=" * 50)
    
    turn = 0
    while True:
        state = get_state()
        
        if not state.get("in_combat") and state.get("screen_type") != "NONE":
            print("战斗结束!")
            return state
        
        turn += 1
        print(f"\n--- 回合 {turn} ---")
        
        monsters = state.get("monsters", [])
        print(f"敌人:")
        for i, m in enumerate(monsters, 1):
            if not m.get("is_gone"):
                print(f"  [{i}] {m.get('name')}: HP {m.get('current_hp')}/{m.get('max_hp')} | 意图: {m.get('intent')}")
        
        hand = state.get("hand", [])
        energy = state.get("energy", 0)
        print(f"手牌 (费用: {energy}):")
        for i, card in enumerate(hand, 1):
            playable = "✓" if card.get("is_playable") else "✗"
            print(f"  {i}. {card.get('name')} ({card.get('cost')}) {playable}")
        
        actions = []
        remaining_energy = energy
        
        for card in hand:
            if remaining_energy <= 0:
                break
            if not card.get("is_playable"):
                continue
            
            cost = card.get("cost", 0)
            if cost > remaining_energy:
                continue
            
            if card.get("has_target"):
                for i, m in enumerate(monsters, 1):
                    if not m.get("is_gone"):
                        actions.append({"action": "play_card", "card_name": card.get("name"), "target_index": i})
                        remaining_energy -= cost
                        break
            else:
                actions.append({"action": "play_card", "card_name": card.get("name")})
                remaining_energy -= cost
        
        if actions:
            actions.append({"action": "end_turn"})
            print(f"执行动作: {len(actions)} 个")
            result = call_tool("execute_actions", {"actions": actions})
            print(f"结果: {result}")
        else:
            print("结束回合")
            result = call_tool("end_turn")
            print(f"结果: {result}")
        
        time.sleep(2)


def handle_reward():
    print("\n处理奖励...")
    state = get_state()
    
    if state.get("screen_type") == "COMBAT_REWARD":
        choices = state.get("choice_list", [])
        print(f"奖励选项: {choices}")
        
        for i, choice in enumerate(choices, 1):
            print(f"选择: {choice}")
            result = call_tool("choose", {"choice_index": i})
            print(f"结果: {result}")
            time.sleep(0.5)
        
        print("点击继续...")
        result = call_tool("proceed")
        print(f"结果: {result}")
        return wait()
    
    return state


def handle_card_reward():
    state = get_state()
    
    if state.get("screen_type") == "CARD_REWARD":
        choices = state.get("choice_list", [])
        print(f"\n卡牌奖励: {choices}")
        
        if choices:
            print(f"选择第一张卡...")
            result = call_tool("choose", {"choice_index": 1})
            print(f"结果: {result}")
            return wait()
    
    return state


def handle_map():
    state = get_state()
    
    if state.get("screen_type") == "MAP":
        print(f"\n选择地图节点...")
        result = call_tool("choose", {"choice_index": 1})
        print(f"结果: {result}")
        return wait(2)
    
    return state


def handle_event():
    state = get_state()
    
    if state.get("screen_type") == "EVENT":
        event_name = state.get("screen_state", {}).get("event_name", "未知事件")
        choices = state.get("choice_list", [])
        print(f"\n事件: {event_name}")
        print(f"选项: {choices}")
        
        if choices:
            print(f"选择选项 1...")
            result = call_tool("choose", {"choice_index": 1})
            print(f"结果: {result}")
            return wait()
    
    return state


def main():
    print("=" * 60)
    print("杀戮尖塔 MCP 完整测试 - 打一关")
    print("=" * 60)

    print("\n[初始化] 连接 MCP...")
    result = send_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    })
    server_info = result.get("result", {}).get("serverInfo", {})
    print(f"服务器: {server_info.get('name')} v{server_info.get('version')}")

    tools_result = send_request("tools/list")
    tools = tools_result.get("result", {}).get("tools", [])
    print(f"可用工具: {len(tools)} 个")

    state = get_state()
    print_state(state)

    if state.get("screen_type") == "MAIN_MENU":
        print("\n[开始游戏] 铁甲战士...")
        result = call_tool("start_game", {"character": "IRONCLAD"})
        print(f"结果: {result}")
        state = wait(2)

    while state.get("screen_type") == "EVENT":
        state = handle_event()

    floors_cleared = 0
    max_floors = 3

    while floors_cleared < max_floors:
        state = get_state()
        print_state(state)

        if state.get("in_combat") or (state.get("screen_type") == "NONE" and state.get("room_type") == "MonsterRoom"):
            state = handle_combat()
            floors_cleared += 1
            print(f"\n已清理 {floors_cleared}/{max_floors} 层")
            
            state = handle_reward()
            state = handle_card_reward()
        
        elif state.get("screen_type") == "MAP":
            state = handle_map()
        
        elif state.get("screen_type") == "EVENT":
            state = handle_event()
        
        elif state.get("screen_type") == "REST":
            print("\n休息点...")
            result = call_tool("choose", {"choice_index": 1})
            print(f"休息结果: {result}")
            result = call_tool("proceed")
            state = wait()
        
        else:
            print(f"\n未知屏幕类型: {state.get('screen_type')}")
            time.sleep(1)

    print("\n" + "=" * 60)
    print(f"测试完成! 清理了 {floors_cleared} 层")
    print("=" * 60)


if __name__ == "__main__":
    main()
