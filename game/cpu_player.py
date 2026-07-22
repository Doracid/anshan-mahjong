"""
鞍山麻将 CPU 策略（强化版）
"""
from collections import Counter
from typing import List, Optional
from .entities import Tile, Player
from .state import GameState
from .logic import can_peng, can_gang, can_chi
from . import config


def cpu_discard(player: Player, game: GameState) -> Optional[Tile]:
    """
    CPU 选牌策略（牌效 + 安全 + 门子意识）
    1. 计算每张可打牌的价值（低价值优先出）
    2. 考虑安全牌（别人打过的最安全）
    3. 保留门子需要的花色和幺九
    """
    hand = player.hand_tiles
    if not hand:
        return None

    counts = Counter(hand)

    # 安全牌：别人打过的牌（点炮风险低）
    discard_set = set(game.discard_pile)

    # 可打的牌（排除混）
    candidates = []
    for tile in hand:
        if tile == game.hun_tile:
            continue
        candidates.append(tile)

    if not candidates:
        return hand[0]  # 全是混，随便出一张

    # 评估每张候选牌
    scored = []
    for tile in candidates:
        efficiency = _tile_efficiency(tile, counts, game.hun_tile)
        safety = _tile_safety(tile, discard_set)
        gate_penalty = _gate_penalty(tile, player.hand_tiles, game.hun_tile)
        total = efficiency + safety + gate_penalty
        scored.append((tile, total))

    # 按总分排序（分越低越好出）
    scored.sort(key=lambda x: x[1])
    best = scored[0][0]

    return best


def _tile_efficiency(tile: Tile, counts: Counter, hun: Tile) -> int:
    """
    牌效评分：这张牌能跟手牌其他牌形成多少搭子。
    分越低，说明这张牌的牌效越低，越该出。
    """
    # 复制计数排除这张牌
    test_counts = Counter(counts)
    test_counts[tile] -= 1
    if test_counts[tile] <= 0:
        del test_counts[tile]

    penalty = 0

    # 检查花色（只有万条饼有顺子搭）
    if tile.suit in (config.WAN, config.TIAO, config.BING):
        v = tile.value
        # 检查附近的牌能形成多少搭子
        neighbors = set()
        for t, cnt in test_counts.items():
            if t.suit == tile.suit and t != hun and abs(t.value - v) <= 2:
                for _ in range(cnt):
                    neighbors.add(t.value)

        # 搭子潜力：附近几张不同的牌
        link_count = sum(1 for nv in range(v - 2, v + 3)
                         if nv != v and nv in neighbors)
        if link_count == 0:
            penalty += 50  # 孤张
        elif link_count == 1:
            penalty += 30  # 边张搭
        elif link_count == 2:
            penalty += 15  # 两面搭
        else:
            penalty += 5   # 好搭
    else:
        # 字牌只有对子/刻子价值
        cnt = sum(1 for t, c in test_counts.items()
                  if t.suit == tile.suit and t.value == tile.value and t != hun)
        if cnt >= 2:
            penalty += 10  # 已经成刻
        elif cnt == 1:
            penalty += 25  # 有一张相同的
        else:
            penalty += 50  # 孤张字牌

    return penalty


def _tile_safety(tile: Tile, discard_set: set) -> int:
    """安全评分：别人打过的牌点炮风险低"""
    if tile in discard_set:
        return 0  # 安全牌
    # 同花色的其他牌被打过越多越安全
    same_suit_discarded = sum(1 for t in discard_set if t.suit == tile.suit and t != tile)
    safety = max(0, 20 - same_suit_discarded * 3)
    return safety


def _gate_penalty(tile: Tile, hand: List[Tile], hun: Tile) -> int:
    """门子惩罚：防止打出破坏必备门子的牌"""
    penalty = 0
    regular = [t for t in hand if t != hun]
    hand_counts = Counter(regular)
    cnt = hand_counts.get(tile, 0)

    # 三门齐：如果在手牌中这是某花色最后一张，打后会断门
    if tile.suit in (config.WAN, config.TIAO, config.BING):
        same_suit = [t for t in regular if t.suit == tile.suit and t != tile]
        if not same_suit and any(t.suit in (config.WAN, config.TIAO, config.BING) for t in regular):
            # 还有其他花色，但不能断掉这个花色
            # 检查是否只剩这一门
            remaining_suits = set(t.suit for t in regular if t != tile)
            remaining_suits.discard(tile.suit)
            num_other_suits = len(remaining_suits & {config.WAN, config.TIAO, config.BING})
            if num_other_suits >= 1:
                # 还有其他花色，但断一门可能损失三门齐
                penalty += 40

    # 有幺九：如果这是最后一张幺九
    if tile.is_yaojiu():
        other_yaojiu = any(t.is_yaojiu() for t in regular if t != tile)
        if not other_yaojiu:
            penalty += 80

    # 有碰：保留对子
    if cnt >= 2:
        penalty += 30

    return penalty


# ===================== 操作决策 =====================

def cpu_action(seat: int, actions: List[str], game: GameState):
    """
    CPU 操作决策：
    - 有胡必胡
    - 杠看情况（明杠加分，暗杠加分+补牌）
    - 碰考虑手牌强度
    - 吃只在手牌差时吃
    """
    action_set = set(actions)

    if "hu" in actions:
        return "hu", None

    player = game.players[seat]
    hand_tiles = player.hand_tiles
    closed = player.is_closed

    # 杠：收益明确
    if "gang" in actions:
        return "gang", None

    # 碰：保留闭门有价值时可以不碰
    if "peng" in actions:
        hand_size = len(hand_tiles)
        # 闭门且手牌好（接近听牌）时不碰
        if closed and hand_size <= 10:
            # 如果手牌结构好（听牌快）不碰
            if _hand_quality(hand_tiles, game.hun_tile) >= 70:
                return "pass", None
        return "peng", None

    # 吃：CPU 简化策略，暂不吃
    if "chi" in actions:
        return "pass", None

    return "pass", None


def _hand_quality(hand_tiles: List[Tile], hun_tile: Tile) -> int:
    """
    手牌质量评估（0-100）
    越高表示手牌越接近听牌/胡牌
    """
    if not hand_tiles:
        return 0

    regular = [t for t in hand_tiles if t != hun_tile]
    hun_count = len(hand_tiles) - len(regular)

    # 成搭率：已经形成的搭子（对子、顺子、刻子）
    made = 0
    sw_counts = Counter((t.suit, t.value) for t in regular)

    for cnt in sw_counts.values():
        if cnt >= 3:
            made += cnt // 3
        elif cnt == 2:
            made += 1

    # 顺子检测
    for suit in (config.WAN, config.TIAO, config.BING):
        vals = sorted(set(v for (s, v), c in sw_counts.items() if s == suit and c > 0))
        for i in range(len(vals) - 2):
            if vals[i] + 1 == vals[i + 1] and vals[i + 1] + 1 == vals[i + 2]:
                made += 1

    made += int(hun_count * 0.5)
    quality = min(100, made * 20)
    return quality
