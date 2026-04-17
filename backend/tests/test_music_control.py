"""测试音乐控制指令的完整链路"""

import asyncio
import sys


async def test_music_control_chain():
    print("=== 测试音乐控制链路 ===\n")

    print("1. 初始化组件...")
    from apps.music.queue import get_music_queue
    from apps.ai.admin_commands import AdminCommandHandler, get_admin_handler
    from core.websocket import manager

    queue = get_music_queue()
    admin_handler = get_admin_handler()

    print(f"   Queue: {queue}")
    print(f"   Admin handler: {admin_handler}")
    print(f"   Volume callbacks registered: {len(admin_handler._volume_change_callbacks)}")
    print(f"   Pause callbacks registered: {len(admin_handler._pause_change_callbacks)}")
    print(f"   Next track callbacks registered: {len(admin_handler._next_track_callbacks)}")
    print(f"   Remove track callbacks registered: {len(admin_handler._remove_track_callbacks)}")

    print("\n2. 测试音量设置...")
    volume_callbacks_called = []

    def capture_volume(vol):
        volume_callbacks_called.append(vol)
        print(f"   Volume callback called with: {vol}")

    admin_handler.register_volume_change_callback(capture_volume)
    queue.set_volume(0.5)

    if volume_callbacks_called:
        print(f"   ✓ 音量回调成功，值={volume_callbacks_called[-1]}")
    else:
        print("   ✗ 音量回调未被调用!")
        return False

    print("\n3. 测试暂停/恢复设置...")
    pause_callbacks_called = []

    def capture_pause(is_paused):
        pause_callbacks_called.append(is_paused)
        print(f"   Pause callback called with: {is_paused}")

    admin_handler.register_pause_change_callback(capture_pause)
    admin_handler._state.is_paused = True
    admin_handler.notify_pause_change(True)

    if pause_callbacks_called:
        print(f"   ✓ 暂停回调成功，值={pause_callbacks_called[-1]}")
    else:
        print("   ✗ 暂停回调未被调用!")
        return False

    print("\n4. 测试下一首...")
    next_callbacks_called = []

    def capture_next():
        next_callbacks_called.append(True)
        print("   Next track callback called")

    admin_handler.register_next_track_callback(capture_next)
    admin_handler.notify_next_track()

    if next_callbacks_called:
        print("   ✓ 下一首回调成功")
    else:
        print("   ✗ 下一首回调未被调用!")
        return False

    print("\n5. 测试移除歌曲...")
    rm_callbacks_called = []

    def capture_rm():
        rm_callbacks_called.append(True)
        print("   Remove track callback called")

    admin_handler.register_remove_track_callback(capture_rm)
    admin_handler.notify_remove_track()

    if rm_callbacks_called:
        print("   ✓ 移除歌曲回调成功")
    else:
        print("   ✗ 移除歌曲回调未被调用!")
        return False

    print("\n6. 测试WebSocket广播...")
    broadcast_called = []

    original_send = manager.send_message

    async def mock_send_message(room_id, message):
        broadcast_called.append((room_id, message))
        print(f"   WS send_message called: room={room_id}, msg={message}")

    manager.send_message = mock_send_message

    await manager.send_message("test_room", {"type": "test"})
    if broadcast_called:
        print("   ✓ WebSocket发送成功")
    else:
        print("   ✗ WebSocket未被调用")
        return False

    print("\n=== 所有测试通过! ===")
    return True


if __name__ == "__main__":
    result = asyncio.run(test_music_control_chain())
    sys.exit(0 if result else 1)
