
import asyncio
import json
import io

import aiofiles
import aiopath
import aiohttp

from PIL import Image
from enum import Enum

from src.logger import log


class Tileset(Enum):

    FLOORS = 'floors.png'
    TILESET = 'tileset.png'
    TILESET2 = 'tileset2.png'

    def __init__(self, file_name) -> None:

        file_url: str = f'https://talesofyore.com/play/tilesets/{file_name}'

        self.blank_tiles: set[int] = set()
        self.file_name: str = file_name
        self.url: str = file_url
        self.image_object = None
    
    async def download(self, session: aiohttp.ClientSession) -> None:

        bytes_buffer: io.BytesIO = io.BytesIO()

        try:    
            async with session.get(url=self.url) as response:
                response.raise_for_status()

                async for chunk in response.content.iter_chunked(4096):
                    if chunk: bytes_buffer.write(chunk)

        except Exception as e:
            log.error('failed downloading', self.name, e)
            return
        
        self.image_object = Image.open(bytes_buffer).convert('RGBA')

    def retrieve_blanks(self) -> None:
        # modify the tileset to highlight empty tiles
        # and collect the tile ids for validator

        image: Image = self.image_object
        blanks: set[int] = self.blank_tiles

        if image is None:
            log.warn('missing image object in', self.name)
            return

        if image.width % 8 or image.height % 8:
            log.error('Invalid tileset dimensions of', self.name)
            return

        blank_tile: Image = Image.new('RGBA', (8, 8), (0,) * 4)
        tiles_x, tiles_y = image.width // 8, image.height // 8
        color_purple: tuple[int, ...] = (255, 0, 255, 127)

        for tile_id in range(tiles_x * tiles_y):

            tile_x = tile_id % tiles_x * 8
            tile_y = tile_id // tiles_x * 8

            tile_box: tuple = (
                tile_x,
                tile_y,
                tile_x + 8,
                tile_y + 8
            )

            if blank_tile.tobytes() == image.crop(tile_box).tobytes():
                image.paste(color_purple, tile_box)
                blanks.add(tile_id)

    async def save(self):
        # save the modified debug tileset
        # and list of its empty tiles to disk

        if not self.image_object or not self.blank_tiles:
            log.error(f'incomplete tileset object {self.name}')
            return

        image: Image = self.image_object
        bytes_buffer: io.BytesIO = io.BytesIO()
        image.save(bytes_buffer, format='PNG')
        
        try:
            await aiopath.AsyncPath('tilesets').mkdir(exist_ok=True)
            file_path: str = 'tilesets/' + self.file_name
            async with aiofiles.open(file_path, 'wb') as file:
                await file.write(bytes_buffer.getbuffer())
        
        except Exception as e:
            log.error(f'saving {self.file_name} failed:', e)

        try:
            await aiopath.AsyncPath('blanks').mkdir(exist_ok=True)
            file_path: str = 'blanks/' + self.name
            async with aiofiles.open(file_path, 'w') as file:
                for tile_id in self.blank_tiles:
                    await file.write(f'{tile_id}\n')
        
        except Exception as e:
            log.error(f'saving {self.name} failed:', e)


class LDtkMap:
    
    def __init__(self, data: dict) -> None:
        self.levels: list[LDtkLevel] = []
        self.warnings: int = 0
        self.errors: int = 0
        self.data = data

        for level_data in data.get('levels'):
            ldtk_level = LDtkLevel(level_data)
            self.levels.append(ldtk_level)

    def validate_levels(self) -> tuple[int, int]:
        for ldtk_level in self.levels:
            errors, warnings = ldtk_level.validate_layers()
            
            self.errors += errors
            self.warnings += warnings
        
        return self.errors, self.warnings

    def update_definitions(self, defs_new: dict) -> bytes | bool:
        # returns bytes: successfully updated
        # returns True: already up-to-date
        # return False: failed to update
        
        # replace tileset paths with relative when pulling from /maps
        # avoid fatal error by replacing layers.OverAll.uid from 410 to 167
        # self.cached_defs['layers'][1]['uid'] = 167

        # TODO remove hard-coded lengths
        # TODO keep old enums

        defs_old: dict = self.data['defs']
        try:
            if (
                len(defs_old['levelFields']) == 23 and
                len(defs_old['entities']) == 19 and
                len(defs_old['tilesets']) == 3 and
                len(defs_old['layers']) == 12
            ):
                return True
        
        except KeyError as e:
            log.error('missing field:', e)
            return False

        try:
            self.data['defs'] = defs_new
            json_str: str = json.dumps(self.data)
            json_bytes: bytes = json_str.encode()
            bytes_buffer = io.BytesIO(json_bytes)

        except Exception as e:
            log.error('failed deserialization of updated map:', e)
            return False

        return bytes_buffer


class LDtkLevel:

    LAYERS: dict = {
        'OverAll2': Tileset.TILESET2,
        'OverAll': Tileset.TILESET,
        'InfontAndBehind': Tileset.TILESET,
        'Walls2': Tileset.TILESET2,
        'Walls': Tileset.TILESET,
        'Objects2': Tileset.TILESET2,
        'Objects': Tileset.TILESET,
        'Decal2': Tileset.TILESET2,
        'Decal': Tileset.TILESET,
        'Floor': Tileset.FLOORS,
        'Reflective': Tileset.FLOORS,
    }

    COLLIDABLE: tuple = (
        'Walls', 'Walls2', 'Objects', 'Objects2'
    )

    def __init__(self, data: dict) -> None:
        self.layers = data.get('layerInstances', [])
        self.warnings: int = 0
        self.errors: int = 0

    def validate_layers(self) -> tuple[int, int]:

        for layer in self.layers:
            layer_id: str = layer.get('__identifier')
            if layer_id not in self.LAYERS or not layer.get('gridTiles'):
                continue

            blank_tiles: int = self.count_holes(layer, layer_id)

            if layer_id in self.COLLIDABLE:
                self.errors += blank_tiles
            else:
                self.warnings += blank_tiles
        
        return self.errors, self.warnings

    def count_holes(self, layer: dict, layer_id: str) -> int:

        tileset: Tileset = self.LAYERS.get(layer_id)
        tiles_counted: int = 0

        for tile in layer.get('gridTiles', []):
            if tile.get('t') in tileset.blank_tiles:
                tiles_counted += 1
        
        return tiles_counted


class Validator:

    def __init__(self) -> None:
        self.client_session: aiohttp.ClientSession | None = None
        self.update_interval: int = 12 * 60 * 60
        self.cached_version: int = 0
        self.cached_defs: dict = {}

    async def process_validate(self, attachment) -> tuple[int, int] | None:
        # only LDTk version matters due to JSON schema
        # tileset version is irrelevant as tile positions
        # are not changed, but new tiles are added

        try:
            await attachment.save(
                bytes_buffer := io.BytesIO()
                # seek_begin=True, use_cached=True
            )
        
        except Exception as e:
            log.error('failed downloading map:', e)
            return

        # create project here
        # class Project?

        try:
            await aiopath.AsyncPath('saved').mkdir(exist_ok=True)
                
            file_path: str = f'./saved/{attachment.filename}'
            async with aiofiles.open(file_path, 'wb') as map_file:
                await map_file.write(bytes_buffer.getvalue())
        
        except Exception as e:
            log.warn('failed saving map:', e)

        try:
            decoded_str: str = bytes_buffer.getvalue().decode()
            json_object: dict = json.loads(decoded_str)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.error('failed decoding map:', e)
            return

        if 'levels' in json_object:
            ldtk_map = LDtkMap(json_object)
            return ldtk_map.validate_levels()
        
        elif 'layerInstances' in json_object:
            ldtk_level = LDtkLevel(json_object)
            return ldtk_level.validate_layers()

        else:
            log.error('failed parsing map')

    async def process_update(self, attachment) -> bytes | bool:
        # returns bytes: successfully updated
        # returns True: already up-to-date
        # return False: failed to update
        
        try:
            await attachment.save(
                bytes_buffer := io.BytesIO()
            )
        
        except Exception as e:
            log.error('failed downloading map:', e)
            return False

        try:
            decoded_str: str = bytes_buffer.getvalue().decode()
            json_object: dict = json.loads(decoded_str)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.error('failed parsing map:', e)
            return False
        
        if 'defs' not in json_object:
            return False
        
        ldtk_map = LDtkMap(json_object)
        return ldtk_map.update_definitions(defs_new=self.cached_defs)

    async def fetch_changelog(self, version: int) -> dict | None:

        changelog_url: str = f'https://talesofyore.com/play/changelog/{version}.json'

        bytes_buffer: bytearray = bytearray()

        try:
            async with self.client_session.get(url=changelog_url) as response:

                if response.status == 404:
                    return

                elif not response.ok:
                    log.error('failed request. Status:', response.status)
                    return

                async for chunk in response.content.iter_chunked(4096):
                    if chunk: bytes_buffer.extend(chunk)

        except Exception as e:
            log.error('failed fetching changelog v', version, e)
            return
        
        try:
            decoded_str: str = bytes_buffer.decode()
            json_object: dict = json.loads(decoded_str)

        except (json.JSONDecodeError, UnicodeDecodeError):
            log.error('failed parsing json')
            return
        
        if type(json_object) is dict:
            return json_object

    async def fetch_version(self) -> int:
        
        url_version: str = 'https://talesofyore.com/play/version'

        async with self.client_session.get(url=url_version) as response:
            response.raise_for_status()

            response_text = await response.text()

            try:
                current_version: int = int(response_text.strip())
            
            except ValueError:
                log.error(f'invalid version "{response_text}"')
            
        return current_version

    async def process_tilesets(self) -> None:

        for tileset in Tileset:
            await tileset.download(session=self.client_session)
            tileset.retrieve_blanks()
            await tileset.save()

    async def save_version(self) -> None:
        try:
            async with aiofiles.open('version', 'w') as file:
                await file.write(str(self.cached_version))
        
        except Exception as e:
            log.error('failed saving version file:', e)

    async def load_cached(self) -> None:

        # TODO move this down once version dependent
        defs_path: str = 'defs'
        if await aiopath.AsyncPath(defs_path).exists():
            async with aiofiles.open(defs_path, 'r') as defs_file:
                defs_content: str = await defs_file.read()
                self.cached_defs = json.loads(defs_content)
        else:
            log.warn(f'file "{defs_path}" was not found')

        if not await aiopath.AsyncPath('version').exists():
            return
        
        for tileset in Tileset:

            tileset_path: str = 'tilesets/' + tileset.file_name
            if await aiopath.AsyncPath(tileset_path).exists():

                async with aiofiles.open(tileset_path, 'rb') as tileset_file:
                    image_data: bytes = await tileset_file.read()
                
                tileset.image_object = Image.open(io.BytesIO(image_data))

            else:
                log.warn('no tileset file for', tileset.name)
                continue
            
            blanks_path: str = 'blanks/' + tileset.name
            if not await aiopath.AsyncPath(blanks_path).exists():
                log.warn('no blank tiles file for', tileset.name)
                continue

            async with aiofiles.open(blanks_path, 'r') as blanks_file:
                tileset.blank_tiles = \
                    {int(n) for n in await blanks_file.readlines() if n}
        
        async with aiofiles.open('version', 'r') as version_file:
            version_content: str = await version_file.read()
            self.cached_version = int(version_content)
        
    async def update_task(self):
        try:
            await self.load_cached()
        
        except Exception as e:
            log.error('failed loading cached files:', e)

        async with aiohttp.ClientSession() as session:
            self.client_session = session

            while True:
                latest_version: int = await self.fetch_version()

                if latest_version > self.cached_version:
                    self.cached_version = latest_version
                    log.info('new version released')
                    await self.process_tilesets()
                    await self.save_version()

                await asyncio.sleep(self.update_interval)
