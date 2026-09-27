import pygame
import asyncio
import random as rand

running = True
header = 50
screen = None
board = None
font = None
fruits = [(2, 0)]

def write(txt, pos, color=(255, 0, 0)):
    screen.blit(font.render(txt, True, color), pos)

def set_pixel(color, pos):
    board.set_at(pos, color)

def clear():
    screen.fill((50, 0, 190))
    board.fill((0, 0, 0))

def new_fruit():
    x = rand.randrange(0, 14)
    y = rand.randrange(0, 14)
    fruits.append((x, y))

def stop(lost=0):
    global running
    if lost in [0, 1]:
        print('hey')
        running = False

class snake:
    pos = (0, 0)
    body = [(0, 0)]
    dir = (1, 0)
    
    def move():
        snake.pos = (snake.pos[0] + snake.dir[0], snake.pos[1] + snake.dir[1])
        if snake.pos in fruits:
            fruits.pop(fruits.index(snake.pos))
            new_fruit()
        elif snake.pos in snake.body[1:]:
            print('self')
            stop()
        else:
            snake.body.pop()
        snake.body = [snake.pos] + snake.body
        if snake.pos[0] > 14 or snake.pos[0] < 0 or snake.pos[1] > 14 or snake.pos[1] < 0:
            print('wall')
            stop()
            
    def draw():
        clear()
        for seg in snake.body:
            set_pixel((0, 0, 255), seg)
        for fruit in fruits:
            set_pixel((255, 0, 0), fruit)
        screen.blit(pygame.transform.scale(board, (screen.get_width(), screen.get_height() - header)), (0, header + 1))
        write("score=" + str(len(snake.body) - 2), (5, 5))

async def main():
    global screen, board, font, running
    
    # Initialize Pygame display and fonts inside async main
    screen = pygame.display.set_mode((900, 900 + header))
    board = pygame.surface.Surface((15, 15))
    pygame.font.init()
    font = pygame.font.SysFont(None, 50)
    
    new_fruit()

    while running:
        for k in pygame.event.get(768):  # pygame.KEYDOWN
            if hasattr(k, 'unicode'):
                if k.unicode == 'w' and snake.dir != (0, 1):
                    snake.dir = (0, -1)
                elif k.unicode == 's' and snake.dir != (0, -1):
                    snake.dir = (0, 1)
                elif k.unicode == 'a' and snake.dir != (1, 0):
                    snake.dir = (-1, 0)
                elif k.unicode == 'd' and snake.dir != (-1, 0):
                    snake.dir = (1, 0)
                    
        if len(pygame.event.get(pygame.QUIT)) > 0:
            stop()
            
        snake.move()
        snake.draw()
        pygame.display.flip()
        
        # Yield control back to the browser for 0.1 seconds
        await asyncio.sleep(0.1)

    pygame.quit()

# Start the async loop for PyScript
try:
    asyncio.get_running_loop().create_task(main())
except RuntimeError:
    asyncio.run(main())
