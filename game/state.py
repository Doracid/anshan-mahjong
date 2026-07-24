"""
鞍山麻将游戏状态机
"""
from __future__ import annotations
from enum import Enum, auto
from typing import List, Optional, Tuple, Callable
from .entities import Tile, Player, Meld
from .logic import (
    init_deck, shuffle_deck, deal, determine_hun,
    check_hu, calculate_fan, FanResult,
    can_peng, can_gang, can_angang, can_bugang, can_chi,
    can_xuanfeng_gang,
)
from . import config


class GamePhase(Enum):
    INIT = auto()
    DEAL = auto()
    DRAW = auto()
    DISCARD = auto()
    WAIT_ACTION = auto()
    SETTLE = auto()


class ActionResult:
    """玩家操作结果"""

    def __init__(self):
        self.huactions = []  # 操作链


class GameState:
    def __init__(self):
        self.players: List[Player] = [Player(i) for i in range(4)]
        self.deck: List[Tile] = []
        self.discard_pile: List[Tile] = []
        self.phase = GamePhase.INIT
        self.current_player = 0
        self.current_turn = 0
        self.hun_tile: Optional[Tile] = None
        self.last_discard: Optional[Tile] = None
        self.last_discard_player: int = -1
        self.winner: Optional[int] = None
        self.fan_result: Optional[FanResult] = None
        self.dice_result: Tuple[int, int] = (0, 0)
        self.gun_draw_tile: Optional[Tile] = None  # 暗枪牌
        self.hun_indicator: Optional[Tile] = None  # 翻混时翻出的指示牌
        self.is_kong_draw = False  # 是否杠后摸牌胡牌

        # WAIT_ACTION 临时状态
        self._pending_tile: Optional[Tile] = None
        self._pending_from: int = -1
        self._action_states: List[ActionState] = []

        # 玩家是否有刚摸的牌（UI用，显示间隔）
        self.just_drew = False

        # 回调（用于 UI 通知）
        self.on_state_change: Optional[Callable] = None
        self.on_discard_needed: Optional[Callable] = None
        self.on_action_needed: Optional[Callable] = None

    def notify_state_change(self):
        if self.on_state_change:
            self.on_state_change(self)

    def reset(self):
        """重置游戏"""
        self.__init__()

    @property
    def has_new_tile(self) -> bool:
        """玩家是否有刚摸的牌（手牌末张）"""
        return self.just_drew and self.phase == GamePhase.DISCARD

    # ===================== 初始化流程 =====================

    def init_game(self):
        """初始化一局"""
        self.phase = GamePhase.INIT
        self.deck = init_deck()
        shuffle_deck(self.deck)
        self.players = [Player(i) for i in range(4)]
        self.discard_pile = []
        self.winner = None
        self.fan_result = None
        self.gun_draw_tile = None
        self.hun_indicator = None
        self.is_kong_draw = False
        self.current_turn = 0
        self.notify_state_change()

    def roll_dice(self) -> Tuple[int, int]:
        """掷两个骰子"""
        import random
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        self.dice_result = (d1, d2)
        return d1, d2

    def deal_phase(self):
        """发牌阶段"""
        self.phase = GamePhase.DEAL
        dice_sum = sum(self.roll_dice())
        import random
        dealer = random.randint(0, 3)
        hands, self.deck = deal(self.deck, dealer)
        for i, tiles in enumerate(hands):
            self.players[i].hand_tiles = tiles
            self.players[i].sort_hand()
            self.players[i].is_dealer = (i == dealer)

        self.hun_tile, self.hun_indicator = determine_hun(self.deck, dice_sum)
        print(f"定混: {self.hun_tile.display()}  庄家: {config.PLAYER_NAMES[dealer]} (骰子: {dice_sum})")
        self.current_player = dealer
        self.just_drew = True  # 庄家多摸一张，允许暗杠
        self.phase = GamePhase.DISCARD
        self.notify_state_change()

    # ===================== 摸牌 =====================

    def draw_phase(self):
        """当前玩家摸牌"""
        if not self.deck:
            self.phase = GamePhase.SETTLE
            print("流局！牌墙摸完。")
            self.notify_state_change()
            return

        tile = self.deck.pop()
        player = self.players[self.current_player]
        player.hand_tiles.append(tile)
        # 不排序，新牌保持在末位（UI显示用）
        self.just_drew = True

        # 自摸检测
        is_hu, special, gates = check_hu(player, tile, self.hun_tile, is_self_draw=True)
        if is_hu:
            if self.current_player == 0:
                # 本家自摸需要按钮确认
                self._pending_tile = tile
                self._pending_from = 0
                self._action_states = [ActionState(seat=0, tile=tile, from_seat=0)]
                self.phase = GamePhase.WAIT_ACTION
                print(f"Player 0 自摸！等待确认...")
                self.notify_state_change()
                return
            else:
                # CPU 自动胡牌
                self.winner = self.current_player
                self.discard_pile.append(tile)
                gun_draw = self.deck.pop() if self.deck else None
                self.gun_draw_tile = gun_draw
                self.fan_result = calculate_fan(
                    self, player, tile, self.hun_tile, is_self_draw=True,
                    is_kong_rob=self.is_kong_draw,
                    gun_draw_tile=gun_draw
                )
                self.is_kong_draw = False
                self.phase = GamePhase.SETTLE
                gun_info = f" 暗枪:{gun_draw.display()}" if gun_draw else ""
                score_info = f"总番:{self.fan_result.total_fan} 分数:{self.fan_result.total_score}"
                print(f"Player {self.current_player} 自摸！{special or ''} {score_info}{gun_info}")
                self.notify_state_change()
                return

        self.phase = GamePhase.DISCARD
        self.notify_state_change()

    # ===================== 打牌（由 UI/AI 调用） =====================

    def discard(self, tile: Tile) -> bool:
        """玩家打出一张牌"""
        if self.phase != GamePhase.DISCARD:
            return False

        player = self.players[self.current_player]
        if tile not in player.hand_tiles:
            return False

        # 混不能打
        if self.hun_tile and tile == self.hun_tile:
            return False

        player.hand_tiles.remove(tile)
        player.sort_hand()
        player.discards.append(tile)
        self.discard_pile.append(tile)
        self.last_discard = tile
        self.last_discard_player = self.current_player
        self.just_drew = False

        print(f"Player {self.current_player} 打出: {tile.display()}")

        # 检查其他玩家能否吃碰杠胡
        self._pending_tile = tile
        self._pending_from = self.current_player
        self._action_states = []

        for seat in (3, 2, 1):  # 下家、对家、上家（逆时针）
            other_seat = (self.current_player + seat) % 4
            self._action_states.append(
                ActionState(seat=other_seat, tile=tile, from_seat=self.current_player)
            )

        # 检查是否有可以操作
        actionable = [a for a in self._action_states if a.has_actions(self)]
        if actionable:
            self.phase = GamePhase.WAIT_ACTION
            self.notify_state_change()
        else:
            self._advance_turn()

        return True

    def _advance_turn(self):
        """轮到下家"""
        self.current_player = (self.current_player + 3) % 4
        self.current_turn += 1
        self.last_discard = None
        self.last_discard_player = -1
        self.just_drew = False
        self.phase = GamePhase.DRAW
        self.notify_state_change()

    # ===================== 操作响应 =====================

    def handle_action(self, seat: int, action: str, tiles: Optional[List[Tile]] = None) -> bool:
        """处理吃碰杠胡操作"""
        if self.phase != GamePhase.WAIT_ACTION:
            return False

        if action == "hu":
            return self._handle_hu(seat)
        elif action == "gang":
            return self._handle_gang(seat, tiles)
        elif action == "peng":
            return self._handle_peng(seat)
        elif action == "chi":
            return self._handle_chi(seat, tiles)
        elif action == "pass":
            return self._handle_pass(seat)

        return False

    def _handle_hu(self, seat: int) -> bool:
        """胡（含自摸和点炮）"""
        player = self.players[seat]
        tile = self._pending_tile

        # 判断是否为自摸：基于谁打出的/摸到的，不依赖手牌中是否有同样花色的牌
        # （否则出现点炮时手牌已有同花色牌会误判为自摸，导致 check_hu 不追加赢牌）
        is_self_draw = (self._pending_from == seat)

        is_hu, special, gates = check_hu(player, tile, self.hun_tile, is_self_draw=is_self_draw)
        if not is_hu:
            return False

        self.winner = seat
        self.last_discard = None
        self.last_discard_player = -1
        # 暗枪：再摸一张
        gun_draw = self.deck.pop() if self.deck else None
        self.gun_draw_tile = gun_draw
        self.fan_result = calculate_fan(
            self, player, tile, self.hun_tile, is_self_draw=is_self_draw,
            is_kong_rob=self.is_kong_draw,
            gun_draw_tile=gun_draw
        )
        self.is_kong_draw = False
        # 点炮胡才需要把牌加入手牌（自摸时已在手牌中）
        if not is_self_draw:
            player.hand_tiles.append(tile)
        # 自摸牌加入弃牌区显示
        if is_self_draw:
            self.discard_pile.append(tile)
        player.sort_hand()
        self.phase = GamePhase.SETTLE
        gun_info = f" 暗枪:{gun_draw.display()}" if gun_draw else ""
        score_info = f"总番:{self.fan_result.total_fan} 分数:{self.fan_result.total_score}"
        print(f"Player {seat} {'自摸' if is_self_draw else '胡牌'}！{special or ''} {score_info}{gun_info}")
        self.notify_state_change()
        return True

    def _remove_last_discard(self):
        """被吃碰杠后从弃牌堆移除最后一张牌"""
        if self.last_discard and self.discard_pile and self.discard_pile[-1] == self.last_discard:
            self.discard_pile.pop()
        if self.last_discard_player >= 0:
            pd = self.players[self.last_discard_player].discards
            if pd and pd[-1] == self.last_discard:
                pd.pop()
        self.last_discard = None
        self.last_discard_player = -1

    def _handle_peng(self, seat: int) -> bool:
        """碰：从手牌移除2张，加上打出的牌组成碰"""
        if not can_peng(self.players[seat], self._pending_tile, self.hun_tile):
            return False

        player = self.players[seat]
        tile = self._pending_tile

        for _ in range(2):
            player.hand_tiles.remove(tile)

        meld = Meld("peng", [tile, tile, tile], source_seat=self._pending_from)
        player.melds.append(meld)
        self._remove_last_discard()
        player.sort_hand()

        print(f"Player {seat} 碰！")
        self.current_player = seat
        self.phase = GamePhase.DISCARD
        self._pending_tile = None
        self._action_states = []
        self.just_drew = False
        self.notify_state_change()
        return True

    def _handle_gang(self, seat: int, tiles: Optional[List[Tile]]) -> bool:
        """明杠"""
        if not can_gang(self.players[seat], self._pending_tile, self.hun_tile):
            return False

        player = self.players[seat]
        tile = self._pending_tile

        for _ in range(3):
            player.hand_tiles.remove(tile)

        meld = Meld("ming_gang", [tile, tile, tile, tile], source_seat=self._pending_from)
        player.melds.append(meld)
        self._remove_last_discard()

        print(f"Player {seat} 明杠！")
        self.current_player = seat
        self._pending_tile = None
        self._action_states = []
        self.just_drew = False
        # 杠后补牌
        self.is_kong_draw = True
        self.draw_phase()
        return True

    def _handle_chi(self, seat: int, tiles: List[Tile]) -> bool:
        """吃（只能吃上家）"""
        if len(tiles) != 3:
            return False
        if (seat - self._pending_from) % 4 != 3:
            return False
        if not can_chi(self.players[seat], self._pending_tile, self.hun_tile):
            return False

        player = self.players[seat]
        for t in tiles:
            if t != self._pending_tile and t not in player.hand_tiles:
                return False

        chi_set = sorted(tiles, key=lambda t: t.value)
        for t in chi_set:
            if t != self._pending_tile:
                player.hand_tiles.remove(t)

        meld = Meld("chi", chi_set, source_seat=self._pending_from)
        player.melds.append(meld)
        self._remove_last_discard()
        player.sort_hand()

        print(f"Player {seat} 吃！")
        self.current_player = seat
        self.phase = GamePhase.DISCARD
        self._pending_tile = None
        self._action_states = []
        self.just_drew = False
        self.notify_state_change()
        return True

    def _handle_pass(self, seat: int) -> bool:
        """过（不操作）"""
        for a in self._action_states:
            if a.seat == seat:
                a.passed = True
                # 自摸过牌：不进WAIT_ACTION，继续出牌
                if a.from_seat == a.seat:
                    self.phase = GamePhase.DISCARD
                    self._pending_tile = None
                    self._action_states = []
                    self.notify_state_change()
                    return True
                break

        if all(a.passed for a in self._action_states):
            self._advance_turn()
        return True

    # ===================== 杠相关（摸牌后操作） =====================

    def try_self_gang(self, tile: Tile) -> bool:
        """摸牌后尝试暗杠、补杠、旋风杠"""
        if self.phase != GamePhase.DISCARD:
            return False

        player = self.players[self.current_player]

        # 暗杠（混不能暗杠）
        if can_angang(player, self.hun_tile):
            gang_tiles = can_angang(player, self.hun_tile)
            if tile in gang_tiles:
                for _ in range(4):
                    player.hand_tiles.remove(tile)
                meld = Meld("an_gang", [tile] * 4, source_seat=-1)
                player.melds.append(meld)
                player.sort_hand()
                print(f"Player {self.current_player} 暗杠！")
                self.just_drew = False
                self.is_kong_draw = True
                self.draw_phase()
                return True

        # 补杠（混不能补杠）
        if can_bugang(player, tile, self.hun_tile):
            for m in player.melds:
                if m.meld_type == "peng" and m.tiles[0] == tile:
                    m.tiles.append(tile)
                    player.hand_tiles.remove(tile)
                    m.meld_type = "bu_gang"
                    print(f"Player {self.current_player} 补杠！")
                    self.just_drew = False
                    self.is_kong_draw = True
                    self.draw_phase()
                    return True

        # 旋风杠
        xuanfeng_types = can_xuanfeng_gang(player, self.hun_tile)
        for gf_type in xuanfeng_types:
            if gf_type == "feng":
                for v in range(4):
                    t = Tile(config.FENG, v)
                    player.hand_tiles.remove(t)
                player.melds.append(Meld("xuanfeng_feng", []))
                print(f"Player {self.current_player} 旋风杠(东南西北)！")
                self.just_drew = False
                self.is_kong_draw = True
                self.draw_phase()
                return True
            elif gf_type == "zfb":
                for v in range(3):
                    t = Tile(config.ZFB, v)
                    player.hand_tiles.remove(t)
                player.melds.append(Meld("xuanfeng_zfb", []))
                print(f"Player {self.current_player} 旋风杠(中发白)！")
                self.just_drew = False
                # 中发白旋风杠不补牌
                self.notify_state_change()
                return True

        return False

    def run_full_game(self, discard_func=None, action_func=None):
        """
        全自动运行一局。
        discard_func: (player, game_state) -> Tile
        action_func: (seat, actions, game_state) -> (action, tiles | None)
        """
        self.init_game()
        self.deal_phase()

        while self.phase != GamePhase.SETTLE:
            if self.phase == GamePhase.DRAW:
                self.draw_phase()
            elif self.phase == GamePhase.DISCARD:
                if discard_func:
                    tile = discard_func(self.players[self.current_player], self)
                    self.discard(tile)
                else:
                    break
            elif self.phase == GamePhase.WAIT_ACTION:
                acted = False
                for priority in ("hu", "gang", "peng", "chi"):
                    for a in self._action_states:
                        if a.passed:
                            continue
                        actions = a.available_actions(self)
                        if priority in actions:
                            if action_func:
                                action, tiles = action_func(a.seat, actions, self)
                                if action and action != "pass":
                                    self.handle_action(a.seat, action, tiles)
                                    acted = True
                                else:
                                    a.passed = True
                            else:
                                self.handle_action(a.seat, priority, None)
                                acted = True
                            break
                    if acted:
                        break
                if not acted:
                    self._advance_turn()

        return self.winner, self.fan_result


class ActionState:
    """记录某玩家对某张牌的操作意向"""

    def __init__(self, seat: int, tile: Tile, from_seat: int):
        self.seat = seat
        self.tile = tile
        self.from_seat = from_seat
        self.passed = False

    def has_actions(self, game: GameState) -> bool:
        return len(self.available_actions(game)) > 0

    def available_actions(self, game: GameState) -> List[str]:
        actions = []
        player = game.players[self.seat]
        tile = self.tile
        hun = game.hun_tile

        # 胡
        is_hu, _, _ = check_hu(player, tile, hun, is_self_draw=(self.from_seat == self.seat))
        if is_hu:
            actions.append("hu")

        # 自摸只提供胡和过
        if self.from_seat == self.seat:
            actions.append("pass")
            return actions

        # 杠（混不能杠）
        if can_gang(player, tile, hun):
            actions.append("gang")

        # 碰（混不能碰）
        if can_peng(player, tile, hun):
            actions.append("peng")

        # 吃（只有上家的牌能吃，混不能吃）
        if (self.seat - self.from_seat) % 4 == 3:
            chi_options = can_chi(player, tile, hun)
            if chi_options:
                actions.append("chi")

        actions.append("pass")
        return actions
