import pygame
import time

# ===============================================================================================
# CONFIGURATION UI & CONSTANTES
# ===============================================================================================

COL_BG      = (43, 43, 43)
COL_PANEL   = (50, 50, 50)
COL_HEADER  = (30, 30, 30)
COL_TEXT    = (220, 220, 220)
COL_TEXT_DIM= (150, 150, 150)

COL_BTN     = (70, 70, 70)
COL_BTN_HOV = (90, 90, 90)
COL_BTN_ACT = (58, 110, 165)
COL_BTN_DIS = (40, 40, 40)
COL_TAB_ACT = (60, 60, 60)   
COL_TAB_INA = (35, 35, 35)   

COL_FIELD   = (30, 30, 30)   
COL_FIELD_ACT= (0, 100, 150) 
COL_BORDER  = (30, 30, 30)
COL_BORDER_TABS  = (65, 65, 65)
COL_ACCENT  = (255, 165, 0)
COL_OVERLAY = (0, 0, 0, 180) 

VIEW_W, VIEW_H = 800, 600
PANEL_W = 320
WIN_W = VIEW_W + PANEL_W
WIN_H = VIEW_H

# ===============================================================================================
# WIDGETS
# ===============================================================================================

class UIElement:
    def draw(self, screen, fonts): pass
    def handle_event(self, event, state): return False

class Button(UIElement):
    def __init__(self, x, y, w, h, text, callback=None, data=None, toggle=False, group=None, color_override=None, border_override=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.data = data
        self.hover = False
        self.active = False
        self.toggle = toggle
        self.group = group 
        self.enabled = True
        self.color_override = color_override
        self.border_override = border_override
        self.corners = -1

    def draw(self, screen, fonts):
        if self.color_override:
            col = self.color_override if not self.active else COL_BTN_ACT
        else:
            col = COL_BTN_DIS if not self.enabled else (COL_BTN_ACT if self.active else (COL_BTN_HOV if self.hover else COL_BTN))
        
        col_border_final = self.border_override if self.border_override else COL_BORDER
        
        if isinstance(self.corners, dict):
            pygame.draw.rect(screen, col, self.rect, 
                             border_top_left_radius=self.corners.get('tl', 0),
                             border_top_right_radius=self.corners.get('tr', 0),
                             border_bottom_left_radius=self.corners.get('bl', 0),
                             border_bottom_right_radius=self.corners.get('br', 0))
                             
            pygame.draw.rect(screen, col_border_final, self.rect, 1, 
                             border_top_left_radius=self.corners.get('tl', 0),
                             border_top_right_radius=self.corners.get('tr', 0),
                             border_bottom_left_radius=self.corners.get('bl', 0),
                             border_bottom_right_radius=self.corners.get('br', 0))
        else:
            # Comportement standard (tous les coins arrondis à 4)
            pygame.draw.rect(screen, col, self.rect, border_radius=4)
            pygame.draw.rect(screen, col_border_final, self.rect, 1, border_radius=4)

        
        txt_col = COL_TEXT_DIM if not self.enabled else COL_TEXT
        f = fonts.get(13)
        txt_surf = f.render(self.text, True, txt_col)
        txt_rect = txt_surf.get_rect(center=self.rect.center)
        screen.blit(txt_surf, txt_rect)

    def handle_event(self, event, state):
        if not self.enabled: return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.hover:
                if self.toggle:
                    if self.group is not None:
                        for btn in self.group: btn.active = False
                    self.active = True
                else:
                    self.active = True
                if self.callback:
                    if self.data is not None: self.callback(self.data)
                    else: self.callback()
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.toggle: self.active = False
        return False

class Label(UIElement):
    def __init__(self, x, y, text, font_size=16, color=COL_TEXT, align="left", width=0):
        self.pos = (x, y)
        self.text = text
        self.color = color
        self.font_size = font_size
        self.align = align 
        self.width = width 
        self.enabled = True 

    def draw(self, screen, fonts):
        display_text = self.text() if callable(self.text) else str(self.text)
        f = fonts.get(self.font_size)
        surf = f.render(display_text, True, self.color)
        draw_pos = list(self.pos)
        if self.align == "center" and self.width > 0:
            txt_w = surf.get_width()
            draw_pos[0] = self.pos[0] + (self.width // 2) - (txt_w // 2)
        screen.blit(surf, draw_pos)

class NumberField(UIElement):
    def __init__(self, x, y, w, h, get_cb, set_cb):
        self.rect = pygame.Rect(x, y, w, h)
        self.get_cb = get_cb 
        self.set_cb = set_cb 
        self.active = False
        self.text_buffer = ""
        self.enabled = True
        self.cursor_pos = 0

    def draw(self, screen, fonts):
        if not self.enabled: return 
        col = COL_FIELD_ACT if self.active else COL_FIELD
        pygame.draw.rect(screen, col, self.rect, border_radius=4)
        pygame.draw.rect(screen, COL_BORDER, self.rect, 1, border_radius=4)
        
        display_txt = self.text_buffer if self.active else f"{self.get_cb():.2f}"
        f = fonts.get(14)
        surf = f.render(display_txt, True, COL_TEXT)
        txt_x = self.rect.x + 5
        txt_y = self.rect.centery - surf.get_height() // 2
        screen.blit(surf, (txt_x, txt_y))
        
        if self.active and time.time() % 1 > 0.5:
            txt_before_cursor = self.text_buffer[:self.cursor_pos]
            width_before = f.size(txt_before_cursor)[0]
            cursor_x = txt_x + width_before
            pygame.draw.line(screen, COL_TEXT, (cursor_x, self.rect.y + 4), (cursor_x, self.rect.bottom - 4), 1)

    def handle_event(self, event, state):
        if not self.enabled: return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.active = True
                self.text_buffer = str(round(self.get_cb(), 5)) 
                self.cursor_pos = len(self.text_buffer)
                state.typing_mode = True 
                return True
            else:
                if self.active: self.confirm(state) 
                return False
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER): self.confirm(state)
            elif event.key == pygame.K_ESCAPE:
                self.active = False; state.typing_mode = False
            elif event.key == pygame.K_LEFT:
                if self.cursor_pos > 0: self.cursor_pos -= 1
            elif event.key == pygame.K_RIGHT:
                if self.cursor_pos < len(self.text_buffer): self.cursor_pos += 1
            elif event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.text_buffer = self.text_buffer[:self.cursor_pos-1] + self.text_buffer[self.cursor_pos:]
                    self.cursor_pos -= 1
            else:
                if event.unicode in "0123456789.-":
                    self.text_buffer = self.text_buffer[:self.cursor_pos] + event.unicode + self.text_buffer[self.cursor_pos:]
                    self.cursor_pos += 1
            return True
        return False

    def confirm(self, state):
        try:
            val = float(self.text_buffer)
            self.set_cb(val)
            state.dirty = True
        except ValueError: pass 
        self.active = False
        state.typing_mode = False

class Slider(UIElement):
    def __init__(self, x, y, w, h, min_v, max_v, get_cb, set_cb, color_track=COL_BTN):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_v, self.max_v = min_v, max_v
        self.get_cb = get_cb
        self.set_cb = set_cb
        self.dragging = False
        self.color_track = color_track
        self.enabled = True

    def draw(self, screen, fonts):
        if not self.enabled: return
        pygame.draw.rect(screen, COL_PANEL, self.rect, border_radius=4)
        pygame.draw.rect(screen, COL_BORDER, self.rect, 1, border_radius=4)
        
        val = max(self.min_v, min(self.max_v, self.get_cb()))
        ratio = (val - self.min_v) / (self.max_v - self.min_v) if (self.max_v > self.min_v) else 0
        
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, int(self.rect.width * ratio), self.rect.height)
        pygame.draw.rect(screen, self.color_track, fill_rect, border_radius=4)
        handle_x = self.rect.x + int(self.rect.width * ratio)
        pygame.draw.circle(screen, COL_TEXT, (handle_x, self.rect.centery), 6)
        
        txt_col = (255,255,255) if ratio < 0.5 else (0,0,0)
        f = fonts.get(12)
        surf = f.render(f"{val:.2f}", True, txt_col)

    def handle_event(self, event, state):
        if not self.enabled: return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self.update_value(event.pos[0], state)
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                return True
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self.update_value(event.pos[0], state)
                return True
        return False

    def update_value(self, mouse_x, state):
        relative_x = mouse_x - self.rect.x
        ratio = max(0.0, min(1.0, relative_x / self.rect.width))
        new_val = self.min_v + ratio * (self.max_v - self.min_v)
        self.set_cb(new_val)
        state.dirty = True

class HeaderBar(UIElement):
    def __init__(self, x, y, w, h, color):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = color
        
    def draw(self, screen, fonts):
        pygame.draw.rect(screen, self.color, self.rect, border_radius=4)
        # Optionnel : petite bordure
        pygame.draw.rect(screen, COL_BORDER, self.rect, 1, border_radius=4)

# ===============================================================================================
# FACTORY HELPERS (Pour éviter la répétition dans les layouts)
# ===============================================================================================

def btn(target_list, x, y, w, h, txt, cb, data=None, toggle=False, grp=None, active=False, col_ov=None, bd_ov=None):
    """Crée un bouton, l'ajoute à la liste UI et gère le groupe/offset."""
    # Note : On utilise VIEW_W qui est défini plus haut dans ce fichier
    b = Button(VIEW_W + x, y, w, h, txt, cb, data, toggle, grp, col_ov, bd_ov)
    
    if active: 
        b.active = True
    
    # Gestion centralisée des groupes (Radio buttons)
    if grp is not None: 
        grp.append(b)
        
    target_list.append(b)
    return b

def lbl(target_list, x, y, txt, sz=16, col=COL_TEXT):
    """Crée un label avec l'offset VIEW_W et l'ajoute à la liste."""
    l = Label(VIEW_W + x, y, txt, sz, col)
    target_list.append(l)
    return l