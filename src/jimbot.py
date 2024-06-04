"""
Jimbot is a Discord application that provides some useful commands.

Features so far:
- LDTk map validator (use !validate with map attached)
- Wiki search (use !wiki <query>)

Features planned
- Link to debug tilesets
- LDTk map renderer
- Slash commands

TODO Attachment#save? 
TODO multiple attachments [103]
TODO Member / User
"""


from urllib import parse

from discord import (
    Attachment,
    Message,
    Intents,
    Client,
    Embed,
    Color
)

from src.validator import Validator
from src.renderer import Renderer
from src.logger import log


class Jimbot(Client):

    def __init__(self) -> None:
        intents: Intents = Intents.all()
        super().__init__(intents=intents)

        self.message_handlers: dict = {}
        self.map_validator: Validator
        self.map_renderer: Renderer

        self.allowed_channels: set = set()
        self.allowed_guilds: set = set()

    async def on_ready(self):
        log.info('jimbot is ready')

    def handle(self, message_content):

        def decorator(func):
            self.message_handlers[message_content] = func
            return func

        return decorator

    async def on_message(self, message: Message):

        if message.channel.id not in self.allowed_channels:
            return

        if message.author == self.user:
            return

        '''
        handler = self.message_handlers.get(message.content)
        if handler:
            handler(self, message)
        '''

        if message.content.startswith('!wiki'):
            await self.handle_wiki(message)

        elif message.content.startswith('!validate'):
            await self.handle_validate(message)

    async def handle_wiki(self, message: Message):

        content, channel = message.content, message.channel

        if len(arg_items := content.split(' ')) > 1:
            search_args: str = ' '.join(arg_items[1:]).strip()
            query: str = parse.quote(search_args)

            url_wiki: str = f'https://talesofyore.com/wiki/index.php?search={query}'

        else:
            url_wiki: str = 'https://talesofyore.com/wiki/index.php/Tales_of_Yore_Wiki'

        await channel.send(url_wiki)

    async def handle_validate(self, message: Message):
        validator, channel = self.map_validator, message.channel

        message_attachments: list[Attachment] = message.attachments
        if not message_attachments:
            await message.reply('nothing attached')
            return

        attachment: Attachment = message_attachments[0]
        file_name: str = attachment.filename

        accepted_types: tuple = ('.ldtk', '.ldtkl', '.json')
        if True not in {file_name.endswith(t) for t in accepted_types}:
            await message.reply('unknown file type')
            return

        if attachment.size > 8e6:
            await message.reply('file is too large')
            return

        async with channel.typing():

            result: tuple[int, int] | None = await validator.validate(map_url=attachment.url)

            if result is None:
                await channel.send('Something went wrong...\nLet me check the logs real quick - Jimbot')
            else:
                await channel.send(embed=self.generate_embed(*result, attachment.filename, message.author.id))

        await message.delete()

    def generate_embed(self, errors: int, warns: int, file_name: str, author_id: int) -> Embed:

        embed = Embed(
            title='LDTk Map Validator',
            description=f'Showing result for `{file_name}` uploaded by <@{author_id}>'
        )

        if not warns and not errors:
            embed.add_field(name='', value=':white_check_mark: No blank tiles were found')
            color: str = '#77B255'  # green

        elif warns > errors:
            embed.add_field(name='', value=f':warning: Warnings found: {warns}')
            if errors:
                embed.add_field(name='', value=f':no_entry_sign: Errors found: {errors}')
            color: str = '#FFCC4D'  # yellow

        else:
            embed.add_field(name='', value=f':no_entry_sign: Errors found: {errors}')
            if warns:
                embed.add_field(name='', value=f':warning: Warnings found: {warns}')
            color: str = '#DD2E44'  # red

        embed.color = Color.from_str(color)
        embed.set_footer(text='Validator scans the map for blank tiles on all layers. If a blank file is found in a collidable layer, it will count as an error, whereas non-collidable layer will result in a warning.')

        return embed
