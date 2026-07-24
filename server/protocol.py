"""
联网对战消息协议定义
"""
from __future__ import annotations
from typing import Any, Dict
from game.entities import Tile
from game.state import GameState, GamePhase
from game.logic import FanResult


# ===================== 消息类型 =====================

# 客户端 → 服务器
C_CREATE_ROOM = "create_room"        # 创建房间
C_JOIN_ROOM = "join_room"            # 加入房间 {room_id, name}
C_ACTION = "action"                   # 操作 {action, tile?, tiles?}
C_READY = "ready"                     # 准备/取消准备
C_CONTINUE = "continue"               # 继续/退出 {action: "continue"|"quit"}

# 服务器 → 客户端
S_ROOM_CREATED = "room_created"       # 房间已创建 {room_id}
S_PLAYER_JOINED = "player_joined"     # 玩家加入 {seat, name}
S_GAME_START = "game_start"           # 游戏开始 {seat, players, dealer, hun_tile}
S_DRAW_TILE = "draw_tile"             # 摸牌 {tile} (仅发给摸牌者)
S_STATE_UPDATE = "state_update"       # 状态更新 {phase, current_player, ...}
S_ACTION_NEEDED = "action_needed"     # 需要操作 {actions, tile?}
S_ACTION_BROADCAST = "action_broadcast"  # 操作广播 {seat, action, tile?, tiles?}
S_DISCARD_BROADCAST = "discard_broadcast"  # 出牌广播 {seat, tile}
S_GAME_OVER = "game_over"             # 游戏结束 {winner, fan_result}
S_READY_STATUS = "ready_status"       # 准备状态 {ready_seats, human_count, ready_count}
S_CONTINUE_NEEDED = "continue_needed" # 需要选择继续/退出
S_CONTINUE_RESULT = "continue_result" # 继续结果 {all_continue: bool, message: str}
S_ERROR = "error"                     # 错误 {message}


def tile_to_dict(tile: Tile) -> Dict[str, int]:
    return {"suit": tile.suit, "value": tile.value}


def dict_to_tile(d: Dict[str, int]) -> Tile:
    return Tile(d["suit"], d["value"])


def encode_public_state(game: GameState, seat: int) -> Dict[str, Any]:
    """编码公开的游戏状态（发送给指定座位的玩家）"""
    p = game.players[seat]
    return {
        "phase": game.phase.name,
        "current_player": game.current_player,
        "current_turn": game.current_turn,
        "hun_tile": tile_to_dict(game.hun_tile) if game.hun_tile else None,
        "hun_indicator": tile_to_dict(game.hun_indicator) if game.hun_indicator else None,
        "deck_size": len(game.deck),
        "discard_pile": [tile_to_dict(t) for t in game.discard_pile],
        "hand": [tile_to_dict(t) for t in p.hand_tiles],
        "melds": [_encode_meld(m) for m in p.melds],
        "all_melds": [[_encode_meld(m) for m in game.players[i].melds] for i in range(4)],
        "discards": [tile_to_dict(t) for t in p.discards],
        "is_dealer": p.is_dealer,
        "just_drew": game.just_drew,
        "last_discard": tile_to_dict(game.last_discard) if game.last_discard else None,
        "last_discard_player": game.last_discard_player,
    }


def encode_players_info(game: GameState) -> list:
    """编码所有玩家的公开信息"""
    return [
        {"seat": i, "name": config.PLAYER_NAMES[i], "hand_count": len(p.hand_tiles),
         "meld_count": len(p.melds), "discard_count": len(p.discards),
         "is_dealer": p.is_dealer}
        for i, p in enumerate(game.players)
    ]


def encode_fan_result(fan: FanResult) -> Dict[str, Any]:
    if fan is None:
        return None
    return {
        "total_fan": fan.total_fan,
        "total_score": fan.total_score,
        "details": dict(fan.details),
        "gun_count": fan.gun_count,
        "kong_score": fan.kong_score,
        "base_score": fan.base_score,
    }


def _encode_meld(meld) -> Dict[str, Any]:
    return {
        "type": meld.meld_type,
        "tiles": [tile_to_dict(t) for t in meld.tiles],
        "source_seat": meld.source_seat,
    }


from game import config
