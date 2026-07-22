"""
鞍山麻将核心算法：胡牌检测、番种计算
"""
from __future__ import annotations
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from .entities import Tile, Player, Meld
from . import config


# ===================== 牌墙操作 =====================

def init_deck() -> List[Tile]:
    """创建136张牌（无花牌）"""
    deck = []
    for suit, (lo, hi) in config.SUIT_RANGES.items():
        for value in range(lo, hi):
            for _ in range(config.TILES_PER_TYPE):
                deck.append(Tile(suit, value))
    return deck


def shuffle_deck(deck: List[Tile]) -> List[Tile]:
    random.shuffle(deck)
    return deck


def deal(deck: List[Tile], dealer_seat: int = 0) -> Tuple[List[List[Tile]], List[Tile]]:
    """发牌：庄家14张，闲家13张"""
    hands = [[] for _ in range(4)]
    for seat in range(4):
        count = config.DEALER_HAND if seat == dealer_seat else config.INITIAL_HAND
        for _ in range(count):
            hands[seat].append(deck.pop())
    return hands, deck


def determine_hun(deck: List[Tile], dice_sum: int) -> Tuple[Tile, Tile]:
    """
    根据骰子点数定混。
    规则：翻开牌墙倒数第 N 张（N=dice_sum），它的下一张就是混。
    返回 (hun_tile, indicator)
    """
    idx = min(dice_sum, len(deck))
    pos = len(deck) - idx
    if pos < 0:
        pos = 0
    revealed = deck[pos]
    return revealed.next_tile(), revealed


# ===================== 工具函数 =====================

def _remove(counts: Counter, suit: int, value: int, n: int) -> Counter:
    """从牌计数器中移除 n 张指定牌，返回新 counter"""
    c = counts.copy()
    key = (suit, value)
    c[key] -= n
    if c[key] <= 0:
        del c[key]
    return c


def _find_first_tile(counts: Counter) -> Optional[Tuple[int, int, int]]:
    """找到排序后第一张有计数的牌，返回 (suit, value, count)"""
    for (suit, value) in sorted(counts.keys(), key=lambda k: (k[0], k[1])):
        cnt = counts[(suit, value)]
        if cnt > 0:
            return suit, value, cnt
    return None


# ===================== 普通胡牌检测（递归回溯 + 混牌） =====================

def _can_form_sets(counts: Counter, hun_count: int) -> Tuple[bool, int]:
    """
    递归检测能否将剩余牌组成 N 组面子（刻子或顺子）。
    返回 (能否组成, 刻子数量) — 刻子数量用于"有碰"门检查。
    """
    total = sum(counts.values())

    if total == 0:
        return (hun_count % 3 == 0, 0)

    first = _find_first_tile(counts)
    if first is None:
        return (hun_count % 3 == 0, 0)
    suit, value, cnt = first

    # --- 尝试刻子 (AAA) ---
    need = max(0, 3 - cnt)
    if need <= hun_count:
        remove_cnt = min(cnt, 3)  # 刻子只用3张，多余的留给后续
        new_counts = _remove(counts, suit, value, remove_cnt)
        ok, sub_pung = _can_form_sets(new_counts, hun_count - need)
        if ok:
            return (True, 1 + sub_pung)  # 这一组是刻子

    # --- 尝试顺子 (ABC)，仅限万条饼 ---
    if suit in (config.WAN, config.TIAO, config.BING) and value <= 7:
        need = 0
        remaining = counts.copy()

        for v in (value, value + 1, value + 2):
            c = remaining.get((suit, v), 0)
            if c >= 1:
                remaining = _remove(remaining, suit, v, 1)
            else:
                need += 1

        if need <= hun_count:
            ok, sub_pung = _can_form_sets(remaining, hun_count - need)
            if ok:
                return (True, sub_pung)  # 顺子不计刻子

    return (False, 0)


def check_standard_win(counts: Counter, hun_count: int) -> Tuple[bool, int]:
    """
    标准胡牌：1个将 + 4组面子。
    返回 (是否可胡, 刻子数量) — 刻子数量用于"有碰"门检查。
    """
    found = False
    best_pung = 0

    # --- 尝试用自然对做将 ---
    for (suit, value), cnt in list(counts.items()):
        if cnt >= 2:
            new_counts = _remove(counts, suit, value, 2)
            ok, pung = _can_form_sets(new_counts, hun_count)
            if ok:
                found = True
                best_pung = max(best_pung, pung)
        # 1张自然牌 + 1张混做将
        if cnt >= 1 and hun_count >= 1:
            new_counts = _remove(counts, suit, value, 1)
            ok, pung = _can_form_sets(new_counts, hun_count - 1)
            if ok:
                found = True
                best_pung = max(best_pung, pung)

    # --- 用两张混做将 ---
    if hun_count >= 2:
        ok, pung = _can_form_sets(counts, hun_count - 2)
        if ok:
            found = True
            best_pung = max(best_pung, pung)

    return (found, best_pung)


# ===================== 特殊牌型 =====================

def check_qidui(counts: Counter, hun_count: int) -> bool:
    """七对：7个对子，每对可用1张混补足"""
    pairs = 0
    remaining_hun = hun_count

    # 先数自然对
    for cnt in counts.values():
        pairs += cnt // 2

    # 如果有单张，检查是否能靠混补成对
    singles = sum(cnt % 2 for cnt in counts.values())
    if singles <= remaining_hun:
        pairs += singles
        remaining_hun -= singles

    # 剩余的混可以两两组对
    pairs += remaining_hun // 2

    return pairs == 7


def check_shisanyao(counts: Counter, hun_count: int) -> bool:
    """十三幺：13种幺九牌各1张 + 1张将（重复某幺九或用混）"""
    yaojiu_tiles = set()
    for suit in (config.WAN, config.TIAO, config.BING):
        yaojiu_tiles.add((suit, 0))
        yaojiu_tiles.add((suit, 8))
    for v in range(4):  # 东南西北
        yaojiu_tiles.add((config.FENG, v))
    for v in range(3):  # 中发白
        yaojiu_tiles.add((config.ZFB, v))

    # 统计手牌中的幺九牌种类
    present = 0
    missing = 0
    has_pair = False

    for key, cnt in counts.items():
        if key in yaojiu_tiles:
            present += 1
            if cnt >= 2:
                has_pair = True
        else:
            # 有非幺九牌，直接失败
            return False

    missing = len(yaojiu_tiles) - present

    # 检查是否有对子（用混做将或自然对）
    # 如果所有13种幺九都齐了且能用混做将
    if present == 13 and has_pair:
        return True
    if present == 13 and hun_count >= 1:
        return True
    # 缺的用混补
    if missing <= hun_count:
        remaining_hun = hun_count - missing
        # 一个对子：要么自然对，要么用混
        if has_pair or remaining_hun >= 1:
            return True

    return False


def check_special_win(counts: Counter, hun_count: int) -> Optional[str]:
    """检查特殊牌型"""
    if check_qidui(counts, hun_count):
        return "七对"
    if check_shisanyao(counts, hun_count):
        return "十三幺"
    return None


# ===================== 鞍山四大硬性条件 =====================

def get_suits_in_hand(hand_tiles: List[Tile], hun_tile: Tile) -> set:
    """获取手牌中的花色（不含混），只计万条饼"""
    return set(t.suit for t in hand_tiles if t != hun_tile and t.suit in (config.WAN, config.TIAO, config.BING))


def has_yaojiu_in_hand(hand_tiles: List[Tile], hun_tile: Tile) -> bool:
    """检查是否有幺九牌"""
    return any(t.is_yaojiu() for t in hand_tiles if t != hun_tile)


def has_pung(player: Player, counts: Counter, hun_count: int = 0) -> bool:
    """检查是否有碰/刻子（中发白做将可免，混可补成刻子）"""
    for m in player.melds:
        if m.meld_type in ("peng", "gang"):
            return True
    for cnt in counts.values():
        # 自然刻子
        if cnt >= 3:
            return True
        # 混补成刻子：一对+1混，或单张+2混
        if cnt == 2 and hun_count >= 1:
            return True
        if cnt == 1 and hun_count >= 2:
            return True
    return False


def has_sequence(player: Player, hun_tile: Tile, hand_tiles: Optional[List[Tile]] = None) -> bool:
    """检查是否有顺子（飘胡可免）"""
    if hand_tiles is None:
        hand_tiles = player.hand_tiles
    # 副露中的吃
    for m in player.melds:
        if m.meld_type == "chi":
            return True
    # 手牌中的顺子（简单检测：不依赖混能否组成顺子）
    tile_values = {}
    for t in hand_tiles:
        if t == hun_tile:
            continue
        if t.suit not in tile_values:
            tile_values[t.suit] = set()
        tile_values[t.suit].add(t.value)

    for suit, values in tile_values.items():
        sorted_vals = sorted(values)
        for i in range(len(sorted_vals) - 2):
            if (sorted_vals[i] + 1 == sorted_vals[i + 1] and
                sorted_vals[i + 1] + 1 == sorted_vals[i + 2]):
                return True
    return False


def check_anshan_gates(player: Player, counts: Counter,
                        hun_tile: Tile, hun_count: int,
                        special_type: Optional[str],
                        hand_tiles: Optional[List[Tile]] = None,
                        max_pung: int = 0) -> Tuple[bool, List[str]]:
    """
    检查鞍山四大门：
    - 三门齐（清一色/七对/十三幺可免）
    - 有幺九
    - 有碰（中发白做将可免）
    - 有顺（飘胡可免）
    max_pung: 胡牌分解方案中的刻子数量（来自 check_standard_win）
    """
    if hand_tiles is None:
        hand_tiles = player.hand_tiles
    gates = []

    # 1. 三门齐
    if special_type in ("七对", "十三幺"):
        gates.append("三门齐(免)")
    else:
        suits = get_suits_in_hand(hand_tiles, hun_tile)
        # 合并副露中的花色
        for m in player.melds:
            for t in m.tiles:
                if t != hun_tile and t.suit in (config.WAN, config.TIAO, config.BING):
                    suits.add(t.suit)
        if len(suits) >= 3:
            gates.append("三门齐")
        elif len(suits) == 1:
            gates.append("三门齐(清一色免)")
        else:
            gates.append("三门齐(免)")

    # 2. 有幺九
    if has_yaojiu_in_hand(hand_tiles, hun_tile):
        gates.append("有幺九")
    else:
        # 检查副露
        for m in player.melds:
            if any(t.is_yaojiu() for t in m.tiles if t != hun_tile):
                gates.append("有幺九")
                break
        else:
            gates.append("有幺九(无)")

    # 3. 有碰/刻
    if special_type:
        gates.append("有碰(免)")
    else:
        zhb_as_pair = False
        for (suit, value), cnt in list(counts.items()):
            if cnt >= 2 and suit == config.ZFB:
                zhb_as_pair = True
                break
            if cnt >= 1 and suit == config.ZFB and hun_count > 0:
                zhb_as_pair = True
                break

        # 使用分解方案中的刻子数（max_pung）确保混不会重复使用
        has_pung_meld = any(m.meld_type in ("peng", "gang") for m in player.melds)
        if has_pung_meld or max_pung > 0:
            gates.append("有碰")
        elif zhb_as_pair:
            gates.append("有碰(中发白将免)")
        else:
            gates.append("有碰(无)")

    # 4. 有顺
    if special_type:
        gates.append("有顺(免)")
    elif has_sequence(player, hun_tile, hand_tiles):
        gates.append("有顺")
    else:
        gates.append("有顺(无)")

    passed = all("(无)" not in g for g in gates)
    return passed, gates


# ===================== 胡牌检测主入口 =====================

def check_hu(player: Player, win_tile: Tile, hun_tile: Tile,
             is_self_draw: bool) -> Tuple[bool, Optional[str], List[str]]:
    """
    完整胡牌检测。
    返回 (is_hu, special_type, passed_gates)
    """
    all_hand = list(player.hand_tiles)
    if not is_self_draw and win_tile:
        all_hand.append(win_tile)

    # 分离混牌，用 (suit, value) 元组作为计数键
    hun_count = sum(1 for t in all_hand if t == hun_tile)
    regular = [(t.suit, t.value) for t in all_hand if t != hun_tile]
    counts = Counter(regular)

    # 1. 特殊牌型
    special = check_special_win(counts, hun_count)

    # 2. 普通胡牌
    standard = False
    max_pung = 0
    if not special:
        standard, max_pung = check_standard_win(counts, hun_count)
    else:
        standard = True

    if not standard:
        return False, None, []

    # 3. 鞍山四大门校验（使用包含 win_tile 的手牌）
    hand_for_gates = list(player.hand_tiles)
    if not is_self_draw and win_tile:
        hand_for_gates.append(win_tile)
    passed, gates = check_anshan_gates(player, counts, hun_tile, hun_count, special, hand_for_gates, max_pung=max_pung)

    return passed, special, gates


# ===================== 番种计算 =====================

@dataclass
class FanResult:
    total_fan: int = 0
    details: dict = field(default_factory=dict)
    gun_count: int = 0
    kong_score: int = 0
    base_score: int = 0
    total_score: int = 0


def calculate_fan(game_state, player: Player, win_tile: Tile,
                  hun_tile: Tile, is_self_draw: bool = False,
                  is_kong_rob: bool = False,
                  gun_draw_tile: Optional[Tile] = None) -> FanResult:
    """
    完整鞍山麻将算番。
    番数累加 → 2^总番 × 底分（杠分另算，不参与 2^n），64 番封顶。
    """
    # --- 收集全部牌（含副露） ---
    all_tiles_hand = list(player.hand_tiles)  # 手牌
    for m in player.melds:
        all_tiles_hand.extend(m.tiles)  # 副露

    # 用于牌型检测的手牌（含赢牌）
    hand_for_check = list(player.hand_tiles)
    if win_tile and not is_self_draw:
        hand_for_check.append(win_tile)
        all_tiles_hand.append(win_tile)

    hun_count = sum(1 for t in hand_for_check if t == hun_tile)
    regular = [t for t in hand_for_check if t != hun_tile]
    counts = Counter((t.suit, t.value) for t in regular)

    regular_all = [t for t in all_tiles_hand if t != hun_tile]
    all_counts = Counter((t.suit, t.value) for t in regular_all)

    special = check_special_win(counts, hun_count)

    fan = 0
    details = {}

    def add_fan(name: str, value: int):
        nonlocal fan
        fan += value
        details[name] = details.get(name, 0) + value

    # ==================== 基础番 ====================
    if player.is_dealer:
        add_fan("坐庄", 1)
    if is_self_draw:
        add_fan("自摸", 1)
    else:
        # 点炮番在结算阶段由点炮方额外支付
        pass
    if player.is_closed:
        add_fan("站立", 1)
    if hun_count == 0:
        add_fan("穷胡", 1)
    # 三家闭
    if all(p.is_closed for i, p in enumerate(game_state.players) if i != player.seat_id):
        add_fan("三家闭", 1)

    # ==================== 牌型番 ====================
    has_piaohu = _check_piaohu(player, counts, hun_count)
    has_hunyise = _check_hunyise(counts, hun_tile)
    has_chunqing = _check_chun_qingyise(counts, hun_tile)
    has_sancha = _check_sancha(player, counts, hun_count)

    # 特殊牌型
    if special == "十三幺":
        add_fan("十三幺", 1)
    elif special == "七对":
        # 七对的番在封顶阶段处理
        pass
    else:
        if has_piaohu:
            add_fan("飘胡", 1)
        if has_hunyise and not has_chunqing:
            add_fan("混一色", 1)
        if has_sancha:
            add_fan("三叉", 1)
        # 大哥大（七对时不算）
        if _check_dageda(player, hun_tile):
            add_fan("大哥大", 1)

    # 四归一（含副露）
    if _check_siguiyi(all_counts):
        add_fan("四归一", 1)

    # 二八将
    if _check_erbajiang(counts, hun_count, special, hun_tile):
        add_fan("二八将", 1)

    # 夹胡
    if win_tile and _check_jiahu(player.hand_tiles, win_tile, hun_tile):
        add_fan("夹胡", 1)

    # 杠上开花
    if is_kong_rob:
        add_fan("杠上开花", 1)

    # 上墙头
    try:
        hun_indicator = getattr(game_state, 'hun_indicator', None)
        if _check_shangqiangtou(player, win_tile, hun_tile, hun_indicator):
            add_fan("上墙头", 1)
    except Exception:
        pass

    # ==================== 枪番 ====================
    gun_count = 0
    if gun_draw_tile:
        next_tile = gun_draw_tile.next_tile()
        gun_count = sum(1 for t in all_tiles_hand
                        if t != hun_tile and (t == gun_draw_tile or t == next_tile))
        gun_count = min(gun_count, 7)
        if gun_count > 0:
            add_fan(f"枪×{gun_count}", gun_count)

    # ==================== 封顶判断 ====================
    if special == "七对" and config.QIDUI_CAP:
        fan = config.FAN_CAP
        details = {"七小对": "封顶"}
    elif has_chunqing and config.CHUN_QING_CAP:
        if has_piaohu:
            fan = config.FAN_CAP
            details = {"纯清一色飘胡": "封顶"}
        else:
            fan = config.FAN_CAP
            details = {"纯清一色": "封顶"}
    else:
        fan = min(fan, config.FAN_CAP)

    # ==================== 杠分 ====================
    bright_kong = sum(1 for m in player.melds
                      if m.meld_type in ("ming_gang", "bu_gang", "xuanfeng_feng", "xuanfeng_zfb"))
    dark_kong = sum(1 for m in player.melds if m.meld_type == "an_gang")
    kong_score = bright_kong * config.BRIGHT_KONG_SCORE + dark_kong * config.DARK_KONG_SCORE

    # ==================== 转分数 ====================
    base_score = 2 ** fan
    total_score = base_score + kong_score

    return FanResult(
        total_fan=fan, details=details,
        gun_count=gun_count, kong_score=kong_score,
        base_score=base_score, total_score=total_score,
    )


def _check_piaohu(player: Player, counts: Counter, hun_count: int) -> bool:
    """飘胡：手牌全是刻子（含混），无顺子"""
    for m in player.melds:
        if m.meld_type == "chi":
            return False

    remaining_hun = hun_count
    for cnt in counts.values():
        if cnt % 3 == 1:
            if cnt == 4:
                continue  # 4 = 杠，等同于刻子
            return False
        # 每3张消耗1组刻子
        groups = cnt // 3
        _ = groups  # 用于计数，暂忽略

    return remaining_hun % 3 == 0


def _check_sancha(player: Player, counts: Counter, hun_count: int) -> bool:
    """三叉：三套刻子（杠也算，混不能充）"""
    pung_count = 0
    for cnt in counts.values():
        if cnt >= 3:
            pung_count += 1
    for m in player.melds:
        if m.meld_type in ("peng", "ming_gang", "an_gang", "bu_gang"):
            pung_count += 1
    return pung_count >= 3


def _check_dageda(player: Player, hun_tile: Tile) -> bool:
    """大哥大：手牌+副露中三个箭牌（中发白）都有，或单独一个达3张"""
    all_tiles = list(player.hand_tiles)
    for m in player.melds:
        all_tiles.extend(m.tiles)

    # 检查每个箭牌是否有3张
    for v in range(3):  # 中=0, 发=1, 白=2
        count = sum(1 for t in all_tiles if t.suit == config.ZFB and t.value == v and t != hun_tile)
        if count >= 3:
            return True
    return False


def _check_yitiao_long(counts: Counter, hun_tile: Tile) -> bool:
    """一条龙：同一花色有 1-9 全部牌"""
    for suit in (config.WAN, config.TIAO, config.BING):
        present = all((suit, v) in counts for v in range(9))
        if present:
            return True
    return False


# ===================== 新增番种检测 =====================

def _check_hunyise(counts: Counter, hun_tile: Tile) -> bool:
    """混一色：一种花色 + 字牌"""
    suits = set(s for (s, _) in counts.keys())
    numbered = [s for s in suits if s in (config.WAN, config.TIAO, config.BING)]
    honors = [s for s in suits if s in (config.FENG, config.ZFB)]
    return len(numbered) == 1 and len(honors) >= 1


def _check_chun_qingyise(counts: Counter, hun_tile: Tile) -> bool:
    """纯清一色：只有一种花色（万条饼），无语牌"""
    suits = set(s for (s, _) in counts.keys())
    numbered = [s for s in suits if s in (config.WAN, config.TIAO, config.BING)]
    honors = [s for s in suits if s in (config.FENG, config.ZFB)]
    return len(numbered) == 1 and len(honors) == 0


def _check_siguiyi(all_counts: Counter) -> bool:
    """四归一：全部牌（含副露）中有四张相同"""
    for cnt in all_counts.values():
        if cnt >= 4:
            return True
    return False


def _check_erbajiang(counts: Counter, hun_count: int,
                      special_type: Optional[str], hun_tile: Tile) -> bool:
    """二八将：将以 2 或 8 做将（七对/十三幺不算）"""
    if special_type:
        return False
    for (suit, value), cnt in counts.items():
        if cnt >= 2 and value in (1, 7) and suit in (config.WAN, config.TIAO, config.BING):
            return True
    # 混牌自身是 2 或 8，且用了一对混做将
    if hun_count >= 2 and hun_tile and hun_tile.value in (1, 7) and hun_tile.suit in (config.WAN, config.TIAO, config.BING):
        return True
    return False


def _check_jiahu(hand_tiles: List[Tile], win_tile: Tile, hun_tile: Tile) -> bool:
    """夹胡：纯夹（中间张）或边夹（3/7）"""
    if not win_tile or win_tile == hun_tile:
        return False
    if win_tile.suit not in (config.WAN, config.TIAO, config.BING):
        return False

    values = set(t.value for t in hand_tiles
                 if t.suit == win_tile.suit and t != win_tile and t != hun_tile)
    v = win_tile.value

    # 纯夹：X-1 and X+1
    if v - 1 in values and v + 1 in values:
        return True
    # 边夹 3：手牌有 1,2 → 胡 3 (v=2)
    if v == 2 and 0 in values and 1 in values:
        return True
    # 边夹 7：手牌有 8,9 → 胡 7 (v=6)
    if v == 6 and 7 in values and 8 in values:
        return True
    return False


def _check_shangqiangtou(player: Player, win_tile: Tile,
                          hun_tile: Tile, hun_indicator: Optional[Tile]) -> bool:
    """上墙头：混指示牌被你碰/刻，用它胡牌"""
    if not hun_indicator or not win_tile:
        return False
    if win_tile != hun_indicator:
        return False

    # 检查手牌或副露中是否有指示牌的刻子
    hand_count = sum(1 for t in player.hand_tiles if t == hun_indicator)
    for m in player.melds:
        for t in m.tiles:
            if t == hun_indicator:
                hand_count += 1
    return hand_count >= 3


# ===================== 可执行操作检测 =====================

def can_peng(player: Player, tile: Tile, hun_tile: Tile = None) -> bool:
    """检测是否能碰（混牌不能被碰）"""
    if hun_tile and tile == hun_tile:
        return False
    count = sum(1 for t in player.hand_tiles if t == tile)
    return count >= 2


def can_gang(player: Player, tile: Tile, hun_tile: Tile = None) -> bool:
    """检测是否能明杠（混牌不能被杠）"""
    if hun_tile and tile == hun_tile:
        return False
    count = sum(1 for t in player.hand_tiles if t == tile)
    return count >= 3


def can_angang(player: Player, hun_tile: Tile = None) -> List[Tile]:
    """检测暗杠机会（混牌不能暗杠）"""
    result = []
    counts = Counter(player.hand_tiles)
    for tile, cnt in counts.items():
        if cnt == 4 and (not hun_tile or tile != hun_tile):
            result.append(tile)
    return result


def can_bugang(player: Player, tile: Tile, hun_tile: Tile = None) -> bool:
    """补杠（混牌不能补杠）"""
    if hun_tile and tile == hun_tile:
        return False
    for m in player.melds:
        if m.meld_type == "peng" and m.tiles[0] == tile:
            if any(t == tile for t in player.hand_tiles):
                return True
    return False


def can_xuanfeng_gang(player: Player, hun_tile: Tile = None) -> List[str]:
    """检测旋风杠：东南西北 或 中发白"""
    result = []
    hand_set = Counter(t for t in player.hand_tiles if not hun_tile or t != hun_tile)

    # 东南西北
    feng_need = {(config.FENG, v) for v in range(4)}
    if feng_need.issubset(hand_set.keys()):
        result.append("feng")

    # 中发白
    zfb_need = {(config.ZFB, v) for v in range(3)}
    if zfb_need.issubset(hand_set.keys()):
        result.append("zfb")

    return result


def can_chi(player: Player, tile: Tile, hun_tile: Tile = None) -> List[Tuple[Tile, Tile, Tile]]:
    """检测能吃哪些顺子（混牌不能被吃，字牌无顺子）"""
    if hun_tile and tile == hun_tile:
        return []
    if tile.suit not in (config.WAN, config.TIAO, config.BING):
        return []
    hand_set = Counter(player.hand_tiles)
    results = []
    v = tile.value

    # 吃头：v-2, v-1, v
    if v >= 2:
        needed = [Tile(tile.suit, v - 2), Tile(tile.suit, v - 1)]
        if all(hand_set.get(t, 0) >= 1 for t in needed):
            results.append((needed[0], needed[1], tile))

    # 吃中：v-1, v, v+1
    if 1 <= v <= 7:
        needed = [Tile(tile.suit, v - 1), Tile(tile.suit, v + 1)]
        if all(hand_set.get(t, 0) >= 1 for t in needed):
            results.append((needed[0], tile, needed[1]))

    # 吃尾：v, v+1, v+2
    if v <= 6:
        needed = [Tile(tile.suit, v + 1), Tile(tile.suit, v + 2)]
        if all(hand_set.get(t, 0) >= 1 for t in needed):
            results.append((tile, needed[0], needed[1]))

    return results
