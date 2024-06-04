"""
validator.py

TODO: cached maps index
TODO: JSON schema version
"""


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

    FLOORS = ('floors.png', 'https://talesofyore.com/play/tilesets/floors.png')
    TILESET = ('tileset.png', 'https://talesofyore.com/play/tilesets/tileset.png')
    TILESET2 = ('tileset2.png', 'https://talesofyore.com/play/tilesets/tileset2.png')

    def __init__(self, file_name, url) -> None:
        self.blank_tiles: set[int] = set()
        self.file_name: str = file_name
        self.image_object: Image
        self.url: str = url


class Validator:

    def __init__(self) -> None:
        self.client_session: aiohttp.ClientSession
        self.update_interval: int = 12 * 60 * 60
        self.cached_version: int = 0

    async def validate(self, map_url: str) -> tuple[int, int] | None:
        """
        
        only LDTk version matters due to JSON schema
        tileset version is irrelevant as tile positions
        are not changed, but new tiles are added

        """
        session: aiohttp.ClientSession = self.client_session
        
        try:
            async with session.get(url=map_url) as response:

                content: aiohttp.StreamReader = response.content

                if not response.ok:
                    log.error('failed request. Status:', response.status)
                    return

                bytes_buffer: bytearray = bytearray()

                async for chunk in content.iter_chunked(4096):
                    if not chunk: break
                    bytes_buffer.extend(chunk)

        except Exception as e:
            log.error('failed downloading map:', e)
            return

        try:
            decoded_str: str = bytes_buffer.decode('utf-8')
            json_object: dict = json.loads(decoded_str)

        except (json.JSONDecodeError, UnicodeDecodeError):
            log.error('failed parsing json')
            return

        if 'layerInstances' in json_object:
            level = MapLevel(json_object)
            return level.validate_layers()

        if 'levels' in json_object:
            warnings: int = 0
            errors: int = 0

            for level_instance in json_object['levels']:
                level = MapLevel(level_instance)
                e, w = level.validate_layers()
                warnings += w
                errors += e
            
            return (errors, warnings)

    async def download_tileset(self, tileset: Tileset):

        bytes_buffer: io.BytesIO = io.BytesIO()
        session: aiohttp.ClientSession = self.client_session
            
        async with session.get(url=tileset.url) as response:

            if response.ok:
                while True:
                    chunk = await response.content.read(1024)
                    if not chunk: break
                    bytes_buffer.write(chunk)
            else:
                response.raise_for_status()

        bytes_buffer.seek(0)
        tileset.image_object = Image.open(bytes_buffer).convert('RGBA')

    async def cache_tileset(self, tileset: Tileset):
        """
        
        save the modified debug tilesetand 
        and list of its empty tiles to disk
        
        """

        if not tileset.image_object or not tileset.blank_tiles:
            log.error(f'incomplete tileset object {tileset.name}')
            return

        image: Image = tileset.image_object
        bytes_buffer: io.BytesIO = io.BytesIO()
        image.save(bytes_buffer, format='PNG')
        
        try:
            await aiopath.AsyncPath('tilesets').mkdir(exist_ok=True)
            file_path: str = 'tilesets/' + tileset.file_name
            async with aiofiles.open(file_path, 'wb') as file:
                await file.write(bytes_buffer.getbuffer())
        
        except Exception as e:
            log.error(f'saving {tileset.file_name} failed', e)

        try:
            await aiopath.AsyncPath('blanks').mkdir(exist_ok=True)
            file_path: str = 'blanks/' + tileset.name
            async with aiofiles.open(file_path, 'w') as file:
                for tile_id in tileset.blank_tiles: await file.write(f'{tile_id}\n')
        
        except Exception as e:
            log.error(f'saving {tileset.name} failed', e)

    async def retrieve_blanks(self, tileset: Tileset):
        """
        
        modify the tileset to highlight empty tiles
        and collect the tile ids for validator
        
        """

        image: Image = tileset.image_object
        blanks: set[int] = tileset.blank_tiles

        if image.width % 8 or image.height % 8:
            log.error('Invalid tileset dimnesions')
            return

        blank_tile: Image = Image.new('RGBA', (8, 8), (0,) * 4)
        tiles_x, tiles_y = image.width // 8, image.height // 8
        COLOR_PURPLE: tuple[int] = (255, 0, 255, 127)

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
                image.paste(COLOR_PURPLE, tile_box)
                blanks.add(tile_id)
        
    async def get_version(self) -> int:
        
        url_version: str = 'https://talesofyore.com/play/version'

        session: aiohttp.ClientSession = self.client_session

        async with session.get(url=url_version) as response:
            if response.ok:
                response_text = await response.text()
                try:
                    current_version: int = int(response_text.strip())
                
                except ValueError:
                    log.error(f'invalid version ({response_text})')
            
            else:
                response.raise_for_status()
        
        return current_version

    async def process_tilesets(self):

        for tileset in Tileset:
            await self.download_tileset(tileset)
            await self.retrieve_blanks(tileset)
            await self.cache_tileset(tileset)

    async def save_version(self, version: int):
        try:
            async with aiofiles.open('version', 'w') as file:
                await file.write(str(version))
        
        except Exception as e:
            log.error('failed saving version file', e)

    async def load_cached(self) -> None:

        if not await aiopath.AsyncPath('version').exists():
            return
        
        async with aiofiles.open('version', 'r') as version_file:
            file_content: str = await version_file.read()
            self.cached_version = int(file_content)

        for tileset in Tileset:
            file_path: str = 'blanks/' + tileset.name
            async with aiofiles.open(file_path, 'r') as file:
                tileset.blank_tiles = {int(a) for a in await file.readlines() if a}

    async def update_task(self):

        try:
            await self.load_cached()
        
        except Exception as e:
            log.error('failed loading from cache', e)

        async with aiohttp.ClientSession() as session:
            self.client_session = session

            while True:
                latest_version: int = await self.get_version()
                if latest_version > self.cached_version:
                    log.info('new version released')
                    self.cached_version = latest_version
                    await self.save_version(latest_version)
                    await self.process_tilesets()
                else:
                    log.info('validator up to date')

                await asyncio.sleep(self.update_interval)


class MapLevel:

    LAYER_MAP: dict = {
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

    def __init__(self, data: dict) -> None:
        self.layers = data.get('layerInstances', [])

    def validate_layers(self) -> tuple[int, int]:
        
        warnings: int = 0
        errors: int = 0

        for layer in self.layers:
            indentifier: str = layer.get('__identifier')
            if not indentifier in self.LAYER_MAP or not layer.get('gridTiles'):
                continue

            tileset: Tileset = self.LAYER_MAP.get(indentifier)

            colidable: bool = indentifier in (
                'Walls', 'Walls2', 'Objects', 'Objects2'
            )

            blank_tiles: int = self.count_holes(layer, tileset)

            if colidable:
                errors += blank_tiles
            else:
                warnings += blank_tiles
        
        return (errors, warnings)

    def count_holes(self, layer: dict, tileset: Tileset) -> int:
        
        tiles_counted: int = 0

        for tile in layer.get('gridTiles', []):
            if tile.get('t') in tileset.blank_tiles:
                tiles_counted += 1
        
        return tiles_counted
