# 花色
WAN = 0
TIAO = 1
BING = 2
FENG = 3
ZFB = 4

SUIT_NAMES = {WAN: "万", TIAO: "条", BING: "饼", FENG: "风", ZFB: "字"}

# 同花色牌值范围
SUIT_RANGES = {
    WAN: (0, 9),
    TIAO: (0, 9),
    BING: (0, 9),
    FENG: (0, 4),
    ZFB: (0, 3),
}

FENG_NAMES = {0: "东", 1: "南", 2: "西", 3: "北"}
ZFB_NAMES = {0: "中", 1: "发", 2: "白"}

# 番种最大封顶
MAX_FAN = 64

# 牌墙总牌数（无花牌）
TOTAL_TILES = 136

# 每种牌的数量
TILES_PER_TYPE = 4

# 骰子面数
DICE_SIDES = 6

# 玩家数量
PLAYER_COUNT = 4

# 初始手牌数
INITIAL_HAND = 13
DEALER_HAND = 14

# 胡牌单元数：1对将 + 4组面子
WIN_PAIRS = 1
WIN_SETS = 4

# 牌值到显示名的映射
def tile_name(suit, value):
    if suit == FENG:
        return FENG_NAMES.get(value, "?")
    if suit == ZFB:
        return ZFB_NAMES.get(value, "?")
    return f"{value + 1}{SUIT_NAMES[suit]}"

# 座位名
PLAYER_NAMES = ["本家", "上家", "对家", "下家"]

# ===================== 算番配置 =====================

# 枪模式: "AN"(暗枪) / "MING"(明枪) / "SHUAI"(摔枪)
GUN_MODE = "AN"

# 封顶番数
FAN_CAP = 64

# 杠分（加分制，非番数）
BRIGHT_KONG_SCORE = 2   # 明杠/补杠
DARK_KONG_SCORE = 5     # 暗杠

# 宝牌系统
ENABLE_BAO = False

# 特殊牌型封顶开关
QIDUI_CAP = True        # 七对封顶
CHUN_QING_CAP = True    # 清一色封顶

# 点炮方额外多付番数
DIANPAO_EXTRA_FAN = 1
