import sys
import traceback
from datetime import datetime
import os
import re
import discord
from discord import app_commands
from discord.ext import commands
import time
import json
import ujson
import subprocess
import functools
from typing import List

from cogs.utils import Utils
from cogs.alchemy_api import check_contract_alchemy

class Admin(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self.utils = Utils(self.bot)

    @staticmethod
    async def owner_only(interaction: discord.Interaction):
        return await interaction.client.is_owner(interaction.user)

    @app_commands.check(owner_only)
    @app_commands.command(
        name='addopensea',
        description="Add Contract by OpenSea or other to tokenBot"
    )
    async def slash_contract_addopensea(
        self, interaction: discord.Interaction,
        link: str
    ) -> None:
        """ /addopensea <link> """
        await interaction.response.send_message(f"{interaction.user.mention} loading link...", ephemeral=True)
        if interaction.user.id not in self.bot.config['discord']['owner_ids']:
            await interaction.edit_original_response(content="Permission denied!!")
            return
        else:
            try:
                contract = None
                token_id = None
                if "https://opensea.io/assets/" in link:
                    links = re.findall(r'(https?://\S+)', link)
                    if len(links) < 1:
                        return
                    contract_token_id = links[0].rstrip('/').split("/")[-3:]
                    if contract_token_id:
                        timeout = 32
                        network = contract_token_id[0]
                        if network == "ethereum":
                            chain = "eth"
                            network = "ETHEREUM"
                            url = "https://eth-mainnet.g.alchemy.com/nft/v2/"
                        elif network == "polygon" or network == "matic":
                            chain = network
                            network = "POLYGON"
                            url = "https://polygon-mainnet.g.alchemy.com/nft/v2/"
                        else:
                            await interaction.edit_original_response(content="Wrong network `{network}`")
                            return
                        contract = contract_token_id[1].lower()
                        token_id = contract_token_id[2].split()[0]
                        url += self.bot.config['api']['alchemy']+"/getContractMetadata?contractAddress="+contract

                        check_cont = await check_contract_alchemy(url, contract)
                        if check_cont is None:
                            await interaction.edit_original_response(content="Contract may not be valid.")
                            return
                        elif check_cont and check_cont['contractMetadata']['tokenType'] not in ["ERC1155", "ERC721"]:
                            await interaction.edit_original_response(content="Contract type is not ERC1155 nor ERC721!")
                            return
                        elif check_cont and check_cont['contractMetadata']['tokenType'] in ["ERC1155", "ERC721"]:
                            if 'name' not in check_cont['contractMetadata']:
                                await interaction.edit_original_response(content="Couldn't fetch name, please add manually.")
                                return
                            name = check_cont['contractMetadata']['name']
                            # Check if exist
                            get_cont = await self.utils.check_nft_cont(contract, network)
                            if get_cont is not None:
                                await interaction.edit_original_response(content="Contract `{}` already existed in DB!".format(contract))
                            else:
                                inserting = await self.utils.insert_new_nft_cont(contract, network, name)
                                if inserting is True:
                                    await interaction.edit_original_response(content="Successfully added contract `{}` / `{}` / `{}`".format(
                                        contract, network, name
                                    ))
                else:
                    await interaction.edit_original_response(content="Not supported yet with `{link}`")
                    return
            except Exception as e:
                traceback.print_exc(file=sys.stdout)

    # Thanks to: https://github.com/middlerange/rarity-analyzer
    @app_commands.check(owner_only)
    @app_commands.command(
        name="metagen",
        description="Generate rarity from meta in database."
    )
    async def command_metagen(
        self, interaction: discord.Interaction, contract_id: str
    ) -> None:
        """ /metagen """
        await interaction.response.send_message("Loading meta gen...", ephemeral=True)
        try:
            if interaction.user.id not in self.bot.config['discord']['owner_ids']:
                await interaction.edit_original_response(
                    content=f"{interaction.user.mention}, permission denied."
                )
                return

            if self.bot.config['rarity']['enable_meta_gen'] != 1:
                await interaction.edit_original_response(
                    content=f"{interaction.user.mention}, command disable."
                )
                return

            get_contract = await self.utils.get_contract_by_id(contract_id)
            if get_contract is None:
                await interaction.edit_original_response(
                    content=f"{interaction.user.mention}, the Contract `{contract_id}` was not found."
                )
                return
            elif get_contract and get_contract['enable_rarity'] == 0:
                await interaction.edit_original_response(
                    content=f"{interaction.user.mention}, the Contract `{contract_id}` not enable with rarity."
                )
                return
            contract_id = get_contract['contract_id'] # replace id
            contract = get_contract['contract']
            collection_name = get_contract['collection_name']
            
            get_rarity_contract = await self.utils.get_nft_rarity_contract_id(contract_id)
            if get_rarity_contract and int(time.time()) - 600 < get_rarity_contract['update_date']:
                await interaction.edit_original_response(
                    content=f"{interaction.user.mention}, the Contract `{contract}` was just recently updated."
                )
                return
            else:
                get_items = await self.utils.get_nft_items_by_contract(contract)
                if len(get_items) == 0:
                    await interaction.edit_original_response(
                        content=f"{interaction.user.mention}, the Contract `{contract}` has no items in database."
                    )
                    return
                else:
                    meta_list = []
                    for each_meta in get_items:
                        data_json = json.loads(each_meta['meta'])
                        if "nft_item_list_id" not in data_json:
                            data_json["nft_item_list_id"] = each_meta['item_id']

                        if "token_id" not in data_json:
                            data_json["token_id"] = int(each_meta['asset_id_hex'], 16)
                        meta_list.append(data_json)
                    meta_list_text = ujson.dumps(meta_list, ensure_ascii=False, escape_forward_slashes=False)
                    # Create a temporary directory & file
                    dir_name = f"/tmp/{contract}_{str(int(time.time()))}_meta_generate"
                    os.mkdir(dir_name)
                    file_name = "meta.json"
                    file_name_out = "rarity.json"
                    path_in = dir_name + "/" + file_name
                    path_out = dir_name + "/" + file_name_out
                    f = open(dir_name + "/" + file_name, "a")
                    f.write(meta_list_text)
                    f.close()

                    def meta_gen(path_json_in: str, path_json_out: str):
                        try:
                            command = f"node rarity-analyzer-compute.js {path_json_in} {path_json_out}"
                            process_meta = subprocess.Popen(command, shell=True)
                            process_meta.wait(timeout=20000) # 20s waiting
                            if os.path.isfile(path_json_out):
                                return path_json_out
                        except Exception as e:
                            traceback.print_exc(file=sys.stdout)
                        return None

                    create_meta = functools.partial(meta_gen, path_in, path_out)
                    generate = await self.bot.loop.run_in_executor(None, create_meta)
                    if generate:
                        # Insert to database
                        path_to_file = open(generate, "r")
                        rarity_json = path_to_file.read()
                        path_to_file.close()
                        await self.utils.update_nft_rarity(contract_id, contract, collection_name, rarity_json)
                        await self.utils.clear_rarity_items(contract_id)
                        # add rarity items
                        rarity_json_data = json.loads(rarity_json)
                        data_rows = []
                        for each_item in rarity_json_data['rarity']:
                            if each_item:
                                data_rows.append((
                                    contract_id, each_item['nft_item_list_id'], each_item['name'],
                                    json.dumps(each_item['attributes']), json.dumps(each_item['missing_traits']),
                                    json.dumps(each_item['trait_count']), each_item['trait_count']['count'],
                                    each_item['rarity_score'], each_item['rank'], int(time.time())
                                ))
                        if len(data_rows) > 0:
                            records = await self.utils.insert_rarity_items(data_rows)
                            await interaction.edit_original_response(
                                content=f"{interaction.user.mention}, the Contract `{contract}` "
                                        f"inserted/updated {str(records)}."
                            )
                        else:
                            await interaction.edit_original_response(
                                content=f"{interaction.user.mention}, the Contract `{contract}` caught 0 data."
                            )
                        return
        except Exception:
            traceback.print_exc(file=sys.stdout)

    @command_metagen.autocomplete('contract_id')
    async def contract_id_callback(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        # Do stuff with the "current" parameter, e.g. querying it search results...
        list_contracts = await self.utils.get_list_contracts()
        contract_ids = []
        contract_names = []
        if len(list_contracts) > 0:
            for each in list_contracts:
                if each['contract_id'] not in contract_ids and each['enable_rarity'] == 1:
                    contract_names.append(each['collection_name'])
                    contract_ids.append(str(each['contract_id']))
            return [
                app_commands.Choice(name=item, value=contract_ids[contract_names.index(item)])
                for item in contract_names if current.lower() in item.lower()
            ]
        else:
            item_list = ["N/A"]
            return [
                app_commands.Choice(name=item, value=item)
                for item in item_list if current.lower() in item.lower()
            ]

    async def cog_load(self) -> None:
        pass

    async def cog_unload(self) -> None:
        pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
