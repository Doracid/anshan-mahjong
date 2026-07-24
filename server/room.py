"""
房间管理：4人房间，AI自动补位
"""
from __future__ import annotations
import asyncio
import json
import random
import string
from typing import List, Optional, Dict, Any, Tuple
from game.state import GameState, GamePhase
from game.logic import check_hu, can_peng, can_gang, can_chi, can_angang, can_bugang, can_xuanfeng_gang
from game.cpu_player import cpu_discard, cpu_action
from .protocol import (
    tile_to_dict, dict_to_tile, encode_public_state, encode_fan_result,
    S_GAME_START, S_DRAW_TILE, S_STATE_UPDATE, S_ACTION_NEEDED,
    S_ACTION_BROADCAST, S_DISCARD_BROADCAST, S_GAME_OVER, S_ERROR,
    S_READY_STATUS, S_CONTINUE_NEEDED, S_CONTINUE_RESULT,
)


def _gen_room_id() -> str:
    return ''.join(random.choices(string.ascii_uppercase, k=4))


class PlayerConnection:
    """玩家连接封装，包含消息队列"""
    def __init__(self, websocket, name: str, seat: int):
        self.ws = websocket
        self.name = name
        self.seat = seat
        self.queue: asyncio.Queue = asyncio.Queue()

    async def send(self, msg: dict):
        try:
            await self.ws.send(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    async def recv(self, timeout: float = 300) -> Optional[dict]:
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def put_message(self, msg: dict):
        self.queue.put_nowait(msg)


class Room:
    def __init__(self):
        self.room_id = _gen_room_id()
        self.players: List[Optional[PlayerConnection]] = [None] * 4  # seat -> PlayerConnection
        self.game: Optional[GameState] = None
        self._running = False
        self._lobby_mode = True
        self._ready_seats: Dict[int, bool] = {}  # seat -> ready state

    @property
    def player_count(self) -> int:
        return sum(1 for p in self.players if p is not None)

    @property
    def is_full(self) -> bool:
        return self.player_count >= 4

    def add_player(self, websocket, name: str) -> int:
        """添加玩家，返回座位号"""
        for seat in range(4):
            if self.players[seat] is None:
                self.players[seat] = PlayerConnection(websocket, name, seat)
                return seat
        raise ValueError("房间已满")

    def remove_player(self, seat: int):
        """移除玩家，并发送断开信号以唤醒可能正在等待的 recv()"""
        pc = self.players[seat]
        if pc:
            pc.put_message({"action": "__disconnect__"})
            self.players[seat] = None
        else:
            self.players[seat] = None

    def get_connection(self, seat: int) -> Optional[PlayerConnection]:
        return self.players[seat]

    def get_websocket(self, seat: int):
        pc = self.players[seat]
        return pc.ws if pc else None

    def fill_ai_seats(self):
        """用AI填充空缺座位（空座位在游戏循环中自动使用cpu_player）"""
        filled = 0
        for seat in range(4):
            if self.players[seat] is None:
                filled += 1
        if filled > 0:
            print(f"[房间 {self.room_id}] AI 补位 {filled} 人")

    @property
    def human_seats(self) -> List[int]:
        return [s for s in range(4) if self.players[s] is not None]

    @property
    def human_count(self) -> int:
        return len(self.human_seats)

    @property
    def ready_count(self) -> int:
        return sum(1 for s in self.human_seats if self._ready_seats.get(s))

    @property
    def all_humans_ready(self) -> bool:
        return self.human_count > 0 and all(
            self._ready_seats.get(s, False) for s in self.human_seats
        )

    def toggle_ready(self, seat: int):
        if seat not in self.human_seats:
            return
        current = self._ready_seats.get(seat, False)
        self._ready_seats[seat] = not current
        print(f"[房间 {self.room_id}] 玩家 {seat} {'准备' if not current else '取消准备'}")

    async def _broadcast_ready_status(self):
        msg = {
            "type": S_READY_STATUS,
            "ready_seats": {s: self._ready_seats.get(s, False) for s in range(4)},
            "human_count": self.human_count,
            "ready_count": self.ready_count,
            "player_count": self.player_count,
            "players": [
                {"seat": s, "name": self.players[s].name if self.players[s] else None}
                for s in range(4)
            ],
        }
        await self.broadcast(msg)

    async def lobby_loop(self):
        """等待所有人类玩家准备，然后开始游戏"""
        self._lobby_mode = True
        self._ready_seats = {}

        await self._broadcast_ready_status()

        # 等待所有人类玩家准备
        while not self.all_humans_ready:
            if self.human_count == 0:
                print(f"[房间 {self.room_id}] 所有人类玩家在准备阶段退出")
                return
            await asyncio.sleep(0.5)

        # 所有人类已准备，AI补位并开始游戏
        self._lobby_mode = False
        self._running = True
        self.fill_ai_seats()
        asyncio.create_task(self.run_game())

    def route_message(self, seat: int, msg: dict):
        """将消息路由到玩家的队列"""
        pc = self.players[seat]
        if pc:
            pc.put_message(msg)

    async def broadcast(self, msg: dict, exclude_seat: int = -1):
        for seat, pc in enumerate(self.players):
            if pc and seat != exclude_seat:
                await pc.send(msg)

    async def send_to(self, seat: int, msg: dict):
        pc = self.players[seat]
        if pc:
            await pc.send(msg)

    async def run_game(self):
        """运行完整游戏，结束后等待继续"""
        while True:
            self._running = True
            self.game = GameState()
            game = self.game

            game.init_game()
            game.deal_phase()

            # 通知所有玩家游戏开始
            await self._broadcast_game_start()

            try:
                await self._game_loop()
            except Exception as e:
                print(f"[房间 {self.room_id}] 游戏错误: {e}")
                import traceback
                traceback.print_exc()
                break
            finally:
                self._running = False

            # 游戏结束，询问是否继续
            all_continue = await self._continue_loop()
            if not all_continue:
                break

        # 房间结束
        print(f"[房间 {self.room_id}] 游戏结束，房间关闭")

    async def _broadcast_game_start(self):
        game = self.game
        for seat in range(4):
            state = encode_public_state(game, seat)
            await self.send_to(seat, {
                "type": S_GAME_START,
                "seat": seat,
                "players": [
                    {"seat": s, "name": self.players[s].name if self.players[s] else f"AI-{s}"}
                    for s in range(4)
                ],
                "dealer": next((i for i, p in enumerate(game.players) if p.is_dealer), 0),
                "hun_tile": tile_to_dict(game.hun_tile),
                "state": state,
            })

    async def _game_loop(self):
        game = self.game
        action_delay = 0

        while game.phase != GamePhase.SETTLE:
            # 所有人类玩家已退出，AI 代管结束
            if self.human_count == 0:
                print(f"[房间 {self.room_id}] 所有人类玩家已退出，游戏终止")
                break

            if game.phase == GamePhase.DRAW:
                await self._handle_draw()
                action_delay = 0

            elif game.phase == GamePhase.DISCARD:
                await self._handle_discard()

            elif game.phase == GamePhase.WAIT_ACTION:
                if action_delay > 0:
                    action_delay -= 1
                    await asyncio.sleep(0.03)
                    continue

                # 收集人类玩家操作
                human_seats = {}
                for a in game._action_states:
                    if not a.passed and self.players[a.seat] is not None:
                        actions = a.available_actions(game)
                        real = [x for x in actions if x != "pass"]
                        if real:
                            human_seats[a.seat] = (a, actions)
                        elif actions:
                            game._handle_pass(a.seat)

                if human_seats:
                    # 通知真人玩家
                    for seat, (a, actions) in human_seats.items():
                        msg = {
                            "type": S_ACTION_NEEDED,
                            "actions": actions,
                            "tile": tile_to_dict(a.tile) if a.tile else None,
                            "from_seat": a.from_seat,
                        }
                        # 吃牌需要附带所有可能的组合供客户端选择
                        if "chi" in actions and a.tile:
                            from game.logic import can_chi
                            player = game.players[seat]
                            chi_opts = can_chi(player, a.tile, game.hun_tile)
                            if chi_opts:
                                msg["chi_options"] = [
                                    [tile_to_dict(t) for t in combo]
                                    for combo in chi_opts
                                ]
                        await self.send_to(seat, msg)

                    # 等待响应
                    results = await self._wait_human_actions(human_seats)
                    if results is None:
                        return

                    # 按优先级处理
                    acted = await self._process_priority_actions(results, game)
                    if acted:
                        action_delay = 30
                    else:
                        # 都过了
                        for seat in list(human_seats.keys()):
                            game._handle_pass(seat)
                        game._advance_turn()
                else:
                    # 只有AI，自动处理
                    await self._process_ai_actions(game)
                    if game.phase == GamePhase.WAIT_ACTION:
                        game._advance_turn()

                # 广播状态
                await self._broadcast_state()

        # 游戏结束
        await self._broadcast_game_over()

    async def _handle_draw(self):
        game = self.game
        game.draw_phase()
        cp = game.current_player

        # 广播摸牌
        for seat in range(4):
            state = encode_public_state(game, seat)
            await self.send_to(seat, {"type": S_STATE_UPDATE, **state})
            if seat == cp and game.just_drew:
                tile = game.players[cp].hand_tiles[-1]
                await self.send_to(seat, {
                    "type": S_DRAW_TILE,
                    "tile": tile_to_dict(tile),
                })

        if game.phase != GamePhase.SETTLE:
            await asyncio.sleep(0.3)

    async def _handle_discard(self):
        game = self.game
        cp = game.current_player
        pc = self.players[cp]

        if pc is not None:
            # 真人玩家出牌
            player = game.players[cp]

            # 自杠检测
            if game.just_drew and len(player.hand_tiles) > 0:
                new_tile = player.hand_tiles[-1]
                gang_types = []
                if can_angang(player, game.hun_tile):
                    gang_types.append("angang")
                if new_tile and can_bugang(player, new_tile, game.hun_tile):
                    gang_types.append("bugang")
                xuanfeng = can_xuanfeng_gang(player, game.hun_tile)
                if xuanfeng:
                    gang_types.extend(xuanfeng)
                if gang_types:
                    await self.send_to(cp, {
                        "type": "self_gang_options",
                        "gang_types": gang_types,
                        "tile": tile_to_dict(new_tile),
                    })
                    msg = await pc.recv(timeout=60)
                    if msg and msg.get("action") != "__disconnect__" and msg.get("action") == "gang":
                        game.try_self_gang(new_tile)
                        await self._broadcast_action(cp, "angang")
                        await self._broadcast_state()
                        await asyncio.sleep(0.3)
                        return

            # 如果玩家仍然在线，询问出牌
            if self.players[cp] is not None:
                await self.send_to(cp, {
                    "type": "need_discard",
                    "hand": [tile_to_dict(t) for t in player.hand_tiles],
                })
                msg = await pc.recv(timeout=300)
                if msg and msg.get("action") != "__disconnect__" and msg.get("action") == "discard":
                    tile = dict_to_tile(msg["tile"])
                    game.discard(tile)
                    await self._broadcast_state()
                    await self.broadcast({
                        "type": S_DISCARD_BROADCAST,
                        "seat": cp,
                        "tile": tile_to_dict(tile),
                    })
                    await asyncio.sleep(0.1)
                    return

        # AI 出牌（也处理断线的人类玩家代管）
        player = game.players[cp]
        if game.just_drew and len(player.hand_tiles) > 0:
            new_tile = player.hand_tiles[-1]
            if game.try_self_gang(new_tile):
                await self._broadcast_state()
                await self.broadcast({"type": S_ACTION_BROADCAST, "seat": cp, "action": "angang"})
                await asyncio.sleep(0.3)
                return
        tile = cpu_discard(player, game)
        if tile:
            game.discard(tile)
            await self._broadcast_state()
            await self.broadcast({
                "type": S_DISCARD_BROADCAST,
                "seat": cp,
                "tile": tile_to_dict(tile),
            })
        await asyncio.sleep(0.1)

    async def _process_priority_actions(self, results: Dict[int, tuple], game) -> bool:
        """按优先级处理真人操作"""
        for priority in ("hu", "gang", "peng", "chi"):
            for seat, (action, tiles) in results.items():
                if action == priority:
                    if action != "pass":
                        ok = game.handle_action(seat, action, tiles)
                        print(f"[房间] 处理操作 seat={seat} action={action} ok={ok}")
                        if ok:
                            await self._broadcast_action(seat, action, tiles)
                            return True
                        else:
                            print(f"[房间] 操作失败: seat={seat} action={action}")
                    return True
        return False

    async def _process_ai_actions(self, game):
        """处理AI玩家的操作"""
        for priority in ("hu", "gang", "peng", "chi"):
            for a in list(game._action_states):
                if a.passed or self.players[a.seat] is not None:
                    continue
                actions = a.available_actions(game)
                if priority in actions:
                    action, tiles = cpu_action(a.seat, actions, game)
                    if action and action != "pass":
                        game.handle_action(a.seat, action, tiles)
                        await self._broadcast_action(a.seat, action, tiles)
                        await asyncio.sleep(0.3)
                        return True
                    a.passed = True
        return False

    async def _wait_human_actions(self, human_seats: dict) -> Optional[Dict[int, tuple]]:
        """同时等待所有真人玩家操作，返回 {seat: (action, tiles)}"""
        results = {}

        async def _wait_one(seat: int):
            pc = self.players[seat]
            if not pc:
                return seat, "pass", None
            msg = await pc.recv(timeout=120)
            if msg is None or msg.get("action") == "__disconnect__":
                return seat, "pass", None
            action = msg.get("action", "pass")
            tiles = None
            if action == "chi" and "tiles" in msg:
                tiles = [dict_to_tile(t) for t in msg["tiles"]]
                print(f"[房间] 收到吃牌: seat={seat} tiles={tiles}")
            elif action != "pass":
                print(f"[房间] 收到操作: seat={seat} action={action}")
            return seat, action, tiles

        tasks = [asyncio.create_task(_wait_one(seat)) for seat in human_seats]
        done, _ = await asyncio.wait(tasks, timeout=130)

        for t in tasks:
            if t in done:
                seat, action, tiles = await t
                results[seat] = (action, tiles)
            else:
                t.cancel()

        return results

    async def _broadcast_state(self):
        """广播游戏状态给所有玩家"""
        game = self.game
        for seat in range(4):
            state = encode_public_state(game, seat)
            await self.send_to(seat, {"type": S_STATE_UPDATE, **state})

    async def _broadcast_action(self, seat: int, action: str, tiles=None):
        msg = {"type": S_ACTION_BROADCAST, "seat": seat, "action": action}
        if tiles:
            msg["tiles"] = [tile_to_dict(t) for t in tiles]
        await self.broadcast(msg)
        await asyncio.sleep(0.3)

    async def _broadcast_game_over(self):
        game = self.game
        for seat in range(4):
            state = encode_public_state(game, seat)
            await self.send_to(seat, {
                "type": S_GAME_OVER,
                "winner": game.winner,
                "fan_result": encode_fan_result(game.fan_result),
                "state": state,
                "gun_draw_tile": tile_to_dict(game.gun_draw_tile) if game.gun_draw_tile else None,
                "hands": [
                    [tile_to_dict(t) for t in game.players[i].hand_tiles]
                    for i in range(4)
                ],
            })

    async def _continue_loop(self) -> bool:
        """游戏结束后询问所有人类玩家是否继续，90秒超时"""
        human_seats = [s for s in range(4) if self.players[s] is not None]
        if not human_seats:
            return False

        print(f"[房间 {self.room_id}] 等待 {len(human_seats)} 名玩家选择继续/退出")
        await self.broadcast({"type": S_CONTINUE_NEEDED})

        results = {}

        async def _wait_one(seat: int):
            pc = self.players[seat]
            if not pc:
                results[seat] = False
                return
            msg = await pc.recv(timeout=90)
            if msg is None:
                results[seat] = False
                print(f"[房间 {self.room_id}] 玩家 {seat} 超时未选择")
                return
            action = msg.get("action", "quit")
            results[seat] = (action == "continue")

        tasks = [asyncio.create_task(_wait_one(s)) for s in human_seats]
        await asyncio.wait(tasks, timeout=95)

        all_continue = all(results.get(s, False) for s in human_seats)
        await self.broadcast({
            "type": S_CONTINUE_RESULT,
            "all_continue": all_continue,
        })

        if all_continue:
            print(f"[房间 {self.room_id}] 所有玩家选择继续，开始新一局")
        else:
            print(f"[房间 {self.room_id}] 有玩家退出或超时，结束游戏")

        return all_continue
