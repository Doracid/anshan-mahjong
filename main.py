"""
鞍山麻将 - Pygame 界面
"""
import sys
import os
import pygame
from collections import Counter
from game.state import GameState, GamePhase
from game.entities import Tile, Player
from game.cpu_player import cpu_discard, cpu_action
from game import config

# Windows DPI 感知——确保鼠标点击坐标与渲染位置匹配
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# Constants
SCREEN_W, SCREEN_H = 1200, 800
TILE_W, TILE_H = 56, 78
DISCARD_W, DISCARD_H = 40, 55  # 弃牌缩小尺寸
HUN_COLOR = (255, 215, 0)  # Gold
BG_COLOR = (20, 100, 30)
TILE_COLOR = (240, 240, 235)
TILE_BORDER = (60, 60, 60)
TEXT_COLOR = (20, 20, 20)
SELECTED_BORDER = (255, 50, 50)
INFO_COLOR = (255, 255, 200)
FONT_SIZE = 24
TITLE_SIZE = 36
BTN_W, BTN_H = 80, 45
BTN_COLOR = (60, 60, 180)
BTN_HOVER = (80, 80, 220)
BTN_PASS_COLOR = (120, 120, 120)
BTN_PASS_HOVER = (160, 160, 160)
BTN_HU_COLOR = (200, 50, 50)
BTN_HU_HOVER = (240, 70, 70)


class MahjongUI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("鞍山麻将")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('SimHei', FONT_SIZE)
        self.title_font = pygame.font.SysFont('SimHei', TITLE_SIZE)
        self.game = GameState()
        self.selected_tile_idx = -1
        self.running = True
        self.game_over = False
        self.show_gates = False

        # 加载牌图片
        self._tile_images = self._load_tile_images()
        # unknown 牌图片（暗杠显示）
        self._unknown_img = None
        unk_path = os.path.join(os.path.dirname(__file__), 'picture', 'pai', 'unknow.png')
        if os.path.exists(unk_path):
            try:
                self._unknown_img = pygame.image.load(unk_path).convert_alpha()
                self._unknown_img = pygame.transform.scale(self._unknown_img, (TILE_W, TILE_H))
            except Exception:
                pass

        # 操作按钮列表: [(rect, action_name, display_text), ...]
        self._action_buttons = []
        # WAIT_ACTION延迟（吃碰杠前等1秒）
        self._action_delay = 0
        # 吃牌选择状态
        self._waiting_chi = False
        self._chi_options = []        # [(rect, tiles), ...]
        self._restart_btn = None      # 再来一局按钮

        # 预缩放弃牌图片
        self._discard_images = {}
        for k, v in self._tile_images.items():
            self._discard_images[k] = pygame.transform.scale(v, (DISCARD_W, DISCARD_H))

        # CPU 出牌延迟（帧计数）
        self._delay_frames = 0
        self._delay_action = None

        # 绑定 UI 通知
        self.game.on_state_change = self._on_state_change

        # 开始游戏
        self.game.init_game()
        self.game.deal_phase()

    def _load_tile_images(self):
        """加载 picture/pai 里的牌图片"""
        import os
        images = {}
        base = os.path.join(os.path.dirname(__file__), 'picture', 'pai')

        suits_map = {
            'wan': config.WAN, 'tiao': config.TIAO, 'bing': config.BING,
        }
        feng_map = {'dong': (config.FENG, 0), 'nan': (config.FENG, 1),
                    'xi': (config.FENG, 2), 'bei': (config.FENG, 3),
                    'zhong': (config.ZFB, 0), 'fa': (config.ZFB, 1),
                    'bai': (config.ZFB, 2)}

        for fname in os.listdir(base):
            if not fname.endswith('.png'):
                continue
            name = fname[:-4]
            path = os.path.join(base, fname)

            try:
                surf = pygame.image.load(path).convert_alpha()
            except Exception:
                continue

            surf = pygame.transform.scale(surf, (TILE_W, TILE_H))

            # 万条饼
            for prefix, suit in suits_map.items():
                if name.startswith(prefix):
                    num = int(name[len(prefix):])
                    images[(suit, num - 1)] = surf
                    break
            else:
                # 东南西北中发白
                if name in feng_map:
                    images[feng_map[name]] = surf

        return images

    def _on_state_change(self, game):
        """状态变化回调"""
        pass

    def run(self):
        while self.running:
            self._handle_events()
            self._run_auto_turns()
            self._draw()
            self.clock.tick(30)
        pygame.quit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE or event.key == pygame.K_d:
                    if self.game.phase == GamePhase.WAIT_ACTION:
                        self._try_human_action("pass")
                    else:
                        self._try_discard()
                elif event.key == pygame.K_t and self.game.phase != GamePhase.WAIT_ACTION:
                    self.show_gates = not self.show_gates
                elif event.key == pygame.K_r:
                    self._restart_game()
                elif event.key == pygame.K_g:
                    if self.game.phase == GamePhase.WAIT_ACTION:
                        self._try_human_action("gang")
                    elif self.game.phase == GamePhase.DISCARD and self.game.current_player == 0:
                        self._try_self_gang()
                elif event.key == pygame.K_h:
                    self._try_human_action("hu")
                elif event.key == pygame.K_p:
                    self._try_human_action("peng")
                elif event.key == pygame.K_c:
                    self._try_human_action("chi")
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.game_over and self._restart_btn and self._restart_btn.collidepoint(event.pos):
                    self._restart_game()
                else:
                    self._handle_click(event.pos)

    def _handle_click(self, pos):
        x, y = pos

        # 吃牌选择模式：点选吃牌组合
        if self._waiting_chi:
            for rect, tiles in self._chi_options:
                if rect.collidepoint(x, y):
                    self._waiting_chi = False
                    self._chi_options = []
                    if tiles is not None:
                        self.game.handle_action(0, "chi", list(tiles))
                    return
            self._waiting_chi = False
            self._chi_options = []
            # 不吃牌选择，继续往下检查操作按钮

        # 检查操作按钮点击（WAIT_ACTION 时优先）
        if self.game.phase == GamePhase.WAIT_ACTION:
            for rect, action, _ in self._action_buttons:
                if rect.collidepoint(x, y):
                    if action == "pass":
                        self._try_human_action("pass")
                    else:
                        self._try_human_action(action)
                    return
            return

        # 出牌点击（DISCARD 阶段）
        if self.game.phase != GamePhase.DISCARD:
            return
        if self.game.current_player != 0:
            return

        player = self.game.players[0]
        hand = player.hand_tiles

        start_x = (SCREEN_W - len(hand) * (TILE_W + 4)) // 2
        tile_y = SCREEN_H - TILE_H - 30

        for i in range(len(hand)):
            tx = start_x + i * (TILE_W + 4)
            if tx <= x <= tx + TILE_W and tile_y <= y <= tile_y + TILE_H:
                if self.selected_tile_idx == i:
                    self._try_discard()
                else:
                    # 混不能选
                    if hand[i] == self.game.hun_tile:
                        self.selected_tile_idx = -1
                    else:
                        self.selected_tile_idx = i
                break

    def _try_discard(self):
        if self.game.phase != GamePhase.DISCARD:
            return
        if self.game.current_player != 0:
            return
        if self.selected_tile_idx < 0:
            return

        player = self.game.players[0]
        if self.selected_tile_idx >= len(player.hand_tiles):
            return

        tile = player.hand_tiles[self.selected_tile_idx]
        self.game.discard(tile)
        if self.game.phase == GamePhase.WAIT_ACTION:
            self._action_delay = 30
        self.selected_tile_idx = -1

    def _try_self_gang(self):
        """尝试摸牌后暗杠/补杠"""
        if self.game.phase != GamePhase.DISCARD:
            return
        if self.game.current_player != 0:
            return
        if not self.game.just_drew:
            return
        player = self.game.players[0]
        if not player.hand_tiles:
            return
        tile = player.hand_tiles[-1]
        self.game.try_self_gang(tile)

    def _try_human_action(self, action: str):
        """尝试人类玩家的吃碰杠胡操作"""
        if self.game.phase != GamePhase.WAIT_ACTION:
            return
        for a in self.game._action_states:
            if a.seat == 0 and not a.passed:
                if action == "pass":
                    self.game._handle_pass(0)
                    return
                actions = a.available_actions(self.game)
                if action in actions:
                    if action == "chi":
                        # 进入吃牌选择模式
                        from game.logic import can_chi
                        options = can_chi(self.game.players[0], a.tile, self.game.hun_tile)
                        if len(options) == 1:
                            self.game.handle_action(0, "chi", list(options[0]))
                        elif len(options) > 1:
                            self._waiting_chi = True
                            self._chi_options = []
                        else:
                            # 没有可吃的组合，自动过
                            self.game._handle_pass(0)
                    else:
                        self.game.handle_action(0, action, None)
                    return
                break

    def _run_auto_turns(self):
        """自动运行 CPU 回合（含出牌延迟）"""
        if self.game.phase == GamePhase.SETTLE:
            self.game_over = True
            return

        # 出牌延迟：每秒30帧，每步等30帧(1秒)
        if self._delay_frames > 0:
            self._delay_frames -= 1
            return
        if self._delay_action:
            self._delay_action = None

        if self.game.phase == GamePhase.DRAW:
            self.game.draw_phase()
            if self.game.phase != GamePhase.SETTLE:
                self._delay_frames = 30
            return

        if self.game.phase == GamePhase.DISCARD:
            if self.game.current_player != 0:
                player = self.game.players[self.game.current_player]
                # 刚摸牌尝试自杠
                if self.game.just_drew and len(player.hand_tiles) > 0:
                    new_tile = player.hand_tiles[-1]
                    if self.game.try_self_gang(new_tile):
                        self._delay_frames = 30
                        return
                tile = cpu_discard(player, self.game)
                if tile:
                    self.game.discard(tile)
                    self._delay_frames = 30
            return

        if self.game.phase == GamePhase.WAIT_ACTION:
            if self._action_delay > 0:
                self._action_delay -= 1
                return

            # 先检查人类是否有操作
            human_actions = []
            for a in self.game._action_states:
                if a.seat == 0 and not a.passed:
                    human_actions = a.available_actions(self.game)
                    break

            # 人类没有可操作项时自动过
            if human_actions and len([x for x in human_actions if x != "pass"]) == 0:
                self.game._handle_pass(0)
                human_actions = []

            # 按优先级处理：胡 > 杠 > 碰 > 吃
            for priority in ("hu", "gang", "peng", "chi"):
                # 人类有该操作，等按键
                if priority in human_actions:
                    return
                # 处理 CPU 的操作
                for a in list(self.game._action_states):
                    if a.passed or a.seat == 0:
                        continue
                    actions = a.available_actions(self.game)
                    if priority in actions:
                        action, tiles = cpu_action(a.seat, actions, self.game)
                        if action and action != "pass":
                            self.game.handle_action(a.seat, action, tiles)
                            self._delay_frames = 30
                            return
                        a.passed = True

            # 所有人都过了
            self.game._advance_turn()
            return

    def _restart_game(self):
        self.game = GameState()
        self.game.on_state_change = self._on_state_change
        self.selected_tile_idx = -1
        self.game_over = False
        self._delay_frames = 0
        self._action_delay = 0
        self._restart_btn = None
        self.game.init_game()
        self.game.deal_phase()

    def _draw(self):
        self.screen.fill(BG_COLOR)

        self._draw_info()
        if not self.game_over:
            self._draw_human_hand()
        self._draw_cpu_hands()
        if not self.game_over:
            self._draw_discard_area()
        self._draw_controls()

        # 吃牌选择
        if self._waiting_chi:
            self._draw_chi_selection()

        if self.game_over:
            self._draw_win_info()

        if self.show_gates:
            self._draw_gates_info()

        pygame.display.flip()

    def _draw_info(self):
        phase_names = {
            "INIT": "初始化", "DEAL": "发牌", "DRAW": "摸牌",
            "DISCARD": "出牌", "WAIT_ACTION": "等待", "SETTLE": "结算"
        }
        player_names = config.PLAYER_NAMES

        if self.game.hun_tile:
            surf = self.font.render(f"混: {self.game.hun_tile.display()}", True, HUN_COLOR)
            self.screen.blit(surf, (20, 10))

        current = self.game.current_player
        surf = self.font.render(f"当前: {player_names[current]}", True, INFO_COLOR)
        self.screen.blit(surf, (200, 10))

        phase_name = phase_names.get(self.game.phase.name, self.game.phase.name)
        surf = self.font.render(phase_name, True, INFO_COLOR)
        self.screen.blit(surf, (430, 10))

        dealer_seat = next((i for i, p in enumerate(self.game.players) if p.is_dealer), -1)
        if dealer_seat >= 0:
            surf = self.font.render(f"庄家: {player_names[dealer_seat]}", True, HUN_COLOR)
            self.screen.blit(surf, (600, 10))

        surf = self.font.render(f"牌墙: {len(self.game.deck)}", True, INFO_COLOR)
        self.screen.blit(surf, (820, 10))

        hand_count = len(self.game.players[0].hand_tiles)
        meld_count = len(self.game.players[0].melds)
        surf = self.font.render(f"手牌: {hand_count}", True, INFO_COLOR)
        self.screen.blit(surf, (1000, 10))

    def _draw_human_hand(self):
        player = self.game.players[0]
        hand = player.hand_tiles
        if not hand:
            return

        has_new = self.game.has_new_tile and self.game.current_player == 0
        n = len(hand)
        # 新牌留出额外间距
        extra = TILE_W + 20 if has_new else 0
        total_w = (n - (1 if has_new else 0)) * (TILE_W + 4) + extra
        start_x = (SCREEN_W - total_w) // 2
        tile_y = SCREEN_H - TILE_H - 30

        for i, tile in enumerate(hand):
            x = start_x + i * (TILE_W + 4)
            if has_new and i == n - 1:
                x = start_x + (n - 1) * (TILE_W + 4) + 24  # 新牌右移
            y = tile_y
            is_selected = (i == self.selected_tile_idx)
            is_hun = (tile == self.game.hun_tile)
            self._draw_tile(x, y, tile.display(), tile=tile, selected=is_selected, is_hun=is_hun)

        # 绘制玩家的副露（碰/杠/吃）
        if player.melds:
            mx = 20
            my = SCREEN_H - TILE_H - 110
            for m in player.melds:
                if m.is_angang() and self._unknown_img:
                    for _ in m.tiles:
                        self.screen.blit(self._unknown_img, (mx, my))
                        mx += TILE_W + 2
                else:
                    for t in m.tiles:
                        self._draw_tile(mx, my, t.display(), tile=t)
                        mx += TILE_W + 2
                mx += 10

    def _draw_tile(self, x, y, text, tile=None, selected=False, is_hun=False):
        """绘制一张牌，优先使用图片"""
        if tile is not None:
            key = (tile.suit, tile.value)
            img = self._tile_images.get(key)
            if img:
                self.screen.blit(img, (x, y))
                if selected:
                    pygame.draw.rect(self.screen, SELECTED_BORDER,
                                   (x, y, TILE_W, TILE_H), 3)
                if is_hun:
                    h_surf = self.font.render("混", True, (200, 0, 0))
                    self.screen.blit(h_surf, (x + 2, y + 2))
                return

        # 没有图片时用文字方块
        color = HUN_COLOR if is_hun else TILE_COLOR
        pygame.draw.rect(self.screen, color, (x, y, TILE_W, TILE_H))
        pygame.draw.rect(self.screen, TILE_BORDER, (x, y, TILE_W, TILE_H), 2)
        if selected:
            pygame.draw.rect(self.screen, SELECTED_BORDER,
                           (x - 2, y - 2, TILE_W + 4, TILE_H + 4), 3)
        surf = self.font.render(text, True, TEXT_COLOR)
        tw, th = surf.get_size()
        self.screen.blit(surf, (x + (TILE_W - tw) // 2, y + (TILE_H - th) // 2))
        if is_hun:
            h_surf = self.font.render("混", True, (200, 0, 0))
            self.screen.blit(h_surf, (x + 2, y + 2))

    def _draw_tile_back(self, x, y):
        """简化的牌背（纯色方块）"""
        pygame.draw.rect(self.screen, (30, 60, 140), (x, y, TILE_W, TILE_H))
        pygame.draw.rect(self.screen, TILE_BORDER, (x, y, TILE_W, TILE_H), 2)

    def _draw_cpu_hands(self):
        """CPU 手牌不显示，只显示开门（副露）"""
        if self.game_over:
            self._draw_all_hands_center()
            return
        # 上家 (Seat 1) - 左（纵向排列）
        self._draw_cpu_melds(self.game.players[1], (60, SCREEN_H // 2 - 150), vertical=True)
        # 对家 (Seat 2) - 上
        self._draw_cpu_melds(self.game.players[2], (SCREEN_W // 2, 100))
        # 下家 (Seat 3) - 右（纵向排列，右对齐）
        self._draw_cpu_melds(self.game.players[3], (0, SCREEN_H // 2 - 150), vertical=True, right_align=True)

    def _draw_all_hands_center(self):
        """结束时在中央显示所有人手牌（含副露）"""
        names = config.PLAYER_NAMES
        gap = 4
        step = DISCARD_W + gap
        row_h = DISCARD_H + 8

        # 放在胡牌信息下方
        used_y = SCREEN_H // 3 + 160
        for seat in range(4):
            player = self.game.players[seat]
            hand = sorted(player.hand_tiles, key=lambda t: (t.suit, t.value))
            if not hand and not player.melds:
                continue

            label = self.font.render(f"{names[seat]}:  ", True, INFO_COLOR)
            self.screen.blit(label, (20, used_y))
            lx = 20 + label.get_width()

            # 副露
            for m in player.melds:
                for t in m.tiles:
                    self._draw_small_tile(lx, used_y - 2, t, is_hun=(t == self.game.hun_tile))
                    lx += step
                lx += 8

            # 手牌
            for t in hand:
                self._draw_small_tile(lx, used_y - 2, t, is_hun=(t == self.game.hun_tile))
                lx += step

            used_y += row_h

    def _draw_cpu_melds(self, player, top_left, vertical=False, right_align=False):
        if not player.melds:
            return
        x, y = top_left
        margin = 20

        # 水平居中：计算所有副露总宽度，居中对齐
        if not vertical and not right_align:
            total_w = 0
            for m in player.melds:
                total_w += len(m.tiles) * (TILE_W + 2)
            total_w += (len(player.melds) - 1) * 10
            x = (SCREEN_W - total_w) // 2

        for m in player.melds:
            meld_tiles = m.tiles
            meld_w = len(meld_tiles) * (TILE_W + 2)
            draw_x = (SCREEN_W - meld_w - margin) if right_align else x

            if m.is_angang() and self._unknown_img:
                for _ in meld_tiles:
                    self.screen.blit(self._unknown_img, (draw_x, y))
                    draw_x += TILE_W + 2
            else:
                for tile in meld_tiles:
                    self._draw_tile(draw_x, y, tile.display(), tile=tile)
                    draw_x += TILE_W + 2

            if vertical:
                y += TILE_H + 8
            else:
                x = draw_x + 10

    def _draw_discard_area(self):
        """集中显示所有弃牌，每行10张（按打出顺序）"""
        all_discards = self.game.discard_pile

        if not all_discards:
            return

        cols = 15
        gap = 2
        col_w = DISCARD_W + gap
        row_h = DISCARD_H + gap

        n = len(all_discards)
        rows = (n + cols - 1) // cols
        total_w = col_w * min(cols, n) - gap

        start_x = (SCREEN_W - total_w) // 2
        start_y = 245

        for i, tile in enumerate(all_discards):
            r = i // cols
            c = i % cols
            x = start_x + c * col_w
            y = start_y + r * row_h
            self._draw_small_tile(x, y, tile, is_hun=(tile == self.game.hun_tile))

    def _draw_small_tile(self, x, y, tile, is_hun=False, rotation=0):
        """绘制小尺寸弃牌"""
        key = (tile.suit, tile.value)
        img = self._discard_images.get(key)
        if img:
            if rotation:
                img = pygame.transform.rotate(img, rotation)
            self.screen.blit(img, (x, y))
            if is_hun and rotation == 0:
                h_surf = self.font.render("混", True, (200, 0, 0))
                self.screen.blit(h_surf, (x + 2, y + 2))
            return

        # 没有图片时回退到文字方块
        w, h = DISCARD_W, DISCARD_H
        if rotation in (90, -90, 270):
            w, h = DISCARD_H, DISCARD_W
        color = HUN_COLOR if is_hun else TILE_COLOR
        pygame.draw.rect(self.screen, color, (x, y, w, h))
        pygame.draw.rect(self.screen, TILE_BORDER, (x, y, w, h), 2)
        surf = self.font.render(tile.display(), True, TEXT_COLOR)
        tw, th = surf.get_size()
        self.screen.blit(surf, (x + (w - tw) // 2, y + (h - th) // 2))
        if is_hun:
            h_surf = self.font.render("混", True, (200, 0, 0))
            self.screen.blit(h_surf, (x + 2, y + 2))

    def _draw_controls(self):
        """底部控制栏 + 操作按钮"""
        y = SCREEN_H - 10
        hints = "[空格] 出牌  [R] 重开  [Esc] 退出"

        # 摸牌后可杠提示
        if (self.game.phase == GamePhase.DISCARD and self.game.current_player == 0
                and self.game.just_drew):
            from game.logic import can_bugang, can_angang, can_xuanfeng_gang
            player = self.game.players[0]
            new_tile = player.hand_tiles[-1] if player.hand_tiles else None
            if new_tile and (can_bugang(player, new_tile, self.game.hun_tile)
                             or can_angang(player, self.game.hun_tile)
                             or can_xuanfeng_gang(player, self.game.hun_tile)):
                hints += "  [G]杠"

        space_surf = self.font.render(hints, True, INFO_COLOR)
        self.screen.blit(space_surf, (20, y - 30))

        # 操作按钮（WAIT_ACTION 时始终显示，不受 _action_delay 影响）
        self._action_buttons = []
        if self.game.phase == GamePhase.WAIT_ACTION:
            for a in self.game._action_states:
                if a.seat == 0 and not a.passed:
                    actions = a.available_actions(self.game)
                    real_actions = [x for x in actions if x != "pass"]
                    if real_actions:
                        self._draw_action_buttons(actions)
                    break

    def _draw_action_buttons(self, actions):
        """绘制可点击的操作按钮"""
        act_map = {"hu": "胡", "gang": "杠", "peng": "碰", "chi": "吃", "pass": "过"}

        # 过滤掉没有的 action（保留 pass 在最后）
        main_actions = [a for a in actions if a != "pass"]
        has_pass = "pass" in actions

        total = len(main_actions) + (1 if has_pass else 0)
        gap = 10
        total_w = total * BTN_W + (total - 1) * gap
        start_x = (SCREEN_W - total_w) // 2
        btn_y = 190

        # 鼠标位置（hover 效果）
        mx, my = pygame.mouse.get_pos()

        for i, action in enumerate(main_actions):
            x = start_x + i * (BTN_W + gap)
            rect = pygame.Rect(x, btn_y, BTN_W, BTN_H)

            is_hu = action == "hu"
            base_color = BTN_HU_COLOR if is_hu else BTN_COLOR
            hover_color = BTN_HU_HOVER if is_hu else BTN_HOVER
            color = hover_color if rect.collidepoint(mx, my) else base_color

            pygame.draw.rect(self.screen, color, rect, border_radius=8)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=8)

            label = act_map[action]
            surf = self.font.render(label, True, (255, 255, 255))
            tw, th = surf.get_size()
            self.screen.blit(surf, (x + (BTN_W - tw) // 2, btn_y + (BTN_H - th) // 2))

            self._action_buttons.append((rect, action, label))

        if has_pass:
            i = len(main_actions)
            x = start_x + i * (BTN_W + gap)
            rect = pygame.Rect(x, btn_y, BTN_W, BTN_H)
            color = BTN_PASS_HOVER if rect.collidepoint(mx, my) else BTN_PASS_COLOR

            pygame.draw.rect(self.screen, color, rect, border_radius=8)
            pygame.draw.rect(self.screen, (200, 200, 200), rect, 2, border_radius=8)

            surf = self.font.render("过", True, (255, 255, 255))
            tw, th = surf.get_size()
            self.screen.blit(surf, (x + (BTN_W - tw) // 2, btn_y + (BTN_H - th) // 2))

            self._action_buttons.append((rect, "pass", "过"))

    def _draw_chi_selection(self):
        """绘制吃牌选择界面"""
        if not self._waiting_chi or not self.game._pending_tile:
            return

        from game.logic import can_chi
        options = can_chi(self.game.players[0], self.game._pending_tile, self.game.hun_tile)
        if not options:
            self._waiting_chi = False
            return

        # 背景遮罩
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(160)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        title_surf = self.font.render("选择吃牌组合（点击选择）", True, (255, 255, 200))
        tw, th = title_surf.get_size()
        self.screen.blit(title_surf, ((SCREEN_W - tw) // 2, SCREEN_H // 2 - 100))

        self._chi_options = []
        total_w = len(options) * (TILE_W * 3 + 20) + (len(options) - 1) * 15
        start_x = (SCREEN_W - total_w) // 2
        btn_y = SCREEN_H // 2 - 40

        mx, my = pygame.mouse.get_pos()

        for i, seq in enumerate(options):
            x = start_x + i * (TILE_W * 3 + 35)

            # 组合背景框
            rect = pygame.Rect(x - 10, btn_y - 8, TILE_W * 3 + 20, TILE_H + 16)
            color = (80, 180, 80) if rect.collidepoint(mx, my) else (50, 100, 50)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, (200, 255, 200), rect, 2, border_radius=6)

            for j, t in enumerate(seq):
                tx = x + j * (TILE_W + 4)
                is_discarded = (t == self.game._pending_tile)
                self._draw_tile(tx, btn_y, t.display(),
                              tile=t, selected=is_discarded,
                              is_hun=(t == self.game.hun_tile))

            self._chi_options.append((rect, seq))

        # 取消按钮
        cancel_rect = pygame.Rect(SCREEN_W // 2 - 50, SCREEN_H // 2 + 60, 100, BTN_H)
        c_color = BTN_PASS_HOVER if cancel_rect.collidepoint(mx, my) else BTN_PASS_COLOR
        pygame.draw.rect(self.screen, c_color, cancel_rect, border_radius=8)
        pygame.draw.rect(self.screen, (200, 200, 200), cancel_rect, 2, border_radius=8)
        cancel_surf = self.font.render("取消", True, (255, 255, 255))
        ctw, cth = cancel_surf.get_size()
        self.screen.blit(cancel_surf,
                        (cancel_rect.x + (BTN_W - ctw) // 2 + 10,
                         cancel_rect.y + (BTN_H - cth) // 2))
        self._chi_options.append((cancel_rect, None))

    def _draw_win_info(self):
        if self.game.winner is None:
            text = "流局！"
            surf = self.title_font.render(text, True, (255, 200, 0))
            tw, th = surf.get_size()
            x = (SCREEN_W - tw) // 2
            y = SCREEN_H // 2
            self.screen.blit(surf, (x, y))
        else:
            winner = self.game.winner
            is_self = config.PLAYER_NAMES[winner]
            fan = self.game.fan_result

            title_surf = self.title_font.render(f"{is_self} 胡牌！", True, (255, 255, 0))
            tw, th = title_surf.get_size()
            x = (SCREEN_W - tw) // 2

            self.screen.blit(title_surf, (x, SCREEN_H // 3))

            # 分数行
            dy = SCREEN_H // 3 + th + 8
            if fan:
                score_text = f"总番: {fan.total_fan}  分数: {fan.total_score} (2^{fan.total_fan}={fan.base_score}"
                if fan.kong_score > 0:
                    score_text += f" + 杠分{fan.kong_score}"
                score_text += ")"
                surf = self.font.render(score_text, True, (255, 255, 200))
                lx = (SCREEN_W - surf.get_width()) // 2
                self.screen.blit(surf, (lx, dy))
                dy += self.font.get_height() + 4

                # 明细行（自动换行）
                if fan.details:
                    detail_lines = []
                    items = list(fan.details.items())
                    line = ""
                    for k, v in items:
                        part = f"{k}={v}"
                        if line:
                            test = line + " + " + part
                            if self.font.size(test)[0] < SCREEN_W - 80:
                                line = test
                            else:
                                detail_lines.append(line)
                                line = part
                        else:
                            line = part
                    if line:
                        detail_lines.append(line)

                    for dl in detail_lines:
                        surf = self.font.render(dl, True, INFO_COLOR)
                        lx = (SCREEN_W - surf.get_width()) // 2
                        self.screen.blit(surf, (lx, dy))
                        dy += self.font.get_height() + 4

            # 暗枪牌
            if self.game.gun_draw_tile:
                gun = self.game.gun_draw_tile
                gun_label = self.font.render("暗枪牌:", True, HUN_COLOR)
                next_tile = gun.next_tile()
                next_label = self.font.render("下一张:", True, INFO_COLOR)
                gun_total_w = (gun_label.get_width() + 5 + DISCARD_W + 10 +
                               next_label.get_width() + 5 + DISCARD_W)
                gun_x = (SCREEN_W - gun_total_w) // 2
                self.screen.blit(gun_label, (gun_x, dy))
                self._draw_small_tile(gun_x + gun_label.get_width() + 5, dy - 2, gun,
                                      is_hun=(gun == self.game.hun_tile))
                nlx = gun_x + gun_label.get_width() + 5 + DISCARD_W + 10
                self.screen.blit(next_label, (nlx, dy))
                self._draw_small_tile(nlx + next_label.get_width() + 5, dy - 2, next_tile,
                                      is_hun=(next_tile == self.game.hun_tile))

            # 再来一局按钮
            if self.game_over:
                mx, my = pygame.mouse.get_pos()
                btn_w, btn_h = 180, 50
                btn_x = (SCREEN_W - btn_w) // 2
                btn_y = SCREEN_H - 80
                rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
                hover = rect.collidepoint(mx, my)
                color = BTN_HOVER if hover else BTN_COLOR
                pygame.draw.rect(self.screen, color, rect, border_radius=10)
                pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=10)
                surf = self.font.render("再来一局 [R]", True, (255, 255, 255))
                tw, th = surf.get_size()
                self.screen.blit(surf, (btn_x + (btn_w - tw) // 2, btn_y + (btn_h - th) // 2))
                self._restart_btn = rect

    def _draw_gates_info(self):
        try:
            from game.logic import check_hu
            is_hu, special, gates = check_hu(
                self.game.players[0], None, self.game.hun_tile, True
            )
            y = 100
            for g in gates:
                surf = self.font.render(g, True, INFO_COLOR)
                self.screen.blit(surf, (20, y))
                y += 25
        except Exception:
            pass


if __name__ == "__main__":
    ui = MahjongUI()
    ui.run()
