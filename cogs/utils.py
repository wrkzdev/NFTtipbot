from discord.ext import commands, tasks
import discord
from discord.enums import ButtonStyle

import aiomysql
from aiomysql.cursors import DictCursor
from typing import Dict, Callable, List, Optional
import traceback, sys
import aiohttp, asyncio
import json
import time
from decimal import Decimal
import math

from eth_utils import is_hex_address # Check hex only
from web3 import Web3
from web3.middleware import geth_poa_middleware

# https://stackoverflow.com/questions/287871/how-do-i-print-colored-text-to-the-terminal

def print_color(prt, color: str):
    if color == "red":
        print(f"\033[91m{prt}\033[00m")
    elif color == "green":
        print(f"\033[92m{prt}\033[00m")
    elif color == "yellow":
        print(f"\033[93m{prt}\033[00m")
    elif color == "lightpurple":
        print(f"\033[94m{prt}\033[00m")
    elif color == "purple":
        print(f"\033[95m{prt}\033[00m")
    elif color == "cyan":
        print(f"\033[96m{prt}\033[00m")
    elif color == "lightgray":
        print(f"\033[97m{prt}\033[00m")
    elif color == "black":
        print(f"\033[98m{prt}\033[00m")
    else:
        print(f"\033[0m{prt}\033[00m")

def truncate(number, digits) -> float:
    stepper = Decimal(pow(10.0, digits))
    return math.trunc(stepper * Decimal(number)) / stepper

def check_address(address: str):
    if is_hex_address(address):
        return address
    return False

async def transfer_main_token(url: str, from_address: str, private_key, to_address: str, atomic_amount: int, chain_id: int):
    try:
        # HTTPProvider:
        w3 = Web3(Web3.HTTPProvider(url))

        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        nonce = w3.eth.getTransactionCount(w3.toChecksumAddress(from_address))
        gasPrice = w3.eth.gasPrice
        estimateGas = w3.eth.estimateGas(
            {
                'to': w3.toChecksumAddress(to_address),
                'from': w3.toChecksumAddress(from_address),
                'value':  atomic_amount
            }
        )
        transaction = {
                'from': w3.toChecksumAddress(from_address),
                'to': w3.toChecksumAddress(to_address),
                'value': atomic_amount,
                'nonce': nonce,
                'gasPrice': gasPrice,
                'gas': estimateGas,
                'chainId': chain_id
        }
        signed = w3.eth.account.sign_transaction(transaction, private_key=private_key)
        sent_tx = w3.eth.sendRawTransaction(signed.rawTransaction)
        if signed and sent_tx:
            return sent_tx.hex()
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None


async def transfer_nft(
        url: str, contract_type: str, contract: str, abi, from_address: str,
        to_address: str, private_key, item_id, chain_id: int, amount: int=1
):
    try:
        # HTTPProvider:
        w3 = Web3(Web3.HTTPProvider(url))

        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        unicorns = w3.eth.contract(address=w3.toChecksumAddress(contract), abi=abi)
        nonce = w3.eth.getTransactionCount(w3.toChecksumAddress(from_address))

        if contract_type == "ERC721":
            estimateGas = unicorns.functions.transferFrom(w3.toChecksumAddress(from_address), w3.toChecksumAddress(to_address), item_id).estimateGas({'from': w3.toChecksumAddress(from_address)})
            unicorn_txn = unicorns.functions.transferFrom(w3.toChecksumAddress(from_address), w3.toChecksumAddress(to_address), item_id).buildTransaction(
                {
                    'from': w3.toChecksumAddress(from_address),
                    'gasPrice': w3.eth.gasPrice,
                    'gas': estimateGas,
                    'nonce': nonce,
                    'chainId': chain_id
                }
            )
        elif contract_type == "ERC1155":
            estimateGas = unicorns.functions.safeTransferFrom(w3.toChecksumAddress(from_address), w3.toChecksumAddress(to_address), item_id, amount, "").estimateGas({'from': w3.toChecksumAddress(from_address)})
            unicorn_txn = unicorns.functions.safeTransferFrom(w3.toChecksumAddress(from_address), w3.toChecksumAddress(to_address), item_id, amount, "").buildTransaction(
                {
                    'from': w3.toChecksumAddress(from_address),
                    'gasPrice': w3.eth.gasPrice,
                    'gas': estimateGas,
                    'nonce': nonce,
                    'chainId': chain_id
                }
            )
        signed_txn = w3.eth.account.sign_transaction(unicorn_txn, private_key=private_key)
        sent_tx = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
        if sent_tx is not None:
            return sent_tx.hex() # hex
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None

async def eth_get_tx_info(
        url: str, tx: str, timeout: int = 64
):
    data = '{"jsonrpc":"2.0", "method": "eth_getTransactionReceipt", "params":["' + tx + '"], "id":1}'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers={'Content-Type': 'application/json'}, json=json.loads(data),
                                    timeout=timeout) as response:
                if response.status == 200:
                    res_data = await response.read()
                    res_data = res_data.decode('utf-8')
                    await session.close()
                    decoded_data = json.loads(res_data)
                    if decoded_data and 'result' in decoded_data:
                        return decoded_data['result']
    except asyncio.TimeoutError:
        print('TIMEOUT: {} get block number {}s'.format(url, timeout))
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None

async def eth_wallet_getbalance(
        url: str, address: str, contract: str=None, is_gas: bool=False
) -> int:
    timeout = 16
    if is_gas is True:
        data = '{"jsonrpc":"2.0","method":"eth_getBalance","params":["'+address+'", "latest"],"id":1}'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers={'Content-Type': 'application/json'}, json=json.loads(data), timeout=timeout) as response:
                    if response.status == 200:
                        res_data = await response.read()
                        res_data = res_data.decode('utf-8')
                        await session.close()
                        decoded_data = json.loads(res_data)
                        if decoded_data and 'result' in decoded_data:
                            return int(decoded_data['result'], 16)
        except asyncio.TimeoutError:
            print('TIMEOUT: get balance {} timeout {}s'.format(address, timeout))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
    else:
        data = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [
                {"to": "'+contract+'", "data": "0x70a08231000000000000000000000000'+address[2:]+'"}, "latest"
            ],
            "id": 1}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        url, headers={'Content-Type': 'application/json'}, json=data, timeout=timeout
                ) as response:
                    if response.status == 200:
                        res_data = await response.read()
                        res_data = res_data.decode('utf-8')
                        await session.close()
                        decoded_data = json.loads(res_data)
                        if decoded_data and 'result' in decoded_data:
                            if decoded_data['result'] == "0x":
                                balance = 0
                            else:
                                balance = int(decoded_data['result'], 16)
                            return balance
        except asyncio.TimeoutError:
            print('TIMEOUT: get balance {} timeout {}s'.format(address, timeout))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
    return None


# Paginator & Close Button
# Defines a simple view of row buttons.
class CloseAnyMessage(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❎ Close", style=ButtonStyle.green, custom_id="close_any_message")
    async def row_close_message(
            self, interaction: discord.MessageInteraction, button: discord.ui.Button
    ):
        pass


class MenuPage(discord.ui.View):
    def __init__(self, inter, embeds: List[discord.Embed], timeout: float = 60, disable_remove: bool=False):
        super().__init__(timeout=timeout)
        self.inter = inter

        # Sets the embed list variable.
        self.embeds = embeds

        # Current embed number.
        self.embed_count = 0

        # Disables previous page button by default.
        self.prev_page.disabled = True

        self.first_page.disabled = True

        if disable_remove is True:
            self.remove.disabled = True

        if len(self.embeds) == 1:
            self.next_page.disabled = True

        if len(self.embeds) < 3:
            self.last_page.disabled = True

        # Sets the footer of the embeds with their respective page numbers.
        for i, embed in enumerate(self.embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(self.embeds)}")

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        # await self.inter.edit_original_response(view=CloseAnyMessage())
        await self.inter.edit_original_response(view=None)

    @discord.ui.button(label="⏪", style=discord.ButtonStyle.red)
    async def first_page(self, interaction: discord.MessageInteraction, button: discord.ui.Button):
        if interaction.user != self.inter.user:
            return
        # Decrements the embed count.
        self.embed_count = 0

        # Gets the embed object.
        embed = self.embeds[self.embed_count]

        self.last_page.disabled = False

        # Enables the next page button and disables the previous page button if we're on the first embed.
        self.next_page.disabled = False
        if self.embed_count == 0:
            self.prev_page.disabled = True
            self.first_page.disabled = True

        await self.inter.edit_original_response(embed=embed, view=self)
        await interaction.response.send_message("‎")
        await interaction.delete_original_response()

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.red)
    async def prev_page(self, interaction: discord.MessageInteraction, button: discord.ui.Button):
        if interaction.user != self.inter.user:
            return
        # Decrements the embed count.
        self.embed_count -= 1

        # Gets the embed object.
        embed = self.embeds[self.embed_count]

        self.last_page.disabled = False

        # Enables the next page button and disables the previous page button if we're on the first embed.
        self.next_page.disabled = False
        if self.embed_count == 0:
            self.prev_page.disabled = True
            self.first_page.disabled = True

        await self.inter.edit_original_response(embed=embed, view=self)
        await interaction.response.send_message("‎")
        await interaction.delete_original_response()

    # @discord.ui.button(label="⏹️", style=discord.ButtonStyle.red)
    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.red)
    async def remove(self, interaction: discord.MessageInteraction, button: discord.ui.Button):
        if interaction.user != self.inter.user:
            return
        await interaction.response.send_message("‎")
        await interaction.delete_original_response()
        try:
            await self.inter.delete_original_response()
        except Exception as e:
            pass

    # @discord.ui.button(label="", emoji="▶️", style=discord.ButtonStyle.green)
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.green)
    async def next_page(self, interaction: discord.MessageInteraction, button: discord.ui.Button):
        if interaction.user != self.inter.user:
            return

        # Increments the embed count.
        self.embed_count += 1

        # Gets the embed object.
        embed = self.embeds[self.embed_count]

        # Enables the previous page button and disables the next page button if we're on the last embed.
        self.prev_page.disabled = False

        self.first_page.disabled = False

        if self.embed_count == len(self.embeds) - 1:
            self.next_page.disabled = True
            self.last_page.disabled = True

        await self.inter.edit_original_response(embed=embed, view=self)
        await interaction.response.send_message("‎")
        await interaction.delete_original_response()

    @discord.ui.button(label="⏩", style=discord.ButtonStyle.green)
    async def last_page(self, interaction: discord.MessageInteraction, button: discord.ui.Button):
        if interaction.user != self.inter.user:
            return

        # Increments the embed count.
        self.embed_count = len(self.embeds) - 1

        # Gets the embed object.
        embed = self.embeds[self.embed_count]

        self.first_page.disabled = False

        # Enables the previous page button and disables the next page button if we're on the last embed.
        self.prev_page.disabled = False
        if self.embed_count == len(self.embeds) - 1:
            self.next_page.disabled = True
            self.last_page.disabled = True
        await self.inter.edit_original_response(embed=embed, view=self)
        await interaction.response.send_message("‎")
        await interaction.delete_original_response()


# Cog class
class Utils(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self.pool = None

    async def log_to_channel(self, channel_id: int, content: str) -> None:
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(content)
                except Exception as e:
                    channel = self.bot.get_channel(self.bot.config['discord']['log_channel_backup']) # Use channel backup
                    if channel:
                        await channel.send(content)
            else:
                print(f"Bot can't find channel {str(channel_id)} for logging. Check for the backup channel.")
                channel = self.bot.get_channel(self.bot.config['discord']['log_channel_backup']) # Use channel backup
                if channel:
                    await channel.send(content)
                else:
                    print(f"Bot can't find channel {str(channel_id)} for logging and no backup channel!")
        except Exception as e:
            traceback.print_exc(file=sys.stdout)

    @tasks.loop(seconds=60.0)
    async def pull_eth_gas_price(self):
        url = 'https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey=' + self.bot.config['etherscan']['api_key']
        try:
            # print(f"pulling gas data {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        url,
                        headers={'Content-Type': 'application/json'},
                        timeout=self.bot.config['etherscan']['gas_fetch_timeout']
                ) as response:
                    if response.status == 200:
                        res_data = await response.read()
                        res_data = res_data.decode('utf-8')
                        await session.close()
                        decoded_data = json.loads(res_data)
                        if decoded_data and 'result' in decoded_data and decoded_data['result']:
                            # OK, we have result
                            gas_data = decoded_data['result']
                            if gas_data and int(gas_data['SafeGasPrice']) and int(gas_data['ProposeGasPrice']) and\
                                    int(gas_data['FastGasPrice']):
                                gas_data['last_update'] = int(time.time())
                                await self.update_eth_gas_tracker(json.dumps(gas_data))
        except asyncio.TimeoutError:
            print('TIMEOUT: pull_gas_price for {}s'.format(self.bot.config['etherscan']['gas_fetch_timeout']))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)

    @tasks.loop(seconds=60.0)
    async def pull_matic_gas_price(self):
        url = 'https://gasstation-mainnet.matic.network/'
        try:
            timeout=12
            # print(f"pulling gas data {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        url,
                        headers={'Content-Type': 'application/json'},
                        timeout=timeout
                ) as response:
                    if response.status == 200:
                        res_data = await response.read()
                        res_data = res_data.decode('utf-8')
                        await session.close()
                        gas_data = json.loads(res_data)
                        if gas_data:
                            # OK, we have result
                            gas_data['last_update'] = int(time.time())
                            await self.update_matic_gas_tracker(json.dumps(gas_data))
        except asyncio.TimeoutError:
            print('TIMEOUT: pull_matic_gas_price for {}s'.format(timeout))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)

    async def openConnection(self):
        try:
            if self.pool is None:
                self.pool = await aiomysql.create_pool(
                    host=self.bot.config['mysql']['host'], port=3306, minsize=2, maxsize=4,
                    user=self.bot.config['mysql']['user'], password=self.bot.config['mysql']['password'],
                    db=self.bot.config['mysql']['db'], cursorclass=DictCursor, autocommit=True
                )
        except Exception:
            traceback.print_exc(file=sys.stdout)

    async def get_pending_withdraw_tx_list_all(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `nft_withdraw` 
                    WHERE `withdrew_status`=%s
                    """
                    await cur.execute(sql, "PENDING")
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_pending_withdraw_tx_list(self, network: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `nft_withdraw` 
                    WHERE `withdrew_status`=%s AND `network`=%s
                    """
                    await cur.execute(sql, ("PENDING", network))
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_pending_withdraw_tx_list_by_id_user(
            self, user_id: str, user_server: str, network: str
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `nft_withdraw` 
                    WHERE `withdrew_status`=%s AND `user_id`=%s AND `user_server`=%s
                    AND `network`=%s
                    """
                    await cur.execute(sql, ("PENDING", user_id, user_server, network))
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def update_withdraw_pending_tx(
            self, withdraw_id: int, txn: str, status: str,
            effective_gas: int, gas_used: int, real_tx_fee: float,
            eth_gas: float, matic_gas: float,
            user_id: str, user_server: str,
            eth_nft_tx: int, matic_nft_tx: int
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ UPDATE `nft_withdraw`, `tbl_users`
                      SET `nft_withdraw`.`withdrew_status`=%s, `nft_withdraw`.`withdrew_gas_price`=%s, 
                      `nft_withdraw`.`withdrew_gas_used`=%s, `nft_withdraw`.`withdrew_tx_real_fee`=%s,
                      `tbl_users`.`eth_gas`=`tbl_users`.`eth_gas`-%s, 
                      `tbl_users`.`matic_gas`=`tbl_users`.`matic_gas`-%s, 
                      `tbl_users`.`eth_nft_withdrew`=`tbl_users`.`eth_nft_withdrew`+%s,
                      `tbl_users`.`matic_nft_withdrew`=`tbl_users`.`matic_nft_withdrew`+%s
                    WHERE `nft_withdraw`.`withdrew_tx`=%s AND `nft_withdraw`.`withdraw_id`=%s
                      AND `tbl_users`.`user_id`=%s AND `tbl_users`.`user_server`=%s
                    """
                    await cur.execute(sql, (
                        status, effective_gas, gas_used, real_tx_fee, 
                        eth_gas, matic_gas, 
                        eth_nft_tx, matic_nft_tx,
                        txn, withdraw_id, user_id, user_server
                    ))
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def get_bot_setting(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `bot_settings` 
                    """
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        res = {}
                        for each in result:
                            res[each['name']] = each['value']
                        self.bot.setting = res
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def update_eth_gas_tracker(self, gas_result):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ UPDATE `bot_settings`
                    SET `value`=%s WHERE `name`=%s
                    LIMIT 1
                    """
                    await cur.execute(sql, (gas_result, "eth_gas_tracker"))
                    await conn.commit()
                    await self.get_bot_setting()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def update_matic_gas_tracker(self, gas_result):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ UPDATE `bot_settings`
                    SET `value`=%s WHERE `name`=%s
                    LIMIT 1
                    """
                    await cur.execute(sql, (gas_result, "matic_gas_tracker"))
                    await conn.commit()
                    await self.get_bot_setting()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def get_list_contract_assets(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `nft_item_list`
                    """
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_list_contract_collection_search(
            self, like: str, limit: int = 20
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT * FROM `nft_info_contract` 
                    WHERE `is_enable`=%s AND `collection_name` LIKE %s LIMIT """+str(limit)
                    await cur.execute(sql, (1, "%" + like + "%"))
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_contract_asset_by_token_id(
            self, contract: str, token_id_hex: str, network: str
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `nft_item_list`
                    WHERE `contract`=%s AND `asset_id_hex`=%s AND `network`=%s
                    LIMIT 1
                    """
                    await cur.execute(sql, (contract, token_id_hex, network))
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def get_list_contracts(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `nft_info_contract` 
                    WHERE `is_enable`=%s
                    """
                    await cur.execute(sql, 1)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_contract_by_id(self, contract_id: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT * FROM `nft_info_contract` 
                    WHERE `contract_id`=%s AND `is_enable`=%s 
                    LIMIT 1
                    """
                    await cur.execute(sql, (contract_id, 1))
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def get_list_user_assets(
            self, user_id: str, user_server: str
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    result = []
                    sql = """ 
                        SELECT `nft_credit`.`nft_id`, `nft_credit`.`token_id_int`, `nft_credit`.`token_id_hex`, 
                        `nft_credit`.`credited_user_id`, `nft_credit`.`credited_user_server`, 
                        `nft_info_contract`.*, `nft_item_list`.*
                        FROM ((`nft_credit`
                        INNER JOIN `nft_info_contract` ON `nft_credit`.`token_address` = `nft_info_contract`.`contract`)
                        INNER JOIN `nft_item_list` ON `nft_credit`.`token_id_hex` = `nft_item_list`.`asset_id_hex` 
                            AND  `nft_credit`.`token_address` = `nft_item_list`.`contract`)
                        WHERE `nft_credit`.`credited_user_id`=%s AND `nft_credit`.`credited_user_server`=%s
                        AND `nft_credit`.`is_frozen`=%s AND `nft_credit`.`amount`>0 
                            AND `nft_info_contract`.`is_enable`=1
                    """
                    await cur.execute(sql, (user_id, user_server, 0))
                    result_721 = await cur.fetchall()
                    if result_721:
                        result += result_721
                    sql = """ 
                        SELECT `nft_credit`.`nft_id`, `nft_credit`.`token_id_int`, `nft_credit`.`token_id_hex`, 
                            `nft_credit`.`credited_user_id`, `nft_credit`.`credited_user_server`, 
                            `nft_info_contract`.*, `nft_erc1155_list`.*
                        FROM ((`nft_credit`
                        INNER JOIN `nft_info_contract` ON `nft_credit`.`token_address` = `nft_info_contract`.`contract`)
                        INNER JOIN `nft_erc1155_list` ON `nft_credit`.`token_id_hex` = `nft_erc1155_list`.`token_id_hex`
                            AND  `nft_credit`.`token_address` = `nft_erc1155_list`.`token_address`)
                        WHERE `nft_credit`.`credited_user_id`=%s AND `nft_credit`.`credited_user_server`=%s
                        AND `nft_credit`.`is_frozen`=%s AND `nft_credit`.`amount`>0 AND `nft_info_contract`.`is_enable`=1
                    """
                    await cur.execute(sql, (user_id, user_server, 0))
                    result_1155 = await cur.fetchall()
                    if result_1155:
                        result += result_1155
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return result

    async def get_list_user_assets_search(
            self, user_id: str, user_server: str, like: str, limit: int = 10
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    result = []
                    sql = """ 
                        SELECT `nft_credit`.`nft_id`, `nft_credit`.`token_id_int`, `nft_credit`.`token_id_hex`, 
                            `nft_credit`.`credited_user_id`, `nft_credit`.`credited_user_server`, 
                            `nft_info_contract`.*, `nft_item_list`.*
                        FROM ((`nft_credit`
                        INNER JOIN `nft_info_contract` ON `nft_credit`.`token_address` = `nft_info_contract`.`contract`)
                        INNER JOIN `nft_item_list` ON `nft_credit`.`token_id_hex` = `nft_item_list`.`asset_id_hex` 
                            AND  `nft_credit`.`token_address` = `nft_item_list`.`contract`)
                        WHERE `nft_credit`.`credited_user_id`=%s AND `nft_credit`.`credited_user_server`=%s
                        AND `nft_credit`.`is_frozen`=%s AND `nft_credit`.`amount`>0 
                            AND `nft_info_contract`.`is_enable`=1
                            AND `nft_item_list`.`name` LIKE %s LIMIT """+str(limit)
                    await cur.execute(sql, (user_id, user_server, 0, "%" + like + "%"))
                    result_721 = await cur.fetchall()
                    if result_721:
                        result += result_721
                    sql = """ 
                        SELECT `nft_credit`.`nft_id`, `nft_credit`.`token_id_int`, `nft_credit`.`token_id_hex`, 
                        `nft_credit`.`credited_user_id`, `nft_credit`.`credited_user_server`, 
                        `nft_info_contract`.*, `nft_erc1155_list`.*
                        FROM ((`nft_credit`
                        INNER JOIN `nft_info_contract` ON `nft_credit`.`token_address` = `nft_info_contract`.`contract`)
                        INNER JOIN `nft_erc1155_list` ON `nft_credit`.`token_id_hex` = `nft_erc1155_list`.`token_id_hex`
                            AND  `nft_credit`.`token_address` = `nft_erc1155_list`.`token_address`)
                        WHERE `nft_credit`.`credited_user_id`=%s AND `nft_credit`.`credited_user_server`=%s
                        AND `nft_credit`.`is_frozen`=%s AND `nft_credit`.`amount`>0 
                            AND `nft_info_contract`.`is_enable`=1
                        AND `nft_erc1155_list`.`name` LIKE %s LIMIT """+str(limit)
                    await cur.execute(sql, (user_id, user_server, 0, "%" + like + "%"))
                    result_1155 = await cur.fetchall()
                    if result_1155:
                        result += result_1155
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return result

    async def move_nft(
            self, network: str, contract: str, from_user_id: str, from_user_server: str,
            to_user_id: str, to_user_server: str, token_id_int: int, token_id_hex: str,
            contract_id: int, amount: int
    ):
        try:
            if from_user_id == to_user_id:
                return False
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    UPDATE `nft_credit` 
                        SET `amount`=`amount`-%s 
                    WHERE `network`=%s AND `token_address`=%s 
                        AND `credited_user_id`=%s AND `credited_user_server`=%s AND `token_id_hex`=%s;

                    INSERT INTO `nft_credit` (`network`, `token_address`, `token_id_int`, `token_id_hex`, 
                    `credited_user_id`, `credited_user_server`, `amount`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY
                    UPDATE
                        `amount`=VALUES(`amount`)+`amount`;
                    
                    INSERT INTO `nft_tip_logs` (`from_user_id`, `from_user_server`, `to_user_id`, 
                    `to_user_server`, `date`, `nft_info_contract_id`, `token_id_int`, `token_id_hex`, `amount`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);

                    INSERT INTO `tbl_users` (`inserted_date`, `user_id`, `user_server`, `total_tipped`)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY
                    UPDATE
                        `total_tipped`=VALUES(`total_tipped`)+`total_tipped`;

                    INSERT INTO `tbl_users` (`inserted_date`, `user_id`, `user_server`, `total_received`)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY
                    UPDATE
                        `total_received`=VALUES(`total_received`)+`total_received`;
                    """
                    await cur.execute(sql, (
                        amount, network, contract, from_user_id, from_user_server, token_id_hex,
                        network, contract, token_id_int, token_id_hex, to_user_id, to_user_server, amount,
                        from_user_id, from_user_server, to_user_id, to_user_server, int(time.time()), contract_id, token_id_int, token_id_hex, amount,
                        int(time.time()), from_user_id, from_user_server, amount,
                        int(time.time()), to_user_id, to_user_server, amount
                    ))
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def move_gas(
            self, from_user_id: str, from_user_server: str,
            to_user_id: str, to_user_server: str, amount: float, gas_ticker: str
    ):
        try:
            if from_user_id == to_user_id:
                return False
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    INSERT INTO `nft_tip_logs` (`from_user_id`, `from_user_server`, `to_user_id`, 
                    `to_user_server`, `date`, `gas_amount`, `gas_ticker`, `type`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);

                    UPDATE `tbl_users` SET `"""+gas_ticker+ """_gas`=`"""+gas_ticker+ """_gas`+%s 
                    WHERE `user_id`=%s AND `user_server`=%s; 

                    UPDATE `tbl_users` SET `"""+gas_ticker+ """_gas`=`"""+gas_ticker+ """_gas`-%s 
                    WHERE `user_id`=%s AND `user_server`=%s; 
                    """
                    await cur.execute(sql, (
                        from_user_id, from_user_server, to_user_id, to_user_server, int(time.time()),
                        amount, gas_ticker, "GAS",
                        amount, to_user_id, to_user_server,
                        amount, from_user_id, from_user_server
                    ))
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def transferred_nft(
            self, network: str, token_address: str, token_id_hex: str,
            user_id: str, txn: str, user_server: str, withdrew_to: str, amount: int
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    UPDATE `nft_credit`
                        SET `amount`=`amount`-%s 
                    WHERE `token_address`=%s AND `network`=%s AND `token_id_hex`=%s AND `credited_user_id`=%s
                        AND `credited_user_server`=%s;

                    INSERT INTO `nft_withdraw` (`network`, `token_address`, `token_id_hex`, 
                    `amount`, `user_id`, `user_server`, `withdrew_to`, `withdrew_tx`, `withdrew_status`, `withdrew_date`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """
                    await cur.execute(sql, (amount, token_address, network, token_id_hex, user_id, user_server,
                                            network, token_address, token_id_hex, amount, user_id, user_server, 
                                            withdrew_to, txn, "PENDING", int(time.time())))
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def verification_check(self, user_id: str, user_server: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT * FROM `metamask_v1` WHERE `discord_id`=%s AND `user_server`=%s AND `is_signed`=%s
                    """
                    await cur.execute(sql, (user_id, user_server, 1))
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def verification_find_sk(self, secret_key: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT * FROM `metamask_v1` WHERE `secret_key`=%s AND `verified_by_key`=%s AND `is_signed`=%s LIMIT 1
                    """
                    await cur.execute(sql, (secret_key, 1, 1))
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def insert_user_info(self, user_id: str, user_server: str, command_called: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    INSERT INTO `tbl_users` (`inserted_date`, `user_id`, `user_server`, `is_first_time`, `command_called`)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY 
                    UPDATE 
                    `command_called`=`command_called`+1,
                    `is_first_time`=0
                    """
                    await cur.execute(sql, (int(time.time()), user_id, user_server, 1, command_called))
                    await conn.commit()
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def get_user_info(self, user_id: str, user_server: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    SELECT * FROM `tbl_users` WHERE `user_id`=%s AND `user_server`=%s LIMIT 1
                    """
                    await cur.execute(sql, (user_id, user_server))
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def get_confirmed_gas_tx_to_notify(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT `metamask_v1`.*, `nft_main_wallet_tx`.*
                    FROM ((`metamask_v1`
                    INNER JOIN `nft_main_wallet_tx` ON `metamask_v1`.`address` = `nft_main_wallet_tx`.`from_address`)
                    INNER JOIN `tbl_users` ON `metamask_v1`.`discord_id` = `tbl_users`.`user_id`)
                    WHERE `tbl_users`.`is_frozen`=0 AND `metamask_v1`.`is_signed`=1 AND `nft_main_wallet_tx`.`is_credited`=0
                    """
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_confirmed_nft_tx_to_notify(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT `metamask_v1`.*, `nft_main_wallet_nft_tx`.*, `nft_item_list`.`name`, `nft_item_list`.`contract`, `nft_item_list`.`asset_id_hex`
                        FROM ((`metamask_v1`
                        INNER JOIN `nft_main_wallet_nft_tx` ON `metamask_v1`.`address` = `nft_main_wallet_nft_tx`.`from_address`)
                        INNER JOIN `tbl_users` ON `metamask_v1`.`discord_id` = `tbl_users`.`user_id`
                        INNER JOIN `nft_item_list` ON `nft_main_wallet_nft_tx`.`token_address` = `nft_item_list`.`contract` AND `nft_item_list`.`asset_id_hex`=`nft_main_wallet_nft_tx`.`token_id_hex`
                        )
                        WHERE `tbl_users`.`is_frozen`=0 AND `metamask_v1`.`is_signed`=1 AND `nft_main_wallet_nft_tx`.`inserted_credited`=0
                    """
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def verification_update(
            self, user_id: str, discord_name: str, user_server: str, secret_key: str
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    UPDATE `metamask_v1` SET `discord_id`=%s, `discord_name`=%s, `discord_verified_date`=%s, `user_server`=%s
                    WHERE `secret_key`=%s LIMIT 1
                    """
                    await cur.execute(sql, (user_id, discord_name, int(time.time()), user_server, secret_key))
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def get_wallet_tx(self, limit: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT * FROM `nft_main_wallet_tx` ORDER BY `block_number` DESC LIMIT """ + str(limit)
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_insert_wallet_txs(self, txs):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    INSERT INTO `nft_main_wallet_tx` (`network`, `hash`, `nonce`, `transaction_index`, `from_address`, 
                    `to_address`, `value`, `gas`, `gas_price`, `input`, `receipt_cumulative_gas_used`,
                    `receipt_gas_used`, `receipt_status`, `block_timestamp`, `block_time`, `block_number`,
                    `block_hash`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    await cur.executemany(sql, txs)
                    await conn.commit()
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def update_confirmed_gas_tx_notify(
            self, txn: str, user_id: str, user_server: str, eth_gas: float, matic_gas: float
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    UPDATE `nft_main_wallet_tx`, `tbl_users`
                      SET `nft_main_wallet_tx`.`is_credited`=%s, `nft_main_wallet_tx`.`credited_user_id`=%s,
                      `nft_main_wallet_tx`.`credited_user_server`=%s, `nft_main_wallet_tx`.`credited_time`=%s,
                      `tbl_users`.`eth_gas`=`eth_gas`+%s, `tbl_users`.`matic_gas`=`matic_gas`+%s
                    WHERE `nft_main_wallet_tx`.`hash`=%s AND `nft_main_wallet_tx`.`is_credited`=%s
                      AND `tbl_users`.`user_id`=%s AND `tbl_users`.`user_server`=%s
                    """
                    await cur.execute(sql, (
                        1, user_id, user_server, int(time.time()),
                        eth_gas, matic_gas,
                        txn, 0, user_id, user_server
                    ))
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def update_confirmed_nft_tx_notify(
            self, txn: str, user_id: str, user_server: str, token_id_hex: str,
            eth_nft_deposited: int, matic_nft_deposited: int
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    UPDATE `nft_main_wallet_nft_tx`, `tbl_users`
                      SET `nft_main_wallet_nft_tx`.`is_credited`=%s, `nft_main_wallet_nft_tx`.`credited_user_id`=%s,
                      `nft_main_wallet_nft_tx`.`credited_user_server`=%s, `nft_main_wallet_nft_tx`.`credited_time`=%s,
                      `nft_main_wallet_nft_tx`.`new_owner_user_id`=%s,
                      `nft_main_wallet_nft_tx`.`new_owner_server`=%s, `nft_main_wallet_nft_tx`.`new_owner_date`=%s,

                      `tbl_users`.`eth_nft_deposited`=`eth_nft_deposited`+%s, `tbl_users`.`matic_nft_deposited`=`matic_nft_deposited`+%s
                    WHERE `nft_main_wallet_nft_tx`.`transaction_hash`=%s AND `nft_main_wallet_nft_tx`.`is_credited`=%s AND `nft_main_wallet_nft_tx`.`token_id_hex`=%s
                      AND `tbl_users`.`user_id`=%s AND `tbl_users`.`user_server`=%s
                    """
                    await cur.execute(sql, (
                        1, user_id, user_server, int(time.time()),
                        user_id, user_server, int(time.time()),
                        eth_nft_deposited, matic_nft_deposited,
                        txn, 0, token_id_hex, user_id, user_server
                    ))
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def get_wallet_nft_tx(self, limit: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT * FROM `nft_main_wallet_nft_tx` ORDER BY `block_number` DESC LIMIT """ + str(limit)
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_insert_wallet_nft_txs(self, txs):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    INSERT INTO `nft_main_wallet_nft_tx` (`network`, `block_number`, `block_timestamp`, `block_time`, `block_hash`, 
                    `transaction_hash`, `transaction_index`, `log_index`, `value`, `contract_type`, `transaction_type`,
                    `token_address`, `token_id_int`, `token_id_hex`, `from_address`, `to_address`,
                    `amount`, `verified`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    await cur.executemany(sql, txs)
                    await conn.commit()
                    return cur.rowcount                    
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def insert_nft_deposited_credits(
            self, user_id: str, user_server: str, eth_nft_deposited: int,
            matic_nft_deposited: int, crediting, nft_tx_id: int,
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    INSERT INTO `nft_credit` (`network`, `token_address`, 
                    `token_id_int`, `token_id_hex`, `credited_user_id`, `credited_user_server`, `amount`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY
                    UPDATE
                        `amount`=VALUES(`amount`)+`amount`
                    """
                    await cur.execute(sql, crediting)
                    await conn.commit()
                    insert = cur.rowcount
                    if insert > 0:
                        sql = """
                        UPDATE `nft_main_wallet_nft_tx`, `tbl_users`
                            SET `nft_main_wallet_nft_tx`.`inserted_credited`=1,
                                `tbl_users`.`eth_nft_deposited`=`eth_nft_deposited`+%s,
                                `tbl_users`.`matic_nft_deposited`=`matic_nft_deposited`+%s
                        WHERE `nft_main_wallet_nft_tx`.`nft_tx_id`=%s
                            AND `tbl_users`.`user_id`=%s AND `tbl_users`.`user_server`=%s
                        """
                        await cur.execute(sql, (
                            eth_nft_deposited, matic_nft_deposited, nft_tx_id, user_id, user_server
                        ))
                        await conn.commit()
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    # ERC1155
    async def get_nft_erc1155_unverified_tx(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    SELECT `nft_main_wallet_nft_tx`.*, `nft_info_contract`.*
                    FROM `nft_main_wallet_nft_tx`
                        INNER JOIN `nft_info_contract` ON `nft_info_contract`.`contract`=`nft_main_wallet_nft_tx`.`token_address`
                    WHERE `nft_info_contract`.`contract_type`="ERC1155" AND `nft_main_wallet_nft_tx`.`inserted_credited`=0
                        AND `nft_info_contract`.`is_enable`=1
                    """
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_nft_erc1155_list(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    SELECT * FROM `nft_erc1155_list`
                    """
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def nft_erc1155_new_to_list(
        self, data_rows
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    INSERT INTO `nft_erc1155_list` (`network`, `name`, `token_address`, `token_id_hex`,
                    `token_uri`, `metadata`, `thumb_url`, `is_verified`, `inserted_date`, `check_later_date`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    await cur.executemany(sql, data_rows)
                    await conn.commit()
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0
    
    # Should we move to Moralis?
    async def nft_erc1155_get_nft_owners(self, chain: str, contract: str, token_id: int):
        try:
            url = self.bot.config['api']['moralis_nft_tx_api_url'] + "nft/"+contract+"/"+str(token_id)+"/owners?chain="+chain+"&format=decimal"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        url,
                        headers={'Content-Type': 'application/json', 'X-API-Key': self.bot.config['api']['moralis']},
                        timeout=30
                ) as response:
                    if response.status == 200:
                        res_data = await response.read()
                        res_data = res_data.decode('utf-8')
                        await session.close()
                        decoded_data = json.loads(res_data)
                        if decoded_data and 'result' in decoded_data and len(decoded_data['result']) > 0:
                            return decoded_data['result']
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def get_confirmed_nft1155_tx_to_notify(self):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT `metamask_v1`.*, `nft_main_wallet_nft_tx`.*, `nft_erc1155_list`.`name`, `nft_erc1155_list`.`token_address`, `nft_erc1155_list`.`token_id_hex`
                        FROM ((`metamask_v1`
                        INNER JOIN `nft_main_wallet_nft_tx` ON `metamask_v1`.`address` = `nft_main_wallet_nft_tx`.`from_address`)
                        INNER JOIN `tbl_users` ON `metamask_v1`.`discord_id` = `tbl_users`.`user_id`
                        INNER JOIN `nft_erc1155_list` ON `nft_main_wallet_nft_tx`.`token_address` = `nft_erc1155_list`.`token_address` AND `nft_erc1155_list`.`token_id_hex`=`nft_main_wallet_nft_tx`.`token_id_hex`
                        )
                        WHERE `tbl_users`.`is_frozen`=0 AND `metamask_v1`.`is_signed`=1 AND `nft_main_wallet_nft_tx`.`inserted_credited`=0 AND `nft_erc1155_list`.`is_verified`=1
                    """
                    await cur.execute(sql)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []
    # End of ERC1155

    # Meta Gen
    async def get_nft_rarity_contract_id(self, contract_id: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT `contract`, `update_date` 
                    FROM `nft_rarity` WHERE `nft_info_contract_id`=%s LIMIT 1
                    """
                    await cur.execute(sql, contract_id)
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None
    
    async def update_nft_rarity(
        self, nft_info_contract_id: int, contract: str, collection_name: str, rarity_json: str
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ INSERT INTO `nft_rarity` (`nft_info_contract_id`, `contract`, `collection_name`, `rarity_json`, `update_date`)
                    VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE 
                    `rarity_json` = VALUES(`rarity_json`), `update_date` = VALUES(`update_date`) """
                    await cur.execute(sql, (nft_info_contract_id, contract, collection_name, rarity_json, int(time.time())))
                    await conn.commit()
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def get_nft_items_by_contract(self, contract: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT *
                    FROM `nft_item_list` WHERE `contract`=%s
                    """
                    await cur.execute(sql, contract)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []
    
    async def clear_rarity_items(self, contract_id: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ DELETE FROM `nft_rarity_items` WHERE `nft_info_contract_id`=%s """
                    await cur.execute(sql, contract_id)
                    await conn.commit()
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False
    
    async def insert_rarity_items(self, data_rows):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ INSERT INTO `nft_rarity_items` (`nft_info_contract_id`, `nft_item_list_id`, 
                    `name`, `attributes_dump`, `missing_traits_dump`, `trait_count_dump`, `trait_count`, 
                    `rarity_score`, `rank`, `updated_date`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) """
                    await cur.executemany(sql, data_rows)
                    await conn.commit()
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def get_rarity_by_contract(self, contract_id: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT `nft_rarity_items`.*, `nft_info_contract`.*
                    FROM `nft_rarity_items`
                        INNER JOIN `nft_info_contract` ON `nft_info_contract`.`contract_id`=`nft_rarity_items`.`nft_info_contract_id`
                    WHERE `nft_info_contract`.`enable_rarity`=1 AND `nft_info_contract`.`is_enable`=1 AND `nft_info_contract`.`contract_id`=%s
                    """
                    await cur.execute(sql, contract_id)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_rarity_by_item_list_id(self, nft_item_list_id: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT `nft_rarity_items`.*, `nft_info_contract`.*, `nft_item_list`.`thumb_url`, `nft_item_list`.`meta`
                    FROM ((`nft_rarity_items`
                    INNER JOIN `nft_info_contract` ON `nft_rarity_items`.`nft_info_contract_id` = `nft_info_contract`.`contract_id`)
                    INNER JOIN `nft_item_list` ON `nft_rarity_items`.`nft_item_list_id` = `nft_item_list`.`item_id`)
                    WHERE `nft_info_contract`.`is_enable`=1 AND `nft_info_contract`.`enable_rarity`=1 AND `nft_item_list`.`item_id`=%s
                    """
                    await cur.execute(sql, nft_item_list_id)
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def get_rarity_by_item_list_name(self, nft_item_list_name: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT `nft_rarity_items`.*, `nft_info_contract`.*, `nft_item_list`.`thumb_url`, `nft_item_list`.`meta`
                    FROM ((`nft_rarity_items`
                    INNER JOIN `nft_info_contract` ON `nft_rarity_items`.`nft_info_contract_id` = `nft_info_contract`.`contract_id`)
                    INNER JOIN `nft_item_list` ON `nft_rarity_items`.`nft_item_list_id` = `nft_item_list`.`item_id`)
                    WHERE `nft_info_contract`.`is_enable`=1 AND `nft_info_contract`.`enable_rarity`=1 AND `nft_item_list`.`name`=%s
                    """
                    await cur.execute(sql, nft_item_list_name)
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def get_rarity_by_item_name_search(self, like: int, limit):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ 
                    SELECT `nft_rarity_items`.*, `nft_info_contract`.*
                    FROM ((`nft_rarity_items`
                    INNER JOIN `nft_info_contract` ON `nft_rarity_items`.`nft_info_contract_id` = `nft_info_contract`.`contract_id`)
                    INNER JOIN `nft_item_list` ON `nft_rarity_items`.`nft_item_list_id` = `nft_item_list`.`item_id`)
                    WHERE `nft_info_contract`.`is_enable`=1 AND `nft_info_contract`.`enable_rarity`=1 AND `nft_item_list`.`name` LIKE %s LIMIT """+str(limit)
                    await cur.execute(sql, "%" + like + "%")
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []
    # End of Meta Gen

    # Store message but not content
    async def insert_discord_message(self, list_message):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ INSERT INTO discord_messages (`serverid`, `server_name`, `channel_id`, `channel_name`, `user_id`, 
                               `message_author`, `message_id`, `message_time`) 
                              VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE 
                              `message_time`=VALUES(`message_time`)
                              """
                    await cur.executemany(sql, list_message)
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def delete_discord_message(self, message_id, user_id):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ DELETE FROM discord_messages WHERE `message_id`=%s AND `user_id`=%s LIMIT 1 """
                    await cur.execute(sql, (message_id, user_id))
                    await conn.commit()
        except Exception:
            traceback.print_exc(file=sys.stdout)
    # End of store messge

    # NFT Meta fetch
    async def get_active_nft_conts(self, limit: int=10):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT *
                    FROM `nft_cont_tracking` 
                    WHERE `is_enable`=1
                    ORDER BY `last_fetched_time` ASC
                    LIMIT %s
                    """
                    await cur.execute(sql, limit)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def get_count_nft_cont_tokens(self, nft_cont_tracking_id: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT COUNT(*) AS numb
                    FROM `nft_tokens` WHERE `nft_cont_tracking_id`=%s
                    """
                    await cur.execute(sql, nft_cont_tracking_id)
                    result = await cur.fetchone()
                    if result:
                        return result['numb']
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def get_active_nft_cont_tokens(self, nft_cont_tracking_id: int, limit: int):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT *
                    FROM `nft_tokens` WHERE `nft_cont_tracking_id`=%s
                    ORDER BY `nft_token_id` DESC
                    LIMIT %s
                    """
                    await cur.execute(sql, (nft_cont_tracking_id, limit))
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def insert_nft_tokens(
        self, list_nft_ids, last_token_id_hex, nft_cont_tracking_id
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    if len(list_nft_ids) > 0:
                        sql = """ INSERT INTO `nft_tokens` (`nft_cont_tracking_id`, `network`, 
                        `token_id_int`, `token_id_hex`, `token_type`, `title`, `tokenUri`, `media`,
                        `metadata`, `timeLastUpdated`, `timeLastUpdated_int`, `contractMetadata`) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        await cur.executemany(sql, list_nft_ids)
                        tx_inserted = cur.rowcount
                        if tx_inserted > 0:
                            sql = """ UPDATE `nft_cont_tracking` SET `last_token_id_hex`=%s, `last_fetched_time`=%s
                            WHERE `nft_cont_tracking_id`=%s
                            """
                            await cur.execute(sql, (last_token_id_hex, int(time.time()), nft_cont_tracking_id))
                        else:
                            sql = """ UPDATE `nft_cont_tracking` SET `last_fetched_time`=%s
                            WHERE `nft_cont_tracking_id`=%s
                            """
                            await cur.execute(sql, (int(time.time()), nft_cont_tracking_id))
                        return tx_inserted
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def update_contract_fetched_time(
        self, nft_cont_tracking_id
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ UPDATE `nft_cont_tracking` SET `last_fetched_time`=%s
                    WHERE `nft_cont_tracking_id`=%s
                    """
                    await cur.execute(sql, (int(time.time()), nft_cont_tracking_id))
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return False

    async def get_nft_token_list_no_image(self, from_number: int=200, limit: int=32):
        try:
            if limit > from_number:
                limit = from_number
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # GROUP BY `image` made slow
                    sql = """ 
                    SELECT * FROM `nft_tokens` AS t1 JOIN (SELECT DISTINCT(`image`), `title`, `nft_token_id` FROM `nft_tokens`
                    WHERE `image_null`=0 AND `local_stored_as_null`=1
                    LIMIT 200) AS t2 ON t1.`nft_token_id`=t2.`nft_token_id` ORDER BY RAND() LIMIT %s
                    """
                    await cur.execute(sql, limit)
                    result = await cur.fetchall()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return []

    async def update_nft_tracking_meta_image(
        self, data_rows
    ):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ UPDATE `nft_tokens`
                    SET `mimetype`=%s, `local_stored_as`=%s
                    WHERE `nft_token_id`=%s
                    """
                    await cur.executemany(sql, data_rows)
                    return cur.rowcount
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return 0

    async def check_nft_cont(self, contract: str, network: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ SELECT *
                    FROM `nft_cont_tracking` 
                    WHERE `contract`=%s AND `network`=%s
                    LIMIT 1
                    """
                    await cur.execute(sql, (contract, network))
                    result = await cur.fetchone()
                    if result:
                        return result
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None

    async def insert_new_nft_cont(self, contract: str, network: str, name: str):
        try:
            await self.openConnection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """ INSERT INTO `nft_cont_tracking` 
                    (`contract`, `name`, `network`)
                    VALUES (%s, %s, %s)
                    """
                    await cur.execute(sql, (contract, name, network))
                    return True
        except Exception:
            traceback.print_exc(file=sys.stdout)
        return None
    # End of NFT Meta fetch

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.pull_eth_gas_price.is_running():
            self.pull_eth_gas_price.start()
        if not self.pull_matic_gas_price.is_running():
            self.pull_matic_gas_price.start()

    async def cog_load(self) -> None:
        if not self.pull_eth_gas_price.is_running():
            self.pull_eth_gas_price.start()
        if not self.pull_matic_gas_price.is_running():
            self.pull_matic_gas_price.start()

    async def cog_unload(self) -> None:
        self.pull_eth_gas_price.cancel()
        self.pull_matic_gas_price.cancel()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utils(bot))
