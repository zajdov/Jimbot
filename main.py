
import asyncio

from src.validator import Validator
from src.jimbot import Jimbot
from src.logger import log


async def main():

    log.info('starting jimbot')
    jimbot: Jimbot = Jimbot()

    validator: Validator = Validator()
    jimbot.validator = validator

    with open('token', 'r') as token_file:
        bot_token: str = token_file.read()

    await asyncio.gather(
        asyncio.create_task(jimbot.start(bot_token)),
        asyncio.create_task(validator.update_task())
    )


if __name__ == '__main__':
    asyncio.run(main())
