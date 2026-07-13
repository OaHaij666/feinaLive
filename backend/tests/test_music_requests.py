from apps.live.music_requests import parse_music_request


def test_music_request_parser_requires_an_explicit_command_for_plain_text():
    assert parse_music_request("这首歌真好听", "viewer") is None
    request = parse_music_request("点歌 晴天", "viewer", request_id="message-1")
    assert request is not None
    assert request.query == "晴天"
    assert request.request_id == "message-1"


def test_play_prefix_requires_whitespace_to_avoid_intercepting_normal_chat():
    assert parse_music_request("播放量突破一百万", "viewer") is None
    request = parse_music_request("播放 晴天", "viewer")
    assert request is not None and request.query == "晴天"
