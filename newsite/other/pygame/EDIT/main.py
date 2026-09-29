import configparser
import os
import pygame

def get_configs(configfile, section, defalts={}):
    try:
        nf = open(configfile, 'x')
        nf.writelines("""
[editor]
background_color=0,0,0
text_color=255,255,255
line_spacing=15
font_name=None
font_size=22
highlight_color=255,255,0
resolution=300,400
start_scroll_line=10
defalt_file=untitled.txt
""")
        nf.close()
    except:
        pass
    
    cp = configparser.ConfigParser()
    cp.read(configfile)
    try:
        cd = cp.__dict__['_sections'][section]
    except:
        cd = {section: {}}
        
    class config:
        pass
        
    for i in defalts.items():
        setattr(config, i[0], i[1])
    for i in cd.items():
        setattr(config, i[0], i[1])
    return config

# Safe virtual profile path
config_file = '.LDpyEDITOR_profile'
configs = get_configs(config_file, 'editor', {
    'defalt_file': 'untitled.txt',
    'resolution': '300,400',
    'start_scroll_line': '10',
    'highlight_color': '255,255,0',
    'background_color': '0,0,0',
    'text_color': '255,255,255',
    'line_spacing': '15',
    'font_name': None,
    'font_size': '22'
})

def llist(cs):
    out = []
    t = str(cs).split(',')
    for i in t:
        out.append(int(i.strip()))
    return tuple(out)
    
configs.line_spacing = int(configs.line_spacing)
configs.font_size = int(configs.font_size)
configs.highlight_color = llist(configs.highlight_color)
configs.text_color = llist(configs.text_color)
configs.background_color = llist(configs.background_color)
configs.resolution = llist(configs.resolution)
configs.start_scroll_line = int(configs.start_scroll_line)

color = configs.text_color
screen = pygame.display.set_mode(configs.resolution)
pygame.font.init()

FC = [""]
font = pygame.font.SysFont(configs.font_name, int(configs.font_size))

def draw():
    screen.fill(configs.background_color)
    Li = -1
    for L in range(len(FC)):
        Li += 1
        if L > configs.start_scroll_line:
            Li = configs.start_scroll_line
        
        line_surface = font.render(str(L) + ": " + FC[L], True, color)
        screen.blit(line_surface, (0, Li * configs.line_spacing))
        
        if L == l:
            carrot = str(L) + ": " + FC[L][:c] + "_"
            carrot_surface = font.render(carrot, True, configs.highlight_color)
            screen.blit(carrot_surface, (0, Li * configs.line_spacing))
            
    pygame.display.flip()

def join(lst, WITH=''):
    out = ""
    for i in range(len(lst)):
        out += lst[i]
        if i < len(lst) - 1:
            out += WITH
    return out

def OPEN(file, mode='r'):
    try:
        f = open(file, mode)
    except:
        if mode.lower() == 'r':
            try:
                open(file, 'x').close()
            except:
                pass
            f = open(file, 'r')
        elif mode.lower() == 'w':
            f = open(file, 'w')
    return f

def read_file(FILE):
    try:
        F = OPEN(FILE)
        globals()['FC'] = join(F.readlines()).split("\n")
        F.close()
    except:
        globals()['FC'] = [""]
    globals()['curfile'] = FILE

curfile = configs.defalt_file
read_file(curfile)

running = True
l = 0
c = 0
clock = pygame.time.Clock()

def main_loop():
    global running, l, c
    draw()
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            K = event.key
            
            if K == pygame.K_ESCAPE:
                running = False
            elif K == pygame.K_RETURN or K == pygame.K_KP_ENTER:
                FC.insert(l + 1, "")
                FC[l + 1] = FC[l][c:]
                FC[l] = FC[l][:c]
                l += 1
                c = 0
            elif K == pygame.K_BACKSPACE:
                if c == 0 and l > 0:
                    c = len(FC[l - 1])
                    FC[l - 1] = FC[l - 1] + FC[l]
                    FC.pop(l)
                    l -= 1
                elif c > 0:
                    FC[l] = FC[l][:c - 1] + FC[l][c:]
                    c -= 1
            elif K == pygame.K_DELETE:
                if c == len(FC[l]) and l < len(FC) - 1:
                    FC[l] = FC[l] + FC[l + 1]
                    FC.pop(l + 1)
                elif c < len(FC[l]):
                    FC[l] = FC[l][:c] + FC[l][c + 1:]
            elif K == pygame.K_LEFT:
                if c > 0: c -= 1
            elif K == pygame.K_RIGHT:
                if c < len(FC[l]): c += 1
            elif K == pygame.K_UP:
                if l > 0: l -= 1
            elif K == pygame.K_DOWN:
                if l < len(FC) - 1: l += 1
            elif event.unicode and event.unicode.isprintable() and event.unicode != '\r':
                FC[l] = FC[l][:c] + event.unicode + FC[l][c:]
                c += len(event.unicode)

# Pygame loop runner for PyScript
import asyncio

async def run():
    while running:
        main_loop()
        await asyncio.sleep(0.01)

asyncio.get_running_loop().create_task(run())