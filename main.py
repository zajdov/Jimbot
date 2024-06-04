"""
This module is safe to run from any directory

dependencies in requirements.txt
"""


import asyncio

from os import chdir
from os import path

from src.validator import Validator
from src.renderer import Renderer
from src.jimbot import Jimbot


async def main():

    jimbot: Jimbot = Jimbot()
    renderer: Renderer = Renderer()
    validator: Validator = Validator()

    jimbot.map_validator = validator
    jimbot.map_renderer = renderer

    with open('token', 'r') as token_file:
        bot_token: str = token_file.read()

    await asyncio.gather(
        asyncio.create_task(jimbot.start(bot_token)),
        asyncio.create_task(validator.update_task())
    )


if __name__ == '__main__':
    chdir(path.dirname(__file__))
    asyncio.run(main())
