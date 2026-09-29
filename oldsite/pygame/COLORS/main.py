#colors

import pygame
import asyncio
import random as rand


async def main():
    globals()['running']=True
    globals()['screen']=pygame.display.set_mode((450,500))
    colors=[(0,0,0),(255,255,255),(255,0,0),(0,255,0),(0,0,255),(0,255,255),(255,0,255),(255,255,0)]
    i=0
    while globals()['running']:
        i+=1
        if i==len(colors):i=0
        screen.fill(colors[i])
        pygame.display.flip()
        print("tick")
        await asyncio.sleep(0.5)

try:
    asyncio.get_running_loop().create_task(main())
except RuntimeError:
    asyncio.run(main())