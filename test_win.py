"""快速测试胡牌界面：直接设置胡牌"""
import sys, pygame
sys.path.insert(0, '.')
from game.state import GameState, GamePhase
from game.entities import Tile, Player
from game.logic import calculate_fan, check_hu
from game import config

# 创建游戏并正常发牌
gs = GameState()
gs.init_game()
gs.deal_phase()

# 替换玩家0的手牌为胡牌牌型：123万 345万 789万 东东东 发发
player = gs.players[0]
player.hand_tiles.clear()
wan = config.WAN
# 123万
player.hand_tiles.extend([Tile(wan, 0), Tile(wan, 1), Tile(wan, 2)])
# 345万
player.hand_tiles.extend([Tile(wan, 2), Tile(wan, 3), Tile(wan, 4)])
# 789万
player.hand_tiles.extend([Tile(wan, 6), Tile(wan, 7), Tile(wan, 8)])
# 东东东
player.hand_tiles.extend([Tile(config.FENG, 0), Tile(config.FENG, 0), Tile(config.FENG, 0)])
# 发发（将）
player.hand_tiles.extend([Tile(config.ZFB, 1), Tile(config.ZFB, 1)])
player.sort_hand()

# 设置胡牌状态
gs.winner = 0
gs.phase = GamePhase.SETTLE

# 暗枪摸牌
gs.gun_draw_tile = Tile(wan, 5)  # 5万
gs.fan_result = calculate_fan(gs, player, None, gs.hun_tile,
                               is_self_draw=True, gun_draw_tile=gs.gun_draw_tile)

print(f"测试：胡牌！暗枪牌: {gs.gun_draw_tile.display()}")
print(f"番数: {gs.fan_result.total_fan} 明细: {gs.fan_result.details}")

# 启动UI
from main import MahjongUI
ui = MahjongUI()
ui.game = gs
ui.game_over = True
ui.game.on_state_change = ui._on_state_change
ui.run()
