import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
import math
import time
import random
import copy
import hashlib
import io
import magic
from pathlib import Path

import aiohttp
from discord.ext import commands, tasks

from cogs.utils import Utils
from cogs.utils import print_color


async def check_contract_alchemy(url: str, contract: str):
    try:
        # url: with key
        # example: https://eth-mainnet.g.alchemy.com/nft/v2/demo/getContractMetadata?contractAddress=0x....'
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={'Content-Type': 'application/json'},
                timeout=32
            ) as response:
                if response.status == 200:
                    res_data = await response.read()
                    res_data = res_data.decode('utf-8')
                    await session.close()
                    decoded_data = json.loads(res_data)
                    if decoded_data and 'contractMetadata' in decoded_data and "tokenType" in decoded_data['contractMetadata']:
                        return decoded_data
                elif response.status == 400:
                    return None
    except asyncio.TimeoutError:
        print('timeout: {} check_contract_alchemy {}s'.format(url))
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None

# Cog class
class AlchemyAPI(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self.utils = Utils(self.bot)
        self.last_eth = 0
        self.last_polygon = 0

    async def get_block_number(self, url: str, timeout: int=16):
        json_data = {"jsonrpc":"2.0", "method": "eth_blockNumber", "params": [], "id": 1}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={'Content-Type': 'application/json'},
                    json=json_data, timeout=timeout
                ) as response:
                    if response.status == 200:
                        res_data = await response.read()
                        res_data = res_data.decode('utf-8')
                        await session.close()
                        decoded_data = json.loads(res_data)
                        if decoded_data and 'result' in decoded_data:
                            return int(decoded_data['result'], 16)
        except asyncio.TimeoutError:
            print('timeout: {} get_block_number {}s'.format(url, timeout))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
        return None

    async def call_fetch_asset_transfer(
        self, chain: str, from_block: int, to_block: int,
        order: str="asc", max_count: int=1000, time_sleep: int=1, pageKey: str=None, timeout: int=32
    ):
        retry = 5
        retrying = 0
        max_count = hex(max_count)
        json_data = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [
                {
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                    "category": [
                            "erc20",
                            "erc721",
                            "erc1155",
                            "specialnft"
                    ],
                    "withMetadata": True,
                    "excludeZeroValue": False,
                    "maxCount": max_count,
                    "order": order.lower()
                }
            ]
        }
        if pageKey:
            json_data = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "alchemy_getAssetTransfers",
                "params": [
                    {
                        "fromBlock": hex(from_block),
                        "toBlock": hex(to_block),
                        "category": [
                                "erc20",
                                "erc721",
                                "erc1155",
                                "specialnft"
                        ],
                        "withMetadata": True,
                        "excludeZeroValue": False,
                        "maxCount": max_count,
                        "order": order.lower(),
                        "pageKey": pageKey
                    }
                ]
            }
        try:
            url = self.bot.config['alchemy_endpoint'][chain.lower()]
            print_color("{} Fetching chain: {}, from: {} to {}, maxCount {}, pageKey {} ...".format(
                f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), from_block, to_block, int(max_count, 16), pageKey), color="yellow"
            )
            while retrying < retry:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=json_data,
                        headers={'Content-Type': 'application/json', 'accept': 'application/json'}, 
                        timeout=timeout
                    ) as response:
                        if response.status == 200:
                            res_data = await response.read()
                            res_data = res_data.decode('utf-8')
                            await session.close()
                            decoded_data = json.loads(res_data)
                            if decoded_data and "result" in decoded_data:
                                await asyncio.sleep(1.0)
                                return decoded_data
                        else:
                            retrying += 1
                            print_color("{} Fetching chain: {}, from: {} to {} got status: {}. Retrying {} in {}".format(
                                f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), from_block, to_block, response.status, retrying, time_sleep), color="red"
                            )
                            await asyncio.sleep(5.0)
        except asyncio.TimeoutError:
            print_color(
                '{} timeout: call_fetch_asset_transfer chain {}, from {} to {}'.format(f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain, from_block, to_block),
                color="red"
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
        return None

    async def get_nft_collections(
        self, chain: str, contract: str, start_token: hex=None,
        time_sleep: int=1, timeout: int=32
    ):
        try:
            url = self.bot.config['alchemy_endpoint'][chain.lower()] + "/getNFTsForCollection?contractAddress="+contract+"&withMetadata=true"
            if start_token:
                url += "&startToken="+str(start_token)

            retry = 5
            retrying = 0
            print_color("{} Fetching NFT collection chain: {}, contract: {} startToken {}".format(
                f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), contract, start_token), color="cyan"
            )
            while retrying < retry:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers={'Content-Type': 'application/json', 'accept': 'application/json'}, 
                        timeout=timeout
                    ) as response:
                        if response.status == 200:
                            res_data = await response.read()
                            res_data = res_data.decode('utf-8')
                            await session.close()
                            decoded_data = json.loads(res_data)
                            if decoded_data and "nfts" in decoded_data:
                                await asyncio.sleep(time_sleep)
                                return decoded_data
                        else:
                            retrying += 1
                            print_color("{} Fetching NFT collection chain: {}, contract: {} startToken {} got status {}. Retrying {} in {}".format(
                                f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), contract, start_token, response.status, retrying, time_sleep), color="red"
                            )
                            await asyncio.sleep(10.0)
        except asyncio.TimeoutError:
            print_color(
                '{} timeout: Fetching NFT collection chain: {}, contract: {} startToken {}'.format(
                    f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain, contract, start_token), color="red"
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
        return None

    @tasks.loop(seconds=10.0)
    async def fetch_nft_tokens(self):
        if self.bot.config['maintenance']['disable_all_tasks'] == 1:
            print_color("{} maintenance is on.. sleep...".format(
                f"{datetime.now():%Y-%m-%d %H:%M:%S}"), color="red")
            await asyncio.sleep(10.0)
            return
        get_active = await self.utils.get_active_nft_conts(limit=20)
        if len(get_active) > 0:
            for each in get_active:
                if each['enable_fetching'] != 1:
                    continue

                if each['network'] == "ETHEREUM":
                    chain = "eth"
                elif each['network'] == "POLYGON":
                    chain = "polygon"
                try:
                    # check if there is last token ID in records else from empty
                    get_existing_tokens = []
                    nft_counts = 0
                    if each['supplying'] > 0:
                        nft_counts = await self.utils.get_count_nft_cont_tokens(each['nft_cont_tracking_id'])
                        # get last 200
                        limit = 200
                        if limit > each['supplying']:
                            limit = each['supplying']
                        get_existing_tokens = await self.utils.get_active_nft_cont_tokens(each['nft_cont_tracking_id'], limit)
                    collections = []
                    next_token = None
                    next_token_hex = None
                    if nft_counts > 0:
                        if each['max_items'] > 0 and nft_counts >= each['max_items']:
                            print_color("{} Skip NFT tokens chain: {}, contract: {}, having supplying = max!".format(
                               f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), each['contract']), color="green"
                            )
                            await self.utils.update_contract_fetched_time(each['nft_cont_tracking_id'])
                            continue
                        # has data, we need to exclude them if in result
                        next_token = int(get_existing_tokens[-1]['token_id_hex'], 16)
                        next_token_hex = get_existing_tokens[-1]['token_id_hex']
                        if each['last_token_id_hex']:
                            next_token_hex = each['last_token_id_hex']

                    
                    # Let's collect
                    nft_collections = await self.get_nft_collections(
                        chain, each['contract'], next_token_hex, 1, 32
                    )
                    if nft_collections and "nfts" in nft_collections and nft_collections['nfts'] and len(nft_collections['nfts']) > 0:
                        collections += nft_collections['nfts']
                    previous_token = None
                    previous_token_hex = None
                    last_token_id_hex = None
                    while True:
                        if next_token_hex is not None and next_token_hex == previous_token_hex:
                            print_color("{} NFT tokens chain: {}, contract: {}, same next and previous {}".format(
                                f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), each['contract'], next_token), color="lightgray"
                            )
                            break
                        print_color("{} NFT tokens chain: {}, contract: {}, collected {} item(s)".format(
                            f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), each['contract'], len(collections)), color="lightgray"
                        )
                        if "nextToken" in nft_collections:
                            previous_token = next_token
                            previous_token_hex = next_token_hex
                            next_token = copy.copy(int(nft_collections['nextToken'], 16))
                            next_token_hex = copy.copy(nft_collections['nextToken'])
                            last_token_id_hex = copy.copy(nft_collections['nextToken'])
                            nft_collections = await self.get_nft_collections(
                                chain, each['contract'], next_token_hex, 1, 32
                            )
                            if nft_collections and "nfts" in nft_collections and nft_collections['nfts'] and len(nft_collections['nfts']) > 0:
                                collections += nft_collections['nfts']
                            if "nextToken" not in nft_collections:
                                break
                        else:
                            break
                        # We should stop records at 10k or data is huge...
                        # We just need to check db and start from last hex
                        if len(collections) >= self.bot.config['api']['max_collection_to_save']:
                            break
                    # Got result...
                    data_rows = []
                    list_existings = [i['token_id_hex'] for i in get_existing_tokens]
                    checking_ids = []
                    for item in collections:
                        if item['id']['tokenId'] in checking_ids:
                            continue
                        else:
                            checking_ids.append(item['id']['tokenId'])
                        token_id_int = int(item['id']['tokenId'], 16) if item['id']['tokenId'] and int(item['id']['tokenId'], 16) < 10**20-1 else None
                        token_id_hex = hex(int(item['id']['tokenId'], 16)) # make it shorter
                        if str(token_id_hex) in list_existings:
                            # skip
                            continue
                        timestamp = None
                        if item['timeLastUpdated']:
                            timestamp=datetime.strptime(
                                item['timeLastUpdated'].split(".")[0]+"Z", '%Y-%m-%dT%H:%M:%SZ'
                            ).replace(tzinfo=timezone.utc).timestamp()
                        token_type = item['id']['tokenMetadata']['tokenType'] if item['id']['tokenMetadata']['tokenType'] else None
                        metadata = json.dumps(item['metadata']) if item['metadata'] else None
                        contract_data = json.dumps(item['contractMetadata']) if "contractMetadata" in item else None
                        media = json.dumps(item['media']) if item['media'] else None
                        token_uri = json.dumps(item['tokenUri']) if item['tokenUri'] else None
                        data_rows.append((
                            each['nft_cont_tracking_id'], each['network'], token_id_int, token_id_hex,
                            token_type, item['title'], token_uri,
                            media, metadata, item['timeLastUpdated'], timestamp, 
                            contract_data
                        ))
                    if len(data_rows) > 0:
                        inserting = await self.utils.insert_nft_tokens(data_rows, last_token_id_hex, each['nft_cont_tracking_id'])
                        print_color("{} Inserting NFT tokens chain: {}, contract: {}, {} item(s)".format(
                            f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), each['contract'], inserting), color="green"
                        )
                    else:
                        # we only update fetched time
                        await self.utils.update_contract_fetched_time(each['nft_cont_tracking_id'])
                        print_color("{} Inserting NFT tokens chain: {}, contract: {}, 0 item(s)".format(
                            f"{datetime.now():%Y-%m-%d %H:%M:%S}", chain.lower(), each['contract']), color="red"
                        )
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)

    @tasks.loop(seconds=10.0)
    async def fetch_image_in_nft(self):
        if self.bot.config['maintenance']['disable_all_tasks'] == 1:
            print_color("{} maintenance is on.. sleep...".format(
                f"{datetime.now():%Y-%m-%d %H:%M:%S}"), color="red")
            await asyncio.sleep(10.0)
            return
        # create function for multiple thread
        # should return value of `nft_token_id` if saved.
        async def fetch_image_ipfs(image_dict, id: int, total_numbers, selected_gw):
            try:
                file_saved = False
                if image_dict['image'].startswith("data:image/svg+xml;utf8,"):
                    data = image_dict['image'].replace("data:image/svg+xml;utf8,", "")
                    extension = "svg"
                    hash_object = hashlib.sha256(data.encode())
                    hex_dig = str(hash_object.hexdigest())
                    mime_type = "svg+xml"
                    saving_file = Path(self.bot.config['ipfs_gateway']['local_path'] + hex_dig + "." + extension)
                    if saving_file.is_file():
                        # file exists
                        file_saved = True
                        return (mime_type, hex_dig + "." + extension, image_dict['nft_token_id'])
                    else:
                        with open(
                            self.bot.config['ipfs_gateway']['local_path'] + hex_dig + "." + extension, "w"
                        ) as file:
                            file.write(data)
                            file.close()
                            file_saved = True
                        return (mime_type, hex_dig + "." + extension, image_dict['nft_token_id'])
                elif image_dict['image'].startswith(("http://", "https://")):
                    url = image_dict['image']
                elif image_dict['image'].startswith("ipfs://"):
                    if self.bot.config['ipfs_gateway']['use_local_node'] == 1:
                        url = self.bot.config['ipfs_gateway']['local_node'] + image_dict['image'].replace("ipfs://", "")
                    else:
                        url =  selected_gw + image_dict['image'].replace("ipfs://", "")
                else:
                    print_color("Fetching invalid image link {}...".format(image_dict['image'][0:50]), color="red")
                    return False

                try:
                    #print_color("{}/{}) Fetching image: {}=>{}".format(
                    #  id, total_numbers, image_dict['image'], url), color="yellow"
                    #)
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url,
                            timeout=32
                        ) as response:
                            if response.status == 200:
                                data = await response.read()
                                buffer = io.BytesIO(data)
                                mime = magic.Magic(mime=True)
                                mime_type = mime.from_buffer(buffer.read(2048))
                                # Example: > image/png
                                extension = mime_type.split("/")[-1]
                                hash_object = hashlib.sha256(data)
                                hex_dig = str(hash_object.hexdigest())
                                if extension == "svg+xml":
                                    extension = "svg"
                                saving_file = Path(self.bot.config['ipfs_gateway']['local_path'] + hex_dig + "." + extension)
                                if saving_file.is_file():
                                    # file exists
                                    # just update data
                                    file_saved = True
                                    return (mime_type, hex_dig + "." + extension, image_dict['nft_token_id'])
                                else:
                                    if extension in ['png', 'jpeg', 'svg', 'mp4', 'gif']:
                                        with open(
                                            self.bot.config['ipfs_gateway']['local_path'] + hex_dig + "." + extension, "wb"
                                        ) as file:
                                            file.write(data)
                                            file.close()
                                            file_saved = True
                                    else:
                                        print_color("{}) Fetched extension {} is not supported yet for {} from {}".format(
                                            id, extension, image_dict['image'], url), color="red"
                                        )
                                if file_saved is True:
                                    return (mime_type, hex_dig + "." + extension, image_dict['nft_token_id'])
                            else:
                                await asyncio.sleep(0.5)
                                #if self.bot.config['ipfs_gateway']['use_local_node'] != 1 and selected_gw in gateway_list:
                                #        gateway_list.remove(selected_gw)
                                print_color("{}) Fetching image url: {} got response: {}".format(id, url, response.status), color="yellow")
                except aiohttp.client_exceptions.InvalidURL:
                    print_color("{}) Fetching invalid image url: {}".format(id, url), color="yellow")
                except asyncio.exceptions.TimeoutError:
                    # print_color("{}) Fetching image timeout for url: {}".format(id, url), color="yellow")
                    #if self.bot.config['ipfs_gateway']['use_local_node'] != 1 and selected_gw in gateway_list:
                    #    gateway_list.remove(selected_gw)
                    pass
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)                                    
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
                print_color("{}) Fetched image failed with: {}=> {}".format(
                    id, image_dict['image'], url), color="red"
                )
            return False

        try:
            # Limit process
            get_list_no_images = await self.utils.get_nft_token_list_no_image(from_number=200, limit=self.bot.config['ipfs_gateway']['num_proc_image_fetch'])
            if len(get_list_no_images) > 0:
                gateway_list = copy.copy(self.bot.config['ipfs_gateway']['public'])
                tasks = []
                i = 1
                in_image = []
                for each in get_list_no_images:
                    if each['image'] in in_image:
                        continue
                    else:
                        if self.bot.config['ipfs_gateway']['use_local_node'] == 1:
                            selected_gw = self.bot.config['ipfs_gateway']['local_node']
                        else:
                            if len(gateway_list) <= 2:
                                gateway_list = copy.copy(self.bot.config['ipfs_gateway']['public'])
                            try:
                                selected_gw = random.choice(gateway_list)
                            except IndexError:
                                gateway_list = copy.copy(self.bot.config['ipfs_gateway']['public'])
                                selected_gw = random.choice(gateway_list)
                        in_image.append(each['image'])
                        tasks.append(fetch_image_ipfs(each, i, len(get_list_no_images), selected_gw))
                        i += 1                        
                inserting = 0
                list_update_nft_tracking_meta_image = []
                for task in asyncio.as_completed(tasks):
                    got_img = await task
                    if type(got_img) is tuple:
                        list_update_nft_tracking_meta_image.append(got_img)
                    else:
                        continue
                if len(list_update_nft_tracking_meta_image) > 0:
                    inserting = await self.utils.update_nft_tracking_meta_image(list_update_nft_tracking_meta_image)
                print_color("Fetched image completed: {}->{} / {}".format(
                    len(list_update_nft_tracking_meta_image), inserting, len(get_list_no_images)), color="green"
                )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.fetch_nft_tokens.is_running():
            self.fetch_nft_tokens.start()
        if not self.fetch_image_in_nft.is_running():
            self.fetch_image_in_nft.start()

    async def cog_load(self) -> None:
        if not self.fetch_nft_tokens.is_running():
            self.fetch_nft_tokens.start()
        if not self.fetch_image_in_nft.is_running():
            self.fetch_image_in_nft.start()

    async def cog_unload(self) -> None:
        self.fetch_nft_tokens.cancel()
        self.fetch_image_in_nft.cancel()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlchemyAPI(bot))
