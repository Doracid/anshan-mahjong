from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from . import config


@dataclass(frozen=True)
class Tile:
    suit: int
    value: int  # 0-8 (万条饼), 0-3 (风), 0-2 (中发白)

    def __post_init__(self):
        assert self.suit in config.SUIT_RANGES, f"Invalid suit: {self.suit}"
        lo, hi = config.SUIT_RANGES[self.suit]
        assert lo <= self.value < hi, f"Invalid value {self.value} for suit {self.suit}"

    def display(self) -> str:
        return config.tile_name(self.suit, self.value)

    def is_feng(self) -> bool:
        return self.suit == config.FENG

    def is_zfb(self) -> bool:
        return self.suit == config.ZFB

    def is_zi(self) -> bool:
        """字牌：风 + 中发白"""
        return self.suit in (config.FENG, config.ZFB)

    def is_yaojiu(self) -> bool:
        """幺九：1/9 或字牌"""
        if self.is_zi():
            return True
        return self.value in (0, 8)

    def next_tile(self) -> Tile:
        """获取下一张牌（用于定混），边界时跨花色轮转"""
        if self.suit == config.WAN:
            if self.value < 8:
                return Tile(config.WAN, self.value + 1)
            return Tile(config.TIAO, 0)  # 9万 → 1条
        if self.suit == config.TIAO:
            if self.value < 8:
                return Tile(config.TIAO, self.value + 1)
            return Tile(config.BING, 0)  # 9条 → 1饼
        if self.suit == config.BING:
            if self.value < 8:
                return Tile(config.BING, self.value + 1)
            return Tile(config.FENG, 0)  # 9饼 → 东
        if self.suit == config.FENG:
            if self.value < 3:
                return Tile(config.FENG, self.value + 1)
            return Tile(config.ZFB, 0)  # 北 → 中
        # ZFB
        if self.value < 2:
            return Tile(config.ZFB, self.value + 1)
        return Tile(config.WAN, 0)  # 白 → 1万

    def __str__(self):
        return self.display()


MeldType = str  # "chi" | "peng" | "ming_gang" | "an_gang" | "bu_gang" | "xuanfeng_feng" | "xuanfeng_zfb"


@dataclass
class Meld:
    meld_type: MeldType
    tiles: List[Tile]
    source_seat: int = -1  # 从哪家吃的/碰的

    def is_angang(self) -> bool:
        return self.meld_type == "an_gang"

    def is_minggang(self) -> bool:
        return self.meld_type in ("ming_gang", "bu_gang")

    def is_xuanfeng(self) -> bool:
        return self.meld_type in ("xuanfeng_feng", "xuanfeng_zfb")


@dataclass
class Player:
    seat_id: int
    hand_tiles: List[Tile] = field(default_factory=list)
    melds: List[Meld] = field(default_factory=list)
    discards: List[Tile] = field(default_factory=list)
    is_dealer: bool = False
    hu_tile: Optional[Tile] = None

    @property
    def is_closed(self) -> bool:
        """
        是否闭门（未吃碰）。
        暗杠(an_gang)和旋风杠(xuanfeng)不算开门。
        明杠(ming_gang)、补杠(bu_gang)、碰(peng)、吃(chi)算开门。
        """
        open_types = ("chi", "peng", "ming_gang", "bu_gang")
        return not any(m.meld_type in open_types for m in self.melds)

    @property
    def all_tiles(self) -> List[Tile]:
        """手牌 + 副露牌"""
        result = list(self.hand_tiles)
        for m in self.melds:
            result.extend(m.tiles)
        return result

    def tile_count_map(self):
        """统计每种牌的数量"""
        counts = {}
        for t in self.all_tiles:
            counts[(t.suit, t.value)] = counts.get((t.suit, t.value), 0) + 1
        return counts

    def sort_hand(self):
        self.hand_tiles.sort(key=lambda t: (t.suit, t.value))

    def __str__(self):
        tiles = ", ".join(t.display() for t in sorted(self.hand_tiles, key=lambda t: (t.suit, t.value)))
        return f"Player[{self.seat_id}]: [{tiles}]"
