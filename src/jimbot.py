
import random

from urllib import parse
from datetime import datetime

from discord import (
    ActivityType,
    Attachment,
    Activity,
    Message,
    Intents,
    Status,
    Client,
    Embed,
    Color,
    File
)

from src.validator import Validator
from src.utils import handle
from src.logger import log


class Jimbot(Client):

    def __init__(self) -> None:
        intents: Intents = Intents.all()
        super().__init__(intents=intents)

        self.validator: Validator | None = None
        
        self.excluded_channels: set[int] = {
            1022973454233899169,  # in-game trading
            874390873566236712,  # in-game events
            913112950728958012,  # in-game chat
            983044877786968124  # in-game help
        }

        self.included_guilds: set[int] = {
            892815809569767524,  # testing
            870770948951924756  # tales of yore
        }

        self.message_reactions: dict[int, int] = {}
        self.message_handlers: dict[str, any] = {}

        handlers = filter(
            lambda a: getattr(a, '_is_handler', False),
            [getattr(self, a) for a in dir(self)]
        )

        for handler in handlers:
            message = handler.__name__.replace('_', '!')
            self.message_handlers[message] = handler

    async def on_ready(self):
        log.info('jimbot is ready')
        watching = Activity(name='!help', type=ActivityType.watching)
        await self.change_presence(status=Status.idle, activity=watching)
    
    async def on_reaction_add(self, reaction, user):

        if user == self.user:
            return

        if reaction.message.id not in self.message_reactions:
            return

        if self.message_reactions.pop(reaction.message.id, None) == user.id:
            await reaction.message.delete()
        
        else:
            await reaction.remove(user)

    async def on_message(self, message: Message):

        if message.guild.id not in self.included_guilds:
            return
        
        if message.channel.id in self.excluded_channels:
            return

        if not message.content.startswith('!'):
            return

        if message.author == self.user:
            return

        command: str = message.content.split(' ').pop(0)
        handler = self.message_handlers.get(command)
        if handler is None:
            return
        
        async with message.channel.typing():
            await handler(message)

    @handle
    async def _botjim(self, message: Message):
        await message.channel.send('Have you met my brother, he lives over in Cennym City?')

    @handle
    async def _mappers(self, message: Message):

        link_pack: str = 'https://drive.usercontent.google.com/uc?id=13UEnYDC6424LxnS6gCOPrvMM2ns6iXRI&export=download'
        link_debug: str = 'https://drive.usercontent.google.com/uc?id=1Hnh9-apkzs3iLPjm2pJFsrpASfUU_V0n&export=download'

        download_links: str = \
            f'- Updated Mapper Pack: [Download]({link_pack})' + \
            f'\n- Level Designer Toolkit: [Download](https://ldtk.io/download/)' + \
            f'\n- Debug Mapper Pack: [Download]({link_debug})'

        embed = Embed(
            title='Mappers - Links',
            description=download_links,
            color=Color.from_str('#FFFFFF')
        )

        embed.add_field(value='[**GUIDE**](https://talesofyore.com/docs/mappers.php)', name='')
        embed.add_field(value='[**UPLOAD**](https://node5.cokeandcode.com:8443/maps)', name='')
        embed.add_field(value='[**TEST**](https://talesofyore.com/staging)', name='')

        await message.channel.send(embed=embed)

    @handle
    async def _fwd(self, message: Message):

        arguments: list[str] = message.content.split(' ')

        message_text = ' '.join(arguments[2:]).strip()

        channel = await self.fetch_channel(arguments[1])
        await channel.send(message_text)

    @handle
    async def _changelog(self, message: Message):
        
        arguments: list[str] = message.content.split(' ')

        if len(arguments) > 1:
            try:
                version: int = int(arguments[1])

            except ValueError:
                version: int = self.validator.cached_version
            
            changelog: dict | None = await self.validator.fetch_changelog(version)
            embed_title: str = f'Showing Changelog for v{version}'
    
        else:
            version: int = self.validator.cached_version
            changelog: dict | None = await self.validator.fetch_changelog(version)
            embed_title: str = f'Latest Version v{version}'

        has_changes = type(changelog) is dict and changelog.get('changes')
        changes = '\n- ' + '\n- '.join(changelog['changes']) if has_changes \
            else 'No changes in this version'

        embed = Embed(
            title=embed_title,
            description=changes,
            color=Color.from_str('#FFFFFF')
        )

        if type(changelog) is dict and changelog.get('date'):
            embed.timestamp = datetime.fromtimestamp(changelog['date'])

        await message.channel.send(embed=embed)
        
    @handle
    async def _help(self, message: Message):

        commands_preview: str = \
            '- !validate (use with your map attached)' + \
            '\n- !changelog [version]' + \
            '\n- !wiki <query>' + \
            '\n- !mappers' + \
            '\n- !botjim' + \
            '\n- !fonu'

        embed = Embed(
            title='List of Commands',
            description=commands_preview,
            color=Color.from_str('#FFFFFF')
        )

        await message.channel.send(embed=embed)

    @handle
    async def _fonu(self, message: Message):

        if random.random() > 0.01:
            await message.channel.send('Fixed on Next Update')
        
        else:
            await message.channel.send('Friends of North Uganda')

    @handle
    async def _wiki(self, message: Message):

        if len(arg_items := message.content.split(' ')) > 1:
            search_args: str = ' '.join(arg_items[1:]).strip()
            query: str = parse.quote(search_args)

            url_wiki: str = f'https://talesofyore.com/wiki/index.php?search={query}'

        else:
            url_wiki: str = 'https://talesofyore.com/wiki/index.php/Tales_of_Yore_Wiki'

        await message.channel.send(url_wiki)

    @handle
    async def _validate(self, message: Message):

        if not message.attachments:
            await message.reply('To validate your map, upload the file with the command.')
            return

        attachment: Attachment = message.attachments[0]
        file_name: str = attachment.filename

        accepted_types: tuple = ('.ldtk', '.ldtkl', '.json')
        if True not in {file_name.endswith(t) for t in accepted_types}:
            await message.reply('I don\'t seem to recognize this file type.')
            return

        if attachment.size > 8e6:
            await message.reply('Your map is too large, maybe split into levels?')
            return

        log.info(f'attempting to validate {file_name} by {message.author.global_name}')

        if message.content == '!validate --update':
            await self.respond_update(message, attachment)
        
        elif message.content == '!validate':
            await self.respond_validate(message, attachment)

        await message.delete()

    async def respond_update(self, message: Message, attachment: Attachment):

        embed_success = Embed(
            title='LDtk Map Updater',
            description=f':white_check_mark: Your map `{attachment.filename}` has been updated successfully!\n\nReact to this message with :wastebasket: for deletion.',
            color=Color.from_str('#77B255'),
        )

        embed_warning = Embed(
            title='LDtk Map Updater',
            description=f':warning: Your map `{attachment.filename}` is already up-to-date.',
            color=Color.from_str('#FFCC4D')
        )

        embed_error = Embed(
            title='LDtk Map Updater',
            description=f':no_entry_sign: Failed to update `{attachment.filename}` uploaded by <@{message.author.id}> Sorry! \n\n<@503592464934764554> This is on You!',
            color=Color.from_str('#DD2E44')
        )

        update_result: bytes | bool = await self.validator.process_update(attachment)
        channel = message.channel

        if update_result is False:
            log.warn('failed updating map')
            await channel.send(embed=embed_error)
            return
        
        elif update_result is True:
            log.info('your map is already up-to-date')
            await channel.send(embed=embed_warning)
            return

        log.info('map updated successfully')

        try:
            updated_map: File = File(update_result, filename=f'updated_{attachment.filename}')
            bot_response: Message = await channel.send(embed=embed_success, file=updated_map)
            self.message_reactions[bot_response.id] = message.author.id
            await bot_response.add_reaction('🗑️')
    
        except Exception as e:
            await channel.send(embed=embed_error)
            log.error('failed uploading map:', e)

    async def respond_validate(self, message: Message, attachment: Attachment):

        channel, validator, author = message.channel, self.validator, message.author

        validation_result: tuple[int, int] | None = await validator.process_validate(attachment)

        if validation_result is None:
            await channel.send('Something went wrong...\nLet me check the logs real quick - Jimbot')
            return

        errors, warns = validation_result

        result_embed = Embed(
            title='LDTk Map Validator',
            description=f'Showing result for `{attachment.filename}` uploaded by <@{author.id}>'
        )

        field_ok: str = ':white_check_mark: No blank tiles were found'
        field_error: str = f':no_entry_sign: Errors found: {errors}'
        field_warn: str = f':warning: Warnings found: {warns}'

        if not warns and not errors:
            result_embed.color = Color.from_str('#77B255')
            result_embed.add_field(value=field_ok, name='')

        elif warns > errors:
            result_embed.color = Color.from_str('#FFCC4D')
            result_embed.add_field(value=field_warn, name='')
            if errors:
                result_embed.add_field(value=field_error, name='')

        else:
            result_embed.color = Color.from_str('#DD2E44')
            result_embed.add_field(value=field_error, name='', )
            if warns:
                result_embed.add_field(value=field_warn, name='')

        log.info('map validated successfully')

        result_embed.set_footer(text='Validator scans your map for empty tiles on all layers. If a tile is found in a collidable layer, it will count as an error, whereas non-collidable layer will result in a warning.')
        await channel.send(embed=result_embed)
