"""
鞍山麻将 - WebSocket 游戏服务器
"""
from __future__ import annotations
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets
from typing import Dict, Optional
from server.room import Room, _gen_room_id
from server.protocol import (
    C_CREATE_ROOM, C_JOIN_ROOM, C_ACTION, C_READY, C_CONTINUE,
    S_ROOM_CREATED, S_ERROR, S_READY_STATUS,
)


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.rooms: Dict[str, Room] = {}

    async def handle_client(self, websocket):
        """处理客户端连接"""
        current_room: Optional[Room] = None
        current_seat: Optional[int] = None

        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": S_ERROR, "message": "无效消息格式"}))
                    continue

                msg_type = msg.get("type", "")

                if msg_type in (C_CREATE_ROOM, C_JOIN_ROOM):
                    if current_room:
                        await websocket.send(json.dumps({"type": S_ERROR, "message": "已在房间中"}))
                        continue
                    room_id = msg.get("room_id", "").upper().strip()
                    if not room_id:
                        room_id = _gen_room_id()
                    room = self.rooms.get(room_id)
                    if room:
                        # 加入已有房间
                        if room.is_full:
                            await websocket.send(json.dumps({"type": S_ERROR, "message": "房间已满"}))
                            continue
                        if room._running:
                            await websocket.send(json.dumps({"type": S_ERROR, "message": "游戏已开始"}))
                            continue
                        seat = room.add_player(websocket, msg.get("name", "玩家"))
                        current_room = room
                        current_seat = seat
                        await websocket.send(json.dumps({
                            "type": S_ROOM_CREATED,
                            "room_id": room_id,
                            "seat": seat,
                        }))
                        # 广播玩家加入
                        await room.broadcast({
                            "type": "player_joined",
                            "seat": seat,
                            "name": msg.get("name", "玩家"),
                            "player_count": room.player_count,
                        }, exclude_seat=seat)
                        print(f"[房间 {room_id}] 玩家 {seat} ({msg.get('name','')}) 加入 ({room.player_count}/4)")
                        # 广播最新准备状态
                        await room._broadcast_ready_status()
                    else:
                        # 创建新房间
                        new_room = Room()
                        new_room.room_id = room_id  # 使用用户指定的房间号
                        seat = new_room.add_player(websocket, msg.get("name", "玩家"))
                        current_room = new_room
                        current_seat = seat
                        self.rooms[room_id] = new_room
                        await websocket.send(json.dumps({
                            "type": S_ROOM_CREATED,
                            "room_id": room_id,
                            "seat": seat,
                        }))
                        print(f"[房间 {room_id}] 创建成功，玩家 {seat} ({msg.get('name','')}) 加入")
                        # 进入等待准备阶段
                        asyncio.create_task(new_room.lobby_loop())

                elif msg_type == C_READY:
                    if current_room and current_seat is not None:
                        current_room.toggle_ready(current_seat)
                        await current_room._broadcast_ready_status()

                elif msg_type == C_ACTION:
                    if current_room and current_seat is not None:
                        # 路由消息到房间的玩家队列
                        current_room.route_message(current_seat, msg)

                elif msg_type == C_CONTINUE:
                    if current_room and current_seat is not None:
                        current_room.route_message(current_seat, msg)

                else:
                    await websocket.send(json.dumps({"type": S_ERROR, "message": f"未知消息类型: {msg_type}"}))

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if current_room and current_seat is not None:
                print(f"[房间 {current_room.room_id}] 玩家 {current_seat} 断线")
                current_room.remove_player(current_seat)
                if current_room.player_count == 0:
                    self.rooms.pop(current_room.room_id, None)
                else:
                    await current_room._broadcast_ready_status()
                    if current_room._running:
                        await current_room.broadcast({
                            "type": "player_disconnected",
                            "seat": current_seat,
                        })

    async def start(self):
        print(f"鞍山麻将服务器启动: {self.host}:{self.port}")
        async with websockets.serve(
            self.handle_client, self.host, self.port,
            ping_interval=None,
        ):
            await asyncio.Future()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="鞍山麻将服务器")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    server = GameServer(host=args.host, port=args.port)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
