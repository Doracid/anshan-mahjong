"""
测试鞍山麻将核心算法
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from game.entities import Tile, Player
from game.logic import (
    init_deck, shuffle_deck, deal, determine_hun,
    check_standard_win, check_qidui, check_shisanyao,
    check_hu, check_anshan_gates,
    can_peng, can_gang, can_chi, can_angang,
)
from game import config
from collections import Counter


def test_tile_creation():
    print("=== 测试牌创建 ===")
    t1 = Tile(config.WAN, 0)
    assert t1.display() == "1万", f"Expected 1万, got {t1.display()}"
    t2 = Tile(config.FENG, 3)
    assert t2.display() == "北", f"Expected 北, got {t2.display()}"
    t3 = Tile(config.ZFB, 0)
    assert t3.display() == "中", f"Expected 中, got {t3.display()}"
    print("  ✓ 牌创建测试通过")


def test_deck():
    print("=== 测试牌墙 ===")
    deck = init_deck()
    assert len(deck) == 136, f"Expected 136, got {len(deck)}"
    # 每种花色
    suits_count = {}
    for t in deck:
        suits_count[t.suit] = suits_count.get(t.suit, 0) + 1
    assert suits_count[config.WAN] == 36  # 9种 * 4张
    assert suits_count[config.FENG] == 16  # 4种 * 4张
    assert suits_count[config.ZFB] == 12  # 3种 * 4张
    print(f"  ✓ 牌墙创建测试通过: {len(deck)}张")


def test_hun_determination():
    print("=== 测试定混 ===")
    deck = init_deck()
    # 翻出 1万，混是 2万
    tile_1wan = Tile(config.WAN, 0)
    next_tile = tile_1wan.next_tile()
    assert next_tile == Tile(config.WAN, 1), f"1万的下张应该是2万, got {next_tile}"
    # 9万 → 1条
    tile_9wan = Tile(config.WAN, 8)
    assert tile_9wan.next_tile() == Tile(config.TIAO, 0)
    # 白 → 1万
    tile_bai = Tile(config.ZFB, 2)
    assert tile_bai.next_tile() == Tile(config.WAN, 0)
    print("  ✓ 定混测试通过")


def _to_counter(tiles):
    """将牌列表转换为 (suit, value) 计数字典"""
    return Counter((t.suit, t.value) for t in tiles)


def test_basic_win():
    """标准胡牌测试：111万 234万 567万 789万 55万"""
    print("=== 测试标准胡牌 ===")
    win_hand = [
        Tile(config.WAN, 0), Tile(config.WAN, 0), Tile(config.WAN, 0),
        Tile(config.WAN, 1), Tile(config.WAN, 2), Tile(config.WAN, 3),
        Tile(config.WAN, 4), Tile(config.WAN, 5), Tile(config.WAN, 6),
        Tile(config.WAN, 7), Tile(config.WAN, 8), Tile(config.WAN, 8),
        Tile(config.WAN, 4), Tile(config.WAN, 4),
    ]
    counts = _to_counter(win_hand)
    result = check_standard_win(counts, 0)
    assert result, "标准胡牌应该通过"
    print("  ✓ 标准胡牌测试通过")


def test_hun_win():
    """带混的胡牌测试"""
    print("=== 测试混牌胡牌 ===")
    # 无混标准胡：111 234 567 678 99 万 = 14张
    hand = [
        Tile(config.WAN, 0), Tile(config.WAN, 0), Tile(config.WAN, 0),
        Tile(config.WAN, 1), Tile(config.WAN, 2), Tile(config.WAN, 3),
        Tile(config.WAN, 4), Tile(config.WAN, 5), Tile(config.WAN, 6),
        Tile(config.WAN, 6), Tile(config.WAN, 7), Tile(config.WAN, 8),
        Tile(config.WAN, 8), Tile(config.WAN, 8),
    ]
    counts = _to_counter(hand)
    assert check_standard_win(counts, 0), "标准胡牌（无混）应该通过"

    # 用混替代一张牌：去掉1个7万，加混(当7万)
    # 111 234 567 6(混)8 99 → 111 234 567 678 99 ✓
    hun_tile = Tile(config.WAN, 7)  # 7万是混
    hand_with_hun = [
        Tile(config.WAN, 0), Tile(config.WAN, 0), Tile(config.WAN, 0),
        Tile(config.WAN, 1), Tile(config.WAN, 2), Tile(config.WAN, 3),
        Tile(config.WAN, 4), Tile(config.WAN, 5), Tile(config.WAN, 6),
        Tile(config.WAN, 6), Tile(config.WAN, 8),
        hun_tile,  # 混当7万
        Tile(config.WAN, 8), Tile(config.WAN, 8),
    ]
    regular = [(t.suit, t.value) for t in hand_with_hun if t != hun_tile]
    counts = Counter(regular)
    result = check_standard_win(counts, 1)
    assert result, f"带混胡牌应该通过"
    print("  ✓ 混牌胡牌测试通过")


def test_qidui():
    print("=== 测试七对 ===")
    hand = [
        Tile(config.WAN, 0), Tile(config.WAN, 0),
        Tile(config.WAN, 1), Tile(config.WAN, 1),
        Tile(config.WAN, 2), Tile(config.WAN, 2),
        Tile(config.WAN, 3), Tile(config.WAN, 3),
        Tile(config.WAN, 4), Tile(config.WAN, 4),
        Tile(config.WAN, 5), Tile(config.WAN, 5),
        Tile(config.WAN, 6),
    ]
    counts = _to_counter(hand)
    assert check_qidui(counts, 1), "6对+1混应该形成七对"
    assert not check_qidui(counts, 0), "6对但无混不应该七对"
    print("  ✓ 七对测试通过")


def test_kan_hu():
    """坎张胡牌测试：222 444 666 888 99万"""
    print("=== 测试坎张胡牌 ===")
    hand = [
        Tile(config.WAN, 1), Tile(config.WAN, 1), Tile(config.WAN, 1),
        Tile(config.WAN, 3), Tile(config.WAN, 3), Tile(config.WAN, 3),
        Tile(config.WAN, 5), Tile(config.WAN, 5), Tile(config.WAN, 5),
        Tile(config.WAN, 7), Tile(config.WAN, 7), Tile(config.WAN, 7),
        Tile(config.WAN, 8), Tile(config.WAN, 8),
    ]
    counts = _to_counter(hand)
    assert check_standard_win(counts, 0), "坎张胡牌应该通过"
    print("  ✓ 坎张胡牌测试通过")


def test_not_win():
    """不能胡牌的情况"""
    print("=== 测试非胡牌 ===")
    hand = [
        Tile(config.WAN, 0), Tile(config.WAN, 1), Tile(config.WAN, 2),
        Tile(config.WAN, 3), Tile(config.WAN, 4), Tile(config.WAN, 5),
        Tile(config.WAN, 6), Tile(config.WAN, 7), Tile(config.WAN, 8),
        Tile(config.FENG, 0), Tile(config.FENG, 1), Tile(config.FENG, 2),
        Tile(config.FENG, 3),
    ]
    counts = _to_counter(hand)
    assert not check_standard_win(counts, 0), "散牌不应该胡"
    print("  ✓ 非胡牌测试通过")


def test_peng_chi():
    """碰和吃检测"""
    print("=== 测试碰/吃 ===")
    p = Player(0)
    p.hand_tiles = [
        Tile(config.WAN, 0), Tile(config.WAN, 0),
        Tile(config.WAN, 0), Tile(config.WAN, 1),
        Tile(config.WAN, 2), Tile(config.WAN, 4),
    ]
    tile_1wan = Tile(config.WAN, 0)
    assert can_peng(p, tile_1wan), "有3张1万应该能碰"

    chi_opts = can_chi(p, Tile(config.WAN, 3))
    assert len(chi_opts) > 0, "有1234万，吃3万应该有组合"
    print(f"  吃选项: {[[t.display() for t in opt] for opt in chi_opts]}")
    print("  ✓ 碰/吃测试通过")


def test_deal_and_determine_hun():
    """发牌和定混"""
    print("=== 测试发牌和定混 ===")
    deck = init_deck()
    shuffle_deck(deck)
    hands, remaining = deal(deck)
    assert len(hands[0]) == 14, f"庄家应有14张，有{len(hands[0])}"
    for i in range(1, 4):
        assert len(hands[i]) == 13, f"闲家{i}应有13张，有{len(hands[i])}"
    assert len(remaining) + 14 + 13*3 == 136
    print(f"  ✓ 发牌测试通过: {len(remaining)}张剩余")

    d1, d2 = 3, 5
    hun = determine_hun(remaining, d1 + d2)
    print(f"  定混: {hun.display()} (骰子{d1}+{d2}={d1+d2})")
    print("  ✓ 定混测试通过")


if __name__ == "__main__":
    test_tile_creation()
    test_deck()
    test_hun_determination()
    test_basic_win()
    test_hun_win()
    test_qidui()
    test_kan_hu()
    test_not_win()
    test_peng_chi()
    test_deal_and_determine_hun()
    print("\n✅ 所有测试通过！")
