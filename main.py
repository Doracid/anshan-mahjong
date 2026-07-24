"""
鞍山麻将 - Pygame 界面（本地 + 联网对战）
"""
from __future__ import annotations
import sys
import os
import pygame
from collections import Counter
from enum import Enum, auto
from typing import Optional, List
from game.state import GameState, GamePhase
from game.entities import Tile, Player
from game.cpu_player import cpu_discard, cpu_action
from game.network import NetworkClient
from game import config

# Windows DPI 感知
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# Constants
SCREEN_W, SCREEN_H = 1200, 800
TILE_W, TILE_H = 56, 78
DISCARD_W, DISCARD_H = 40, 55
HUN_COLOR = (255, 215, 0)
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

# 在线状态按钮
BTN_WIDE_W, BTN_WIDE_H = 200, 50


class AppMode(Enum):
    MENU = auto()
    CONNECT = auto()
    LOCAL_GAME = auto()
    ONLINE_GAME = auto()


# ===================== 公共绘制工具 =====================

class TileRenderer:
    """牌面渲染工具（与模式无关）"""
    def __init__(self):
        self._tile_images = self._load_tile_images()
        self._unknown_img = None
        unk_path = os.path.join(os.path.dirname(__file__), 'picture', 'pai', 'unknow.png')
        if os.path.exists(unk_path):
            try:
                self._unknown_img = pygame.image.load(unk_path).convert_alpha()
                self._unknown_img = pygame.transform.scale(self._unknown_img, (TILE_W, TILE_H))
            except Exception:
                pass
        self._discard_images = {}
        for k, v in self._tile_images.items():
            self._discard_images[k] = pygame.transform.scale(v, (DISCARD_W, DISCARD_H))

    def _load_tile_images(self):
        images = {}
        base = os.path.join(os.path.dirname(__file__), 'picture', 'pai')
        suits_map = {'wan': config.WAN, 'tiao': config.TIAO, 'bing': config.BING}
        feng_map = {'dong': (config.FENG, 0), 'nan': (config.FENG, 1),
                    'xi': (config.FENG, 2), 'bei': (config.FENG, 3),
                    'zhong': (config.ZFB, 0), 'fa': (config.ZFB, 1),
                    'bai': (config.ZFB, 2)}
        if not os.path.exists(base):
            return images
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
            for prefix, suit in suits_map.items():
                if name.startswith(prefix):
                    num = int(name[len(prefix):])
                    images[(suit, num - 1)] = surf
                    break
            else:
                if name in feng_map:
                    images[feng_map[name]] = surf
        return images

    def draw_tile(self, screen, x, y, text, tile=None, selected=False, is_hun=False, font=None):
        if tile is not None:
            key = (tile.suit, tile.value)
            img = self._tile_images.get(key)
            if img:
                screen.blit(img, (x, y))
                if is_hun:
                    gold = pygame.Surface((TILE_W, TILE_H))
                    gold.fill((255, 215, 0))
                    gold.set_alpha(80)
                    screen.blit(gold, (x, y))
                if selected:
                    pygame.draw.rect(screen, SELECTED_BORDER, (x, y, TILE_W, TILE_H), 3)
                return
        color = HUN_COLOR if is_hun else TILE_COLOR
        pygame.draw.rect(screen, color, (x, y, TILE_W, TILE_H))
        pygame.draw.rect(screen, TILE_BORDER, (x, y, TILE_W, TILE_H), 2)
        if selected:
            pygame.draw.rect(screen, SELECTED_BORDER, (x - 2, y - 2, TILE_W + 4, TILE_H + 4), 3)
        if font:
            surf = font.render(text, True, TEXT_COLOR)
            tw, th = surf.get_size()
            screen.blit(surf, (x + (TILE_W - tw) // 2, y + (TILE_H - th) // 2))

    def draw_small_tile(self, screen, x, y, tile, is_hun=False, rotation=0, font=None):
        key = (tile.suit, tile.value)
        img = self._discard_images.get(key)
        if img:
            if rotation:
                img = pygame.transform.rotate(img, rotation)
            screen.blit(img, (x, y))
            if is_hun and rotation == 0:
                w, h = (DISCARD_W, DISCARD_H) if rotation == 0 else (DISCARD_H, DISCARD_W)
                gold = pygame.Surface((DISCARD_W, DISCARD_H))
                gold.fill((255, 215, 0))
                gold.set_alpha(80)
                screen.blit(gold, (x, y))
            return
        w, h = DISCARD_W, DISCARD_H
        if rotation in (90, -90, 270):
            w, h = DISCARD_H, DISCARD_W
        color = HUN_COLOR if is_hun else TILE_COLOR
        pygame.draw.rect(screen, color, (x, y, w, h))
        pygame.draw.rect(screen, TILE_BORDER, (x, y, w, h), 2)
        if font:
            surf = font.render(tile.display(), True, TEXT_COLOR)
            tw, th = surf.get_size()
            screen.blit(surf, (x + (w - tw) // 2, y + (h - th) // 2))

    def draw_tile_back(self, screen, x, y):
        pygame.draw.rect(screen, (30, 60, 140), (x, y, TILE_W, TILE_H))
        pygame.draw.rect(screen, TILE_BORDER, (x, y, TILE_W, TILE_H), 2)

    def get_tile_img(self, tile):
        return self._tile_images.get((tile.suit, tile.value))

    def get_unknown_img(self):
        return self._unknown_img


# ===================== 本地游戏（原 MahjongUI） =====================

class LocalGameUI:
    def __init__(self, screen, font, title_font, renderer: TileRenderer):
        self.screen = screen
        self.font = font
        self.title_font = title_font
        self.renderer = renderer
        self.game = GameState()
        self.selected_tile_idx = -1
        self.game_over = False
        self.show_gates = False

        self._action_buttons = []
        self._action_delay = 0
        self._waiting_chi = False
        self._chi_options = []
        self._restart_btn = None
        self._delay_frames = 0
        self._delay_action = None

        self.game.on_state_change = lambda g: None
        self.game.init_game()
        self.game.deal_phase()

    def reset(self):
        self.game = GameState()
        self.game.on_state_change = lambda g: None
        self.selected_tile_idx = -1
        self.game_over = False
        self._delay_frames = 0
        self._action_delay = 0
        self._restart_btn = None
        self._waiting_chi = False
        self._chi_options = []
        self.game.init_game()
        self.game.deal_phase()

    def handle_events(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "quit"
            elif event.key == pygame.K_SPACE or event.key == pygame.K_d:
                if self.game.phase == GamePhase.WAIT_ACTION:
                    self._try_human_action("pass")
                else:
                    self._try_discard()
            elif event.key == pygame.K_t and self.game.phase != GamePhase.WAIT_ACTION:
                self.show_gates = not self.show_gates
            elif event.key == pygame.K_r:
                self.reset()
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
                self.reset()
            else:
                self._handle_click(event.pos)

    def _handle_click(self, pos):
        x, y = pos
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
        if self.game.phase == GamePhase.WAIT_ACTION:
            for rect, action, _ in self._action_buttons:
                if rect.collidepoint(x, y):
                    if action == "pass":
                        self._try_human_action("pass")
                    else:
                        self._try_human_action(action)
                    return
            return
        if self.game.phase != GamePhase.DISCARD or self.game.current_player != 0:
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
                    if hand[i] == self.game.hun_tile:
                        self.selected_tile_idx = -1
                    else:
                        self.selected_tile_idx = i
                break

    def _try_discard(self):
        if (self.game.phase != GamePhase.DISCARD or self.game.current_player != 0
                or self.selected_tile_idx < 0):
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
        if self.game.phase != GamePhase.DISCARD or self.game.current_player != 0:
            return
        player = self.game.players[0]
        if not player.hand_tiles:
            return
        from game.logic import can_angang, can_bugang, can_xuanfeng_gang
        # 优先暗杠：找手里任何4张相同的牌
        angang_tiles = can_angang(player, self.game.hun_tile)
        for t in angang_tiles:
            if self.game.try_self_gang(t):
                return
        # 补杠
        if self.game.just_drew:
            new_tile = player.hand_tiles[-1]
            if self.game.try_self_gang(new_tile):
                return

    def _try_human_action(self, action: str):
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
                        from game.logic import can_chi
                        options = can_chi(self.game.players[0], a.tile, self.game.hun_tile)
                        if len(options) == 1:
                            self.game.handle_action(0, "chi", list(options[0]))
                        elif len(options) > 1:
                            self._waiting_chi = True
                            self._chi_options = []
                        else:
                            self.game._handle_pass(0)
                    else:
                        self.game.handle_action(0, action, None)
                    return
                break

    def update(self):
        if self.game.phase == GamePhase.SETTLE:
            self.game_over = True
            return
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
            human_actions = []
            for a in self.game._action_states:
                if a.seat == 0 and not a.passed:
                    human_actions = a.available_actions(self.game)
                    break
            if human_actions and len([x for x in human_actions if x != "pass"]) == 0:
                self.game._handle_pass(0)
                human_actions = []
            for priority in ("hu", "gang", "peng", "chi"):
                if priority in human_actions:
                    return
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
            self.game._advance_turn()
            return

    def draw(self):
        self._draw_info()
        if not self.game_over:
            self._draw_human_hand()
        self._draw_cpu_hands()
        if not self.game_over:
            self._draw_discard_area()
        self._draw_controls()
        if self._waiting_chi:
            self._draw_chi_selection()
        if self.game_over:
            self._draw_win_info()
        if self.show_gates:
            self._draw_gates_info()

    def _draw_info(self):
        phase_names = {"INIT": "初始化", "DEAL": "发牌", "DRAW": "摸牌",
                       "DISCARD": "出牌", "WAIT_ACTION": "等待", "SETTLE": "结算"}
        player_names = config.PLAYER_NAMES
        if self.game.hun_tile:
            surf = self.font.render(f"混: {self.game.hun_tile.display()}", True, HUN_COLOR)
            self.screen.blit(surf, (20, 10))
        cp = self.game.current_player
        surf = self.font.render(f"当前: {player_names[cp]}", True, INFO_COLOR)
        self.screen.blit(surf, (200, 10))
        phase_name = phase_names.get(self.game.phase.name, self.game.phase.name)
        surf = self.font.render(phase_name, True, INFO_COLOR)
        self.screen.blit(surf, (430, 10))
        dealer = next((i for i, p in enumerate(self.game.players) if p.is_dealer), -1)
        if dealer >= 0:
            surf = self.font.render(f"庄家: {player_names[dealer]}", True, HUN_COLOR)
            self.screen.blit(surf, (600, 10))
        surf = self.font.render(f"牌墙: {len(self.game.deck)}", True, INFO_COLOR)
        self.screen.blit(surf, (820, 10))
        surf = self.font.render(f"手牌: {len(self.game.players[0].hand_tiles)}", True, INFO_COLOR)
        self.screen.blit(surf, (1000, 10))

    def _draw_human_hand(self):
        player = self.game.players[0]
        hand = player.hand_tiles
        if not hand:
            return
        has_new = self.game.has_new_tile and self.game.current_player == 0
        n = len(hand)
        extra = TILE_W + 20 if has_new else 0
        total_w = (n - (1 if has_new else 0)) * (TILE_W + 4) + extra
        start_x = (SCREEN_W - total_w) // 2
        tile_y = SCREEN_H - TILE_H - 30
        for i, tile in enumerate(hand):
            x = start_x + i * (TILE_W + 4)
            if has_new and i == n - 1:
                x = start_x + (n - 1) * (TILE_W + 4) + 24
            is_selected = (i == self.selected_tile_idx)
            is_hun = (tile == self.game.hun_tile)
            self.renderer.draw_tile(self.screen, x, tile_y, tile.display(),
                                   tile=tile, selected=is_selected, is_hun=is_hun, font=self.font)
        if player.melds:
            mx, my = 20, SCREEN_H - TILE_H - 110
            for m in player.melds:
                if m.is_angang() and self.renderer.get_unknown_img():
                    for _ in m.tiles:
                        self.screen.blit(self.renderer.get_unknown_img(), (mx, my))
                        mx += TILE_W + 2
                else:
                    for t in m.tiles:
                        self.renderer.draw_tile(self.screen, mx, my, t.display(), tile=t, font=self.font)
                        mx += TILE_W + 2
                mx += 10

    def _draw_cpu_hands(self):
        if self.game_over:
            self._draw_all_hands_center()
            return
        self._draw_cpu_melds(self.game.players[1], (60, SCREEN_H // 2 - 150), vertical=True)
        self._draw_cpu_melds(self.game.players[2], (SCREEN_W // 2, 100))
        self._draw_cpu_melds(self.game.players[3], (0, SCREEN_H // 2 - 150), vertical=True, right_align=True)

    def _draw_all_hands_center(self):
        names = config.PLAYER_NAMES
        gap = 4
        step = DISCARD_W + gap
        row_h = DISCARD_H + 8
        used_y = SCREEN_H // 3 + 160
        for seat in range(4):
            player = self.game.players[seat]
            hand = sorted(player.hand_tiles, key=lambda t: (t.suit, t.value))
            if not hand and not player.melds:
                continue
            label = self.font.render(f"{names[seat]}:  ", True, INFO_COLOR)
            self.screen.blit(label, (20, used_y))
            lx = 20 + label.get_width()
            for m in player.melds:
                for t in m.tiles:
                    self.renderer.draw_small_tile(self.screen, lx, used_y - 2, t,
                                                 is_hun=(t == self.game.hun_tile), font=self.font)
                    lx += step
                lx += 8
            for t in hand:
                self.renderer.draw_small_tile(self.screen, lx, used_y - 2, t,
                                             is_hun=(t == self.game.hun_tile), font=self.font)
                lx += step
            used_y += row_h

    def _draw_cpu_melds(self, player, top_left, vertical=False, right_align=False):
        if not player.melds:
            return
        x, y = top_left
        margin = 20
        if not vertical and not right_align:
            total_w = sum(len(m.tiles) * (TILE_W + 2) for m in player.melds)
            total_w += (len(player.melds) - 1) * 10
            x = (SCREEN_W - total_w) // 2
        for m in player.melds:
            meld_w = len(m.tiles) * (TILE_W + 2)
            draw_x = (SCREEN_W - meld_w - margin) if right_align else x
            if m.is_angang() and self.renderer.get_unknown_img():
                for _ in m.tiles:
                    self.screen.blit(self.renderer.get_unknown_img(), (draw_x, y))
                    draw_x += TILE_W + 2
            else:
                for tile in m.tiles:
                    self.renderer.draw_tile(self.screen, draw_x, y, tile.display(), tile=tile, font=self.font)
                    draw_x += TILE_W + 2
            if vertical:
                y += TILE_H + 8
            else:
                x = draw_x + 10

    def _draw_discard_area(self):
        all_discards = self.game.discard_pile
        if not all_discards:
            return
        cols, gap = 15, 2
        col_w, row_h = DISCARD_W + gap, DISCARD_H + gap
        n = len(all_discards)
        rows = (n + cols - 1) // cols
        total_w = col_w * min(cols, n) - gap
        start_x, start_y = (SCREEN_W - total_w) // 2, 245
        for i, tile in enumerate(all_discards):
            r, c = i // cols, i % cols
            x, y = start_x + c * col_w, start_y + r * row_h
            self.renderer.draw_small_tile(self.screen, x, y, tile,
                                         is_hun=(tile == self.game.hun_tile), font=self.font)

    def _draw_controls(self):
        y = SCREEN_H - 10
        hints = "[空格] 出牌  [R] 重开  [Esc] 返回菜单"
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
        act_map = {"hu": "胡", "gang": "杠", "peng": "碰", "chi": "吃", "pass": "过"}
        main_actions = [a for a in actions if a != "pass"]
        has_pass = "pass" in actions
        total = len(main_actions) + (1 if has_pass else 0)
        gap = 10
        total_w = total * BTN_W + (total - 1) * gap
        start_x = (SCREEN_W - total_w) // 2
        btn_y = 190
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
        if not self._waiting_chi or not self.game._pending_tile:
            return
        from game.logic import can_chi
        options = can_chi(self.game.players[0], self.game._pending_tile, self.game.hun_tile)
        if not options:
            self._waiting_chi = False
            return
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
            rect = pygame.Rect(x - 10, btn_y - 8, TILE_W * 3 + 20, TILE_H + 16)
            color = (80, 180, 80) if rect.collidepoint(mx, my) else (50, 100, 50)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, (200, 255, 200), rect, 2, border_radius=6)
            for j, t in enumerate(seq):
                tx = x + j * (TILE_W + 4)
                is_discarded = (t == self.game._pending_tile)
                self.renderer.draw_tile(self.screen, tx, btn_y, t.display(),
                                       tile=t, selected=is_discarded,
                                       is_hun=(t == self.game.hun_tile), font=self.font)
            self._chi_options.append((rect, seq))
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
            self.screen.blit(surf, ((SCREEN_W - tw) // 2, SCREEN_H // 4))
        else:
            winner = self.game.winner
            is_self = config.PLAYER_NAMES[winner]
            fan = self.game.fan_result
            title_surf = self.title_font.render(f"{is_self} 胡牌！", True, (255, 255, 0))
            tw, th = title_surf.get_size()
            x = (SCREEN_W - tw) // 2
            self.screen.blit(title_surf, (x, SCREEN_H // 4))
            dy = SCREEN_H // 4 + th + 8
            if fan:
                score_text = f"总番: {fan.total_fan}  分数: {fan.total_score}"
                surf = self.font.render(score_text, True, (255, 255, 200))
                lx = (SCREEN_W - surf.get_width()) // 2
                self.screen.blit(surf, (lx, dy))
                dy += self.font.get_height() + 4
                if fan.details:
                    items = list(fan.details.items())
                    line = ""
                    for k, v in items:
                        part = f"{k}={v}"
                        if line:
                            test = line + " + " + part
                            if self.font.size(test)[0] < SCREEN_W - 80:
                                line = test
                            else:
                                self._draw_text_center(line, dy)
                                dy += self.font.get_height() + 4
                                line = part
                        else:
                            line = part
                    if line:
                        self._draw_text_center(line, dy)
                        dy += self.font.get_height() + 4
            if self.game.gun_draw_tile:
                gun = self.game.gun_draw_tile
                gun_label = self.font.render("暗枪牌:", True, HUN_COLOR)
                next_label = self.font.render("下一张:", True, INFO_COLOR)
                gun_total_w = (gun_label.get_width() + 5 + DISCARD_W + 10 +
                               next_label.get_width() + 5 + DISCARD_W)
                gun_x = (SCREEN_W - gun_total_w) // 2
                self.screen.blit(gun_label, (gun_x, dy))
                self.renderer.draw_small_tile(self.screen, gun_x + gun_label.get_width() + 5, dy - 2, gun,
                                             is_hun=(gun == self.game.hun_tile), font=self.font)
                nlx = gun_x + gun_label.get_width() + 5 + DISCARD_W + 10
                self.screen.blit(next_label, (nlx, dy))
                self.renderer.draw_small_tile(self.screen, nlx + next_label.get_width() + 5, dy - 2,
                                             gun.next_tile(),
                                             is_hun=(gun.next_tile() == self.game.hun_tile), font=self.font)
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

    def _draw_text_center(self, text, y):
        surf = self.font.render(text, True, INFO_COLOR)
        lx = (SCREEN_W - surf.get_width()) // 2
        self.screen.blit(surf, (lx, y))

    def _draw_gates_info(self):
        try:
            from game.logic import check_hu
            _, _, gates = check_hu(self.game.players[0], None, self.game.hun_tile, True)
            y = 100
            for g in gates:
                surf = self.font.render(g, True, INFO_COLOR)
                self.screen.blit(surf, (20, y))
                y += 25
        except Exception:
            pass


# ===================== 在线游戏 =====================

class OnlineGameUI:
    def __init__(self, screen, font, title_font, renderer: TileRenderer):
        self.screen = screen
        self.font = font
        self.title_font = title_font
        self.renderer = renderer
        self.net = NetworkClient()
        self.net.on_message = self._on_message
        self.net.on_connected = self._on_connected
        self.net.on_disconnected = self._on_disconnected

        # 状态
        self.my_seat = 0
        self.player_names = ["本家", "上家", "对家", "下家"]
        self.game: Optional[GameState] = None
        self.room_id = ""
        self.connected = False
        self.game_started = False
        self.game_over = False
        self.status_text = "连接中..."
        self._lobby_mode = False
        self._lobby_players = []  # [{seat, name, ready}]
        self._is_ready = False
        self._notifications: List[dict] = []  # 事件提示 [{text, timer, color}]
        self._action_display = None  # {text, tiles, timer}

        # UI 状态
        self._action_buttons = []
        self._waiting_chi = False
        self._chi_options = []
        self._hand_tiles: List[Tile] = []
        self._discard_pile: List[Tile] = []
        self._melds = []
        self._all_melds = []  # 所有玩家的副露
        self._hun_tile: Optional[Tile] = None
        self._current_player = 0
        self._phase = ""
        self._just_drew = False
        self._pending_actions: List[str] = []
        self._selected_tile_idx = -1
        self._need_discard = False
        self._restart_btn = None
        self._win_info = None
        self._hands_end = None
        self._pending_name = ""
        self._pending_room = None  # None=创建, str=加入
        self._waiting_continue = False
        self._continue_btn = None
        self._quit_btn = None

    def connect(self, host: str, port: int = 8765, name: str = "玩家", room_id: str = ""):
        self.status_text = f"连接 {host}:{port}..."
        self._pending_name = name
        self._pending_room = room_id
        self.net.connect(host, port)

    def join_or_create(self, room_id: str = ""):
        """加入房间，不存在则自动创建"""
        self.net.send({"type": "join_room", "room_id": room_id, "name": self._pending_name})
        self.status_text = f"房间 {room_id}..." if room_id else "创建房间..."

    def _on_connected(self):
        self.connected = True
        self.status_text = "已连接，正在操作..."
        print(f"[调试] _on_connected: _pending_room={self._pending_room!r}")
        # 连接后立即创建或加入房间
        self.join_or_create(self._pending_room)

    def _on_disconnected(self):
        self.connected = False
        if self.game_started and not self.game_over:
            self.status_text = "连接断开，AI代管中"
        else:
            self.status_text = "连接断开"

    def _on_message(self, msg: dict):
        t = msg.get("type", "")
        if t == "room_created":
            self.room_id = msg["room_id"]
            self.my_seat = msg["seat"]
            self._lobby_mode = True
            self.status_text = f"房间 {self.room_id} 已创建，等待准备..."
        elif t == "player_joined":
            if not self._lobby_mode:
                self._add_notification(f"{msg['name']} 加入了房间", (100, 255, 100))
        elif t == "ready_status":
            self._lobby_mode = True
            players = msg.get("players", [])
            ready_seats = msg.get("ready_seats", {})
            self._lobby_players = []
            for p in players:
                if p["name"] is not None:
                    self._lobby_players.append({
                        "seat": p["seat"],
                        "name": p["name"],
                        "ready": ready_seats.get(str(p["seat"]), False),
                    })
            self._is_ready = ready_seats.get(str(self.my_seat), False)
            self.status_text = f"已准备: {msg.get('ready_count', 0)}/{msg.get('human_count', 0)}"
        elif t == "game_start":
            self._handle_game_start(msg)
        elif t == "state_update":
            self._pending_actions = []  # 状态更新时清除旧操作
            self._handle_state_update(msg)
        elif t == "draw_tile":
            self._handle_draw_tile(msg)
        elif t == "action_needed":
            self._pending_actions = msg.get("actions", [])
            self._chi_options = [
                [Tile(d["suit"], d["value"]) for d in combo]
                for combo in msg.get("chi_options", [])
            ]
            print(f"[客户端] action_needed: actions={self._pending_actions} chi_options={self._chi_options}")
        elif t == "need_discard":
            self._pending_actions = []  # 轮到出牌，清除操作提示
            self._hand_tiles = [Tile(d["suit"], d["value"]) for d in msg.get("hand", [])]
            self._need_discard = True
            self._selected_tile_idx = -1
        elif t == "action_broadcast":
            self._pending_actions = []
            self._show_action_display(msg)
            self._add_action_notice(msg)
        elif t == "discard_broadcast":
            self._add_discard_notice(msg)
        elif t == "self_gang_options":
            pass  # 暂时简化
        elif t == "game_over":
            self._handle_game_over(msg)
        elif t == "continue_needed":
            self._waiting_continue = True
            self.status_text = "选择继续或退出..."
        elif t == "continue_result":
            if msg.get("all_continue"):
                self._add_notification("新一局开始！", (100, 255, 100))
            else:
                self._add_notification("游戏结束", (255, 100, 100))
                self.status_text = "其他玩家已退出"
                self._waiting_continue = False
        elif t == "error":
            self.status_text = f"错误: {msg.get('message', '')}"
        elif t == "player_disconnected":
            seat = msg.get("seat", -1)
            name = self.player_names[seat] if 0 <= seat < 4 and hasattr(self, "player_names") and seat < len(self.player_names) else f"玩家{seat}"
            self._add_notification(f"{name} 断线，AI代管", (255, 200, 100))

    def _handle_game_start(self, msg: dict):
        self.game_started = True
        self._lobby_mode = False
        self.game_over = False
        self._win_info = None
        self._waiting_continue = False
        self.my_seat = msg["seat"]
        players = msg.get("players", [])
        self.player_names = ["", "", "", ""]
        for p in players:
            self.player_names[p["seat"]] = p["name"]
        self._apply_state(msg.get("state", {}))

    def _handle_state_update(self, msg: dict):
        self._apply_state(msg)

    def _apply_state(self, state: dict):
        self._phase = state.get("phase", "")
        self._current_player = state.get("current_player", 0)
        if state.get("hun_tile"):
            self._hun_tile = Tile(state["hun_tile"]["suit"], state["hun_tile"]["value"])
        self._discard_pile = [Tile(d["suit"], d["value"]) for d in state.get("discard_pile", [])]
        self._hand_tiles = [Tile(d["suit"], d["value"]) for d in state.get("hand", [])]
        self._melds = state.get("melds", [])
        self._all_melds = state.get("all_melds", [])
        self._just_drew = state.get("just_drew", False)

    def _handle_draw_tile(self, msg: dict):
        tile_dict = msg.get("tile", {})
        if tile_dict:
            tile = Tile(tile_dict["suit"], tile_dict["value"])
            self._hand_tiles.append(tile)
            self._just_drew = True

    def _handle_game_over(self, msg: dict):
        self.game_over = True
        self._win_info = msg
        # 结算时显示所有手牌
        self._hands_end = []
        for i, hand in enumerate(msg.get("hands", [])):
            self._hands_end.append([Tile(d["suit"], d["value"]) for d in hand])

    # ===== 事件提示系统 =====

    _ACTION_LABELS = {
        "peng": "碰", "chi": "吃", "gang": "杠", "angang": "暗杠",
        "bugang": "补杠", "xuanfeng_gang": "旋风杠", "hu": "胡", "discard": "出牌",
    }
    _ACTION_COLORS = {
        "peng": (100, 200, 255), "chi": (100, 255, 100), "gang": (255, 200, 50),
        "angang": (255, 200, 50), "bugang": (255, 200, 50), "xuanfeng_gang": (255, 200, 50),
        "hu": (255, 100, 100), "discard": (200, 200, 200),
    }

    def _add_notification(self, text: str, color=(255, 255, 200)):
        self._notifications.append({"text": text, "timer": 60, "color": color})

    def _show_action_display(self, msg: dict):
        """显示中央大提示（含牌面）"""
        seat = msg.get("seat", -1)
        action = msg.get("action", "")
        name = self.player_names[seat] if 0 <= seat < 4 else f"玩家{seat}"
        label = self._ACTION_LABELS.get(action, action)
        tiles_data = msg.get("tiles", [])
        tiles = [Tile(d["suit"], d["value"]) for d in tiles_data] if tiles_data else None
        color = self._ACTION_COLORS.get(action, (255, 215, 0))
        self._action_display = {
            "text": f"{name}  {label}",
            "sub_text": None,
            "tiles": tiles,
            "color": color,
            "timer": 45,
        }

    def _add_action_notice(self, msg: dict):
        seat = msg.get("seat", -1)
        action = msg.get("action", "")
        name = self.player_names[seat] if 0 <= seat < 4 else f"玩家{seat}"
        label = self._ACTION_LABELS.get(action, action)
        color = self._ACTION_COLORS.get(action, (255, 255, 200))
        self._add_notification(f"{name}  {label}", color)

    def _add_discard_notice(self, msg: dict):
        seat = msg.get("seat", -1)
        name = self.player_names[seat] if 0 <= seat < 4 else f"玩家{seat}"
        self._add_notification(f"{name}  出牌", (180, 180, 180))

    def _update_notifications(self):
        if self._action_display:
            self._action_display["timer"] -= 1
            if self._action_display["timer"] <= 0:
                self._action_display = None
        expired = []
        for n in self._notifications:
            n["timer"] -= 1
            if n["timer"] <= 0:
                expired.append(n)
        for n in expired:
            self._notifications.remove(n)

    def _draw_action_display(self):
        """绘制中央大操作提示"""
        ad = self._action_display
        if not ad or ad["timer"] <= 0:
            return
        alpha = min(255, ad["timer"] * 6)
        color = tuple(min(255, max(0, c * alpha // 255)) for c in ad["color"])

        # 操作文字
        surf = self.title_font.render(ad["text"], True, color)
        tw, th = surf.get_size()
        x = (SCREEN_W - tw) // 2
        y = SCREEN_H // 3 - 20
        # 背景
        bg = pygame.Surface((tw + 40, th + 20))
        bg.set_alpha(min(200, alpha))
        bg.fill((0, 0, 0))
        self.screen.blit(bg, (x - 20, y - 10))
        self.screen.blit(surf, (x, y))

        # 牌面
        if ad["tiles"]:
            tile_w = TILE_W
            total_w = len(ad["tiles"]) * (tile_w + 4)
            tx = (SCREEN_W - total_w) // 2
            ty = y + th + 15
            for ti, tile in enumerate(ad["tiles"]):
                self.renderer.draw_tile(self.screen, tx + ti * (tile_w + 4), ty, tile.display(), tile=tile, font=self.font)
            # 外框
            pygame.draw.rect(self.screen, color,
                             (tx - 6, ty - 6, total_w + 12, TILE_H + 12), 3, border_radius=6)

    def _draw_notifications(self):
        if not self._notifications:
            return
        for i, n in enumerate(self._notifications[-3:]):  # 最多显示3条
            alpha = min(255, n["timer"] * 8)
            color = tuple(min(255, max(0, c * alpha // 255)) for c in n["color"])
            surf = self.font.render(n["text"], True, color)
            tw, th = surf.get_size()
            x = (SCREEN_W - tw) // 2
            y = 120 + i * 35
            # 背景
            bg = pygame.Surface((tw + 16, th + 6))
            bg.set_alpha(min(160, alpha // 2))
            bg.fill((10, 10, 10))
            self.screen.blit(bg, (x - 8, y - 3))
            self.screen.blit(surf, (x, y))

    # ===== 大厅（等待准备） =====

    def _handle_lobby_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "quit"
        elif event.type == pygame.MOUSEBUTTONDOWN:
            x, y = event.pos
            # 准备/取消准备按钮
            if 540 <= x <= 740 and 500 <= y <= 560:
                self._toggle_ready()

    def _toggle_ready(self):
        self.net.send({"type": "ready"})
        self._is_ready = not self._is_ready
        self.status_text = "已准备" if self._is_ready else "未准备"

    def _draw_lobby(self):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        # 房间号（醒目显示）
        room_label = self.font.render("房间号:", True, (255, 255, 200))
        room_surf = self.title_font.render(self.room_id, True, (255, 215, 0))
        # 背景框
        box_w = room_label.get_width() + room_surf.get_width() + 60
        box_h = 60
        box_x = (SCREEN_W - box_w) // 2
        box_y = 60
        pygame.draw.rect(self.screen, (40, 40, 40), (box_x, box_y, box_w, box_h), border_radius=10)
        pygame.draw.rect(self.screen, (255, 215, 0), (box_x, box_y, box_w, box_h), 3, border_radius=10)
        self.screen.blit(room_label, (box_x + 15, box_y + (box_h - room_label.get_height()) // 2))
        self.screen.blit(room_surf, (box_x + 30 + room_label.get_width(), box_y + (box_h - room_surf.get_height()) // 2))
        # 提示分享
        share_hint = self.font.render("将房间号告诉其他玩家，在连接界面输入加入", True, (180, 180, 180))
        shw, shh = share_hint.get_size()
        self.screen.blit(share_hint, ((SCREEN_W - shw) // 2, box_y + box_h + 8))

        # 玩家列表
        colors = [(200, 50, 50), (50, 150, 200), (50, 200, 50), (200, 150, 50)]
        start_y = 200
        for i, p in enumerate(self._lobby_players):
            y = start_y + i * 70
            is_me = p["seat"] == self.my_seat
            color = colors[p["seat"] % 4]

            # 座位背景
            rect = pygame.Rect(300, y, 600, 55)
            pygame.draw.rect(self.screen, (40, 40, 40), rect, border_radius=8)
            pygame.draw.rect(self.screen, color, rect, 2, border_radius=8)

            # 座位号
            seat_label = self.font.render(f"座位 {p['seat']}", True, color)
            self.screen.blit(seat_label, (320, y + 15))

            # 玩家名
            name_text = p["name"]
            if is_me:
                name_text += " (我)"
            name_surf = self.font.render(name_text, True, (255, 255, 255))
            self.screen.blit(name_surf, (450, y + 15))

            # 准备状态
            if p["ready"]:
                ready_surf = self.font.render("已准备", True, (100, 255, 100))
            else:
                ready_surf = self.font.render("未准备", True, (200, 200, 200))
            self.screen.blit(ready_surf, (700, y + 15))

        # 准备按钮
        btn_color = (80, 200, 80) if not self._is_ready else (200, 80, 80)
        btn_text = "准备" if not self._is_ready else "取消准备"
        btn_rect = pygame.Rect(540, 500, 200, 60)
        pygame.draw.rect(self.screen, btn_color, btn_rect, border_radius=12)
        pygame.draw.rect(self.screen, (255, 255, 255), btn_rect, 2, border_radius=12)
        btn_surf = self.font.render(btn_text, True, (255, 255, 255))
        btw, bth = btn_surf.get_size()
        self.screen.blit(btn_surf, (btn_rect.x + (btn_rect.w - btw) // 2, btn_rect.y + (btn_rect.h - bth) // 2))

        # 状态提示
        status_surf = self.font.render(self.status_text, True, INFO_COLOR)
        sw, sh = status_surf.get_size()
        self.screen.blit(status_surf, ((SCREEN_W - sw) // 2, 600))

    # ===== 操作发送 =====

    def send_discard(self, tile: Tile):
        self.net.send({
            "type": "action",
            "action": "discard",
            "tile": {"suit": tile.suit, "value": tile.value},
        })
        self._need_discard = False
        self._pending_actions = []
        self._selected_tile_idx = -1

    def send_action(self, action: str, tiles: list = None):
        msg = {"type": "action", "action": action}
        if tiles:
            msg["tiles"] = [{"suit": t.suit, "value": t.value} for t in tiles]
        print(f"[客户端] 发送操作: {action} tiles={tiles}")
        self.net.send(msg)
        self._pending_actions = []

    def send_continue(self, action: str):
        """发送继续/退出选择"""
        self.net.send({"type": "continue", "action": action})

    # ===== 事件处理 =====

    def handle_events(self, event):
        if self._lobby_mode:
            return self._handle_lobby_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "quit"
            elif event.key == pygame.K_h and "hu" in self._pending_actions:
                self.send_action("hu")
            elif event.key == pygame.K_p and "peng" in self._pending_actions:
                self.send_action("peng")
            elif event.key == pygame.K_g and "gang" in self._pending_actions:
                self.send_action("gang")
            elif event.key == pygame.K_c and "chi" in self._pending_actions:
                if len(self._chi_options) == 1:
                    self.send_action("chi", self._chi_options[0])
                elif len(self._chi_options) > 1:
                    self._waiting_chi = True  # 等待玩家选择组合
            elif event.key == pygame.K_SPACE:
                if self._pending_actions:
                    self.send_action("pass")
                elif self._need_discard and self._selected_tile_idx >= 0:
                    if self._selected_tile_idx < len(self._hand_tiles):
                        self.send_discard(self._hand_tiles[self._selected_tile_idx])
        elif event.type == pygame.MOUSEBUTTONDOWN:
            result = self._handle_click(event.pos)
            if result == "quit":
                return "quit"

    def _handle_click(self, pos):
        x, y = pos
        # 继续 / 退出 (游戏结束且等待选择)
        if self.game_over and self._continue_btn and self._continue_btn.collidepoint(pos):
            self.send_continue("continue")
            self._waiting_continue = True
            self._continue_btn = None
            self._quit_btn = None
            return
        if self.game_over and self._quit_btn and self._quit_btn.collidepoint(pos):
            self.send_continue("quit")
            return "quit"

        # 吃牌选择组合
        if self._waiting_chi and self._chi_options:
            total_w = len(self._chi_options) * 320
            start_x = (SCREEN_W - total_w) // 2
            for ci, combo in enumerate(self._chi_options):
                rx = start_x + ci * 320
                ry = SCREEN_H // 2
                if rx <= x <= rx + 300 and ry <= y <= ry + 60:
                    self.send_action("chi", combo)
                    self._waiting_chi = False
                    return

        # 操作按钮
        if self._pending_actions:
            for rect, action, _ in self._action_buttons:
                if rect.collidepoint(x, y):
                    if action == "pass":
                        self.send_action("pass")
                    elif action == "chi":
                        print(f"[客户端] 点击吃 _chi_options长度={len(self._chi_options)}")
                        if len(self._chi_options) == 1:
                            self.send_action("chi", self._chi_options[0])
                        elif len(self._chi_options) > 1:
                            self._waiting_chi = True
                        else:
                            print("[客户端] 无吃牌组合,从手牌构造")
                            # 无chi_options时的fallback
                    else:
                        self.send_action(action)
                    return

        # 出牌
        if self._need_discard and self._hand_tiles:
            hand = self._hand_tiles
            start_x = (SCREEN_W - len(hand) * (TILE_W + 4)) // 2
            tile_y = SCREEN_H - TILE_H - 30
            for i in range(len(hand)):
                tx = start_x + i * (TILE_W + 4)
                if tx <= x <= tx + TILE_W and tile_y <= y <= tile_y + TILE_H:
                    if self._selected_tile_idx == i:
                        self.send_discard(hand[i])
                    else:
                        if hand[i] != self._hun_tile:
                            self._selected_tile_idx = i
                    break

    def draw(self):
        self._update_notifications()

        if self._lobby_mode:
            self._draw_lobby()
            self._draw_notifications()
            return
        if not self.game_started:
            self._draw_waiting()
            return

        self._draw_online_info()
        self._draw_online_hand()
        self._draw_online_players()
        self._draw_online_discards()
        self._draw_online_controls()
        self._draw_notifications()
        self._draw_action_display()

        if self.game_over and self._win_info:
            self._draw_online_win()

        if self._waiting_continue:
            self._draw_continue_waiting()

    def _draw_waiting(self):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        text = f"房间 {self.room_id}" if self.room_id else self.status_text
        surf = self.title_font.render(text, True, (255, 255, 200))
        tw, th = surf.get_size()
        self.screen.blit(surf, ((SCREEN_W - tw) // 2, SCREEN_H // 2 - 80))
        if self.room_id:
            sub = self.font.render("等待其他玩家加入...", True, INFO_COLOR)
            sw, sh = sub.get_size()
            self.screen.blit(sub, ((SCREEN_W - sw) // 2, SCREEN_H // 2 + 10))

    def _draw_online_info(self):
        if self._hun_tile:
            surf = self.font.render(f"混: {self._hun_tile.display()}", True, HUN_COLOR)
            self.screen.blit(surf, (20, 50))
        phase_names = {"WAIT_ACTION": "等待", "DISCARD": "出牌", "DRAW": "摸牌", "SETTLE": "结算"}
        pn = phase_names.get(self._phase, self._phase)
        surf = self.font.render(f"当前: {self.player_names[self._current_player]}", True, INFO_COLOR)
        self.screen.blit(surf, (200, 50))
        surf = self.font.render(pn, True, INFO_COLOR)
        self.screen.blit(surf, (500, 50))

    def _draw_online_hand(self):
        if not self._hand_tiles:
            return
        hand = self._hand_tiles
        has_new = self._just_drew and self._current_player == self.my_seat
        n = len(hand)
        extra = TILE_W + 20 if has_new else 0
        total_w = (n - (1 if has_new else 0)) * (TILE_W + 4) + extra
        start_x = (SCREEN_W - total_w) // 2
        tile_y = SCREEN_H - TILE_H - 30
        for i, tile in enumerate(hand):
            x = start_x + i * (TILE_W + 4)
            if has_new and i == n - 1:
                x = start_x + (n - 1) * (TILE_W + 4) + 24
            is_selected = (i == self._selected_tile_idx)
            is_hun = (self._hun_tile and tile == self._hun_tile)
            self.renderer.draw_tile(self.screen, x, tile_y, tile.display(),
                                   tile=tile, selected=is_selected, is_hun=is_hun, font=self.font)
        # 自己的副露
        self._draw_melds_at(self.my_seat)

    def _draw_melds_at(self, seat: int):
        """在对应位置画副露（与单机模式一致）"""
        melds = self._all_melds[seat] if seat < len(self._all_melds) else []
        if not melds:
            return

        left_seat = (self.my_seat + 1) % 4
        top_seat = (self.my_seat + 2) % 4
        right_seat = (self.my_seat + 3) % 4

        if seat == self.my_seat:
            mx, my = 20, SCREEN_H - TILE_H - 110
            for m in melds:
                for td in m["tiles"]:
                    tile = Tile(td["suit"], td["value"])
                    self.renderer.draw_tile(self.screen, mx, my, tile.display(), tile=tile, font=self.font)
                    mx += TILE_W + 2
                mx += 10
        elif seat == left_seat:  # left (vertical)
            x, y = 60, SCREEN_H // 2 - 150
            for m in melds:
                draw_x = x
                if m["type"] == "an_gang":
                    for _ in m["tiles"]:
                        self.screen.blit(self.renderer.get_unknown_img(), (draw_x, y))
                        draw_x += TILE_W + 2
                else:
                    for td in m["tiles"]:
                        tile = Tile(td["suit"], td["value"])
                        self.renderer.draw_tile(self.screen, draw_x, y, tile.display(), tile=tile, font=self.font)
                        draw_x += TILE_W + 2
                y += TILE_H + 8
        elif seat == top_seat:  # top (horizontal, centered)
            total_w = sum(len(m["tiles"]) * (TILE_W + 2) for m in melds) + (len(melds) - 1) * 10
            x = (SCREEN_W - total_w) // 2
            y = 100
            for m in melds:
                if m["type"] == "an_gang":
                    for _ in m["tiles"]:
                        self.screen.blit(self.renderer.get_unknown_img(), (x, y))
                        x += TILE_W + 2
                else:
                    for td in m["tiles"]:
                        tile = Tile(td["suit"], td["value"])
                        self.renderer.draw_tile(self.screen, x, y, tile.display(), tile=tile, font=self.font)
                        x += TILE_W + 2
                x += 10
        elif seat == right_seat:  # right (vertical, right-aligned)
            margin = 20
            x, y = SCREEN_W - margin, SCREEN_H // 2 - 150
            for m in melds:
                meld_w = len(m["tiles"]) * (TILE_W + 2)
                draw_x = x - meld_w
                if m["type"] == "an_gang":
                    for _ in m["tiles"]:
                        self.screen.blit(self.renderer.get_unknown_img(), (draw_x, y))
                        draw_x += TILE_W + 2
                else:
                    for td in m["tiles"]:
                        tile = Tile(td["suit"], td["value"])
                        self.renderer.draw_tile(self.screen, draw_x, y, tile.display(), tile=tile, font=self.font)
                        draw_x += TILE_W + 2
                y += TILE_H + 8

    def _draw_online_players(self):
        # 对手信息
        left_seat = (self.my_seat + 1) % 4
        top_seat = (self.my_seat + 2) % 4
        right_seat = (self.my_seat + 3) % 4
        for seat in range(4):
            if seat == self.my_seat:
                continue
            name = self.player_names[seat] if seat < len(self.player_names) else f"P{seat}"
            if seat == left_seat:  # left (下家)
                surf = self.font.render(name, True, INFO_COLOR)
                self.screen.blit(surf, (10, SCREEN_H // 2 - 60))
            elif seat == top_seat:  # top (对家)
                surf = self.font.render(name, True, INFO_COLOR)
                tw = surf.get_width()
                self.screen.blit(surf, ((SCREEN_W - tw) // 2, 80))
            elif seat == right_seat:  # right (上家)
                surf = self.font.render(name, True, INFO_COLOR)
                tw = surf.get_width()
                self.screen.blit(surf, (SCREEN_W - tw - 10, SCREEN_H // 2 - 60))
            # 对方副露
            self._draw_melds_at(seat)

    def _draw_online_discards(self):
        if not self._discard_pile:
            return
        cols, gap = 15, 2
        col_w, row_h = DISCARD_W + gap, DISCARD_H + gap
        n = len(self._discard_pile)
        total_w = col_w * min(cols, n) - gap
        start_x, start_y = (SCREEN_W - total_w) // 2, 245
        for i, tile in enumerate(self._discard_pile):
            r, c = i // cols, i % cols
            x, y = start_x + c * col_w, start_y + r * row_h
            self.renderer.draw_small_tile(self.screen, x, y, tile,
                                         is_hun=(self._hun_tile and tile == self._hun_tile),
                                         font=self.font)

    def _draw_online_controls(self):
        self._action_buttons = []
        if self._pending_actions:
            real = [a for a in self._pending_actions if a != "pass"]
            has_pass = "pass" in self._pending_actions
            total = len(real) + (1 if has_pass else 0)
            gap = 10
            total_w = total * BTN_W + (total - 1) * gap
            start_x = (SCREEN_W - total_w) // 2
            btn_y = 190
            mx, my = pygame.mouse.get_pos()
            act_map = {"hu": "胡", "gang": "杠", "peng": "碰", "chi": "吃", "pass": "过"}
            for i, action in enumerate(real):
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
                i = len(real)
                x = start_x + i * (BTN_W + gap)
                rect = pygame.Rect(x, btn_y, BTN_W, BTN_H)
                color = BTN_PASS_HOVER if rect.collidepoint(mx, my) else BTN_PASS_COLOR
                pygame.draw.rect(self.screen, color, rect, border_radius=8)
                pygame.draw.rect(self.screen, (200, 200, 200), rect, 2, border_radius=8)
                surf = self.font.render("过", True, (255, 255, 255))
                tw, th = surf.get_size()
                self.screen.blit(surf, (x + (BTN_W - tw) // 2, btn_y + (BTN_H - th) // 2))
                self._action_buttons.append((rect, "pass", "过"))
        # 提示
        hints = "[H]胡 [P]碰 [G]杠 [C]吃 [空格]过/出牌"
        if self._need_discard:
            hints = "选择牌后 [空格] 出牌"
        surf = self.font.render(hints, True, INFO_COLOR)
        self.screen.blit(surf, (20, SCREEN_H - 40))

        # 吃牌选择组合
        if self._waiting_chi and self._chi_options:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H))
            overlay.set_alpha(160)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))
            label = self.font.render("选择吃牌组合:", True, (255, 255, 200))
            lw, lh = label.get_size()
            self.screen.blit(label, ((SCREEN_W - lw) // 2, SCREEN_H // 2 - 60))
            for ci, combo in enumerate(self._chi_options):
                cx = (SCREEN_W - len(self._chi_options) * 320) // 2 + ci * 320
                cy = SCREEN_H // 2
                # 显示三张牌
                for ti, tile in enumerate(combo):
                    tx = cx + ti * (TILE_W + 4)
                    self.renderer.draw_tile(self.screen, tx, cy, tile.display(), tile=tile, font=self.font)
                rect = pygame.Rect(cx, cy, 300, 55)
                pygame.draw.rect(self.screen, (80, 180, 80), rect, 3, border_radius=6)

    def _draw_online_win(self):
        info = self._win_info
        winner = info.get("winner")
        fan = info.get("fan_result")
        name = self.player_names[winner] if winner is not None and winner < len(self.player_names) else "?"
        title_surf = self.title_font.render(f"{name} 胡牌！", True, (255, 255, 0))
        tw, th = title_surf.get_size()
        self.screen.blit(title_surf, ((SCREEN_W - tw) // 2, SCREEN_H // 4))
        if fan:
            dy = SCREEN_H // 4 + th + 8
            score_text = f"总番: {fan.get('total_fan', 0)}  分数: {fan.get('total_score', 0)}"
            surf = self.font.render(score_text, True, (255, 255, 200))
            lx = (SCREEN_W - surf.get_width()) // 2
            self.screen.blit(surf, (lx, dy))
            dy += self.font.get_height() + 4
            details = fan.get("details", {})
            if details:
                line = " + ".join(f"{k}={v}" for k, v in details.items())
                surf = self.font.render(line, True, INFO_COLOR)
                lx = (SCREEN_W - surf.get_width()) // 2
                self.screen.blit(surf, (lx, dy))
                dy += self.font.get_height() + 4
        # 显示所有手牌
        if self._hands_end:
            dy = SCREEN_H // 4 + 160
            for seat in range(4):
                hand = self._hands_end[seat] if seat < len(self._hands_end) else []
                if not hand:
                    continue
                name = self.player_names[seat] if seat < len(self.player_names) else f"P{seat}"
                label = self.font.render(f"{name}:  ", True, INFO_COLOR)
                self.screen.blit(label, (20, dy))
                lx = 20 + label.get_width()
                for t in sorted(hand, key=lambda x: (x.suit, x.value)):
                    self.renderer.draw_small_tile(self.screen, lx, dy - 2, t,
                                                 is_hun=(self._hun_tile and t == self._hun_tile),
                                                 font=self.font)
                    lx += DISCARD_W + 4
                dy += DISCARD_H + 8

        # 继续 / 退出 按钮
        mx, my = pygame.mouse.get_pos()
        btn_y = SCREEN_H - 90
        # 继续
        cont_rect = pygame.Rect(SCREEN_W // 2 - 220, btn_y, 180, 55)
        cont_color = (60, 160, 60) if cont_rect.collidepoint(mx, my) else (40, 120, 40)
        pygame.draw.rect(self.screen, cont_color, cont_rect, border_radius=10)
        pygame.draw.rect(self.screen, (255, 255, 255), cont_rect, 2, border_radius=10)
        cont_surf = self.font.render("继续", True, (255, 255, 255))
        ctw, cth = cont_surf.get_size()
        self.screen.blit(cont_surf, (cont_rect.x + (cont_rect.w - ctw) // 2, cont_rect.y + (cont_rect.h - cth) // 2))
        self._continue_btn = cont_rect
        # 退出
        quit_rect = pygame.Rect(SCREEN_W // 2 + 40, btn_y, 180, 55)
        quit_color = (180, 60, 60) if quit_rect.collidepoint(mx, my) else (140, 40, 40)
        pygame.draw.rect(self.screen, quit_color, quit_rect, border_radius=10)
        pygame.draw.rect(self.screen, (255, 255, 255), quit_rect, 2, border_radius=10)
        quit_surf = self.font.render("退出", True, (255, 255, 255))
        qtw, qth = quit_surf.get_size()
        self.screen.blit(quit_surf, (quit_rect.x + (quit_rect.w - qtw) // 2, quit_rect.y + (quit_rect.h - qth) // 2))
        self._quit_btn = quit_rect

    def _draw_continue_waiting(self):
        """等待其他玩家选择继续"""
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(160)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        surf = self.font.render("等待其他玩家选择...", True, INFO_COLOR)
        tw, th = surf.get_size()
        self.screen.blit(surf, ((SCREEN_W - tw) // 2, SCREEN_H // 2 - 20))
        # 超时提示
        hint = self.font.render("90秒内未全部选择则自动退出", True, (200, 200, 200))
        hw, _ = hint.get_size()
        self.screen.blit(hint, ((SCREEN_W - hw) // 2, SCREEN_H // 2 + 20))

    def disconnect(self):
        self.net.disconnect()


# ===================== 主应用 =====================

class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("鞍山麻将")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('SimHei', FONT_SIZE)
        self.title_font = pygame.font.SysFont('SimHei', TITLE_SIZE)
        self.renderer = TileRenderer()

        self.mode = AppMode.MENU
        self.local_ui: Optional[LocalGameUI] = None
        self.online_ui: Optional[OnlineGameUI] = None

        # 连接界面输入
        self.connect_ip = "120.26.239.95"
        self.connect_port = "8765"
        self.connect_name = "玩家"
        self.connect_room = ""
        self.input_active = 0  # 0=IP, 1=Port, 2=Name, 3=Room
        self.status_text = ""

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif self.mode == AppMode.MENU:
                    self._handle_menu_event(event)
                elif self.mode == AppMode.CONNECT:
                    self._handle_connect_event(event)
                elif self.mode == AppMode.LOCAL_GAME:
                    if self.local_ui:
                        result = self.local_ui.handle_events(event)
                        if result == "quit":
                            self.mode = AppMode.MENU
                elif self.mode == AppMode.ONLINE_GAME:
                    if self.online_ui:
                        result = self.online_ui.handle_events(event)
                        if result == "quit":
                            self.online_ui.disconnect()
                            self.mode = AppMode.MENU

            # 更新
            if self.mode == AppMode.LOCAL_GAME and self.local_ui:
                self.local_ui.update()
            elif self.mode == AppMode.ONLINE_GAME and self.online_ui:
                pass  # 在线模式由网络消息驱动

            # 绘制
            self.screen.fill(BG_COLOR)
            if self.mode == AppMode.MENU:
                self._draw_menu()
            elif self.mode == AppMode.CONNECT:
                self._draw_connect()
            elif self.mode == AppMode.LOCAL_GAME and self.local_ui:
                self.local_ui.draw()
            elif self.mode == AppMode.ONLINE_GAME and self.online_ui:
                self.online_ui.draw()

            pygame.display.flip()
            self.clock.tick(30)

        # 清理
        if self.online_ui:
            self.online_ui.disconnect()
        pygame.quit()

    # ========== 菜单 ==========

    def _handle_menu_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            elif event.key == pygame.K_1:
                self._start_local()
            elif event.key == pygame.K_2:
                self.mode = AppMode.CONNECT
        elif event.type == pygame.MOUSEBUTTONDOWN:
            x, y = event.pos
            if 400 <= x <= 800:
                if 300 <= y <= 370:
                    self._start_local()
                elif 400 <= y <= 470:
                    self.mode = AppMode.CONNECT

    def _draw_menu(self):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        title_surf = self.title_font.render("鞍山麻将", True, (255, 215, 0))
        tw, th = title_surf.get_size()
        self.screen.blit(title_surf, ((SCREEN_W - tw) // 2, 150))

        btn_configs = [
            ("1. 本地游戏（VS CPU）", 300, BTN_COLOR, BTN_HOVER),
            ("2. 联网对战", 400, (50, 130, 50), (70, 160, 70)),
        ]
        mx, my = pygame.mouse.get_pos()
        for text, y, base, hover in btn_configs:
            rect = pygame.Rect(400, y, 400, 70)
            color = hover if rect.collidepoint(mx, my) else base
            pygame.draw.rect(self.screen, color, rect, border_radius=12)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=12)
            surf = self.font.render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            self.screen.blit(surf, (rect.x + (rect.w - tw) // 2, rect.y + (rect.h - th) // 2))

        hint = self.font.render("操作提示: [H]胡 [P]碰 [G]杠 [C]吃 [空格]出牌/过 [Esc]退出", True, INFO_COLOR)
        hw, hh = hint.get_size()
        self.screen.blit(hint, ((SCREEN_W - hw) // 2, 550))

    # ========== 连接界面 ==========

    def _handle_connect_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.mode = AppMode.MENU
            elif event.key == pygame.K_TAB:
                self.input_active = (self.input_active + 1) % 4
            elif event.key == pygame.K_RETURN:
                self._do_connect()
            elif event.key == pygame.K_BACKSPACE:
                if self.input_active == 0 and len(self.connect_ip) > 0:
                    self.connect_ip = self.connect_ip[:-1]
                elif self.input_active == 1 and len(self.connect_port) > 0:
                    self.connect_port = self.connect_port[:-1]
                elif self.input_active == 2 and len(self.connect_name) > 0:
                    self.connect_name = self.connect_name[:-1]
                elif self.input_active == 3 and len(self.connect_room) > 0:
                    self.connect_room = self.connect_room[:-1]
            else:
                ch = event.unicode
                if not ch:
                    return
                # 首次输入时清空默认值
                if self.input_active == 0 and self.connect_ip == "127.0.0.1":
                    self.connect_ip = ""
                elif self.input_active == 1 and self.connect_port == "8765":
                    self.connect_port = ""
                elif self.input_active == 2 and self.connect_name == "玩家":
                    self.connect_name = ""
                if self.input_active == 0 and (ch.isdigit() or ch == '.'):
                    self.connect_ip += ch
                elif self.input_active == 1 and ch.isdigit():
                    self.connect_port += ch
                elif self.input_active == 2 and ch.isprintable():
                    self.connect_name += ch
                elif self.input_active == 3 and ch.isalnum():
                    self.connect_room += ch.upper()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            x, y = event.pos
            # 连接按钮（根据房间号是否输入决定创建或加入）
            if 400 <= x <= 800 and 520 <= y <= 590:
                self._do_connect()

    def _do_connect(self):
        try:
            port = int(self.connect_port)
        except ValueError:
            port = 8765
        print(f"[调试] _do_connect: ip={self.connect_ip} port={port} name={self.connect_name} room={self.connect_room!r}")
        self.online_ui = OnlineGameUI(self.screen, self.font, self.title_font, self.renderer)
        self.online_ui.connect(self.connect_ip, port, self.connect_name, self.connect_room)
        self.mode = AppMode.ONLINE_GAME

    def _draw_connect(self):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        title_surf = self.title_font.render("联网对战", True, (255, 215, 0))
        tw, th = title_surf.get_size()
        self.screen.blit(title_surf, ((SCREEN_W - tw) // 2, 80))

        fields = [
            ("服务器地址:", self.connect_ip, 200),
            ("端口:", self.connect_port, 280),
            ("昵称:", self.connect_name, 360),
            ("房间号(留空=创建):", self.connect_room, 440),
        ]
        for label, value, y in fields:
            surf = self.font.render(label, True, INFO_COLOR)
            self.screen.blit(surf, (350, y))
            is_active = fields.index((label, value, y)) == self.input_active
            color = (200, 200, 100) if is_active else (255, 255, 255)
            pygame.draw.rect(self.screen, (60, 60, 60), (530, y - 5, 320, 35))
            pygame.draw.rect(self.screen, color, (530, y - 5, 320, 35), 2)
            val_surf = self.font.render(value, True, (255, 255, 255))
            self.screen.blit(val_surf, (535, y))

        mx, my = pygame.mouse.get_pos()

        if self.connect_room:
            btn_text = f"加入房间 {self.connect_room} [Enter]"
            btn_color = (50, 130, 50)
            btn_hover = (70, 160, 70)
        else:
            btn_text = "创建新房间 [Enter]"
            btn_color = BTN_COLOR
            btn_hover = BTN_HOVER

        rect1 = pygame.Rect(400, 520, 400, 70)
        color1 = btn_hover if rect1.collidepoint(mx, my) else btn_color
        pygame.draw.rect(self.screen, color1, rect1, border_radius=12)
        pygame.draw.rect(self.screen, (255, 255, 255), rect1, 2, border_radius=12)
        surf = self.font.render(btn_text, True, (255, 255, 255))
        tw, th = surf.get_size()
        self.screen.blit(surf, (rect1.x + (rect1.w - tw) // 2, rect1.y + (rect1.h - th) // 2))

        hint = self.font.render("[Tab]切换输入 [Enter]确认 [Esc]返回", True, INFO_COLOR)
        hw, hh = hint.get_size()
        self.screen.blit(hint, ((SCREEN_W - hw) // 2, 650))
        # 提示：输入房间号加入别人，留空则自己创建
        tip = self.font.render("提示：先在第一个窗口创建房间拿到房间号，再在第二个窗口输入房间号加入", True, (180, 180, 100))
        tw2, th2 = tip.get_size()
        self.screen.blit(tip, ((SCREEN_W - tw2) // 2, 700))

    def _start_local(self):
        self.local_ui = LocalGameUI(self.screen, self.font, self.title_font, self.renderer)
        self.mode = AppMode.LOCAL_GAME


if __name__ == "__main__":
    app = App()
    app.run()
