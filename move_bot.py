import os
import io
import json
import discord
import requests
import sqlite3
from contextlib import closing
from discord import Thread
from discord.http import Route
from discord.webhook import Webhook
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
STATS_TOKEN = os.getenv('STATS_TOKEN')
STATS_ID = os.getenv('MOVEBOT_STATS_ID')
LISTEN_TO = os.getenv('LISTEN_TO')
ADMIN_ID = os.getenv('ADMIN_UID')
BOT_ID = os.getenv('MOVEBOT_ID')

available_prefs = ["notify_dm", "move_message"]
default_msg = "MESSAGE_USER, your message has been moved to DESTINATION_CHANNEL by MOVER_USER"

prefs = {}
with sqlite3.connect("settings.db") as connection:
    connection.row_factory = sqlite3.Row
    with closing(connection.cursor()) as cursor:
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS prefs (
            key INTEGER PRIMARY KEY,
            guild_id INTEGER,
            pref TEXT,
            value TEXT)"""
        )
        cursor.execute(f"SELECT * FROM prefs")
        rows = cursor.fetchall()
        for row in rows:
            g_id = int(row["guild_id"])
            if g_id not in prefs:
                prefs[g_id] = {}
            prefs[g_id][str(row["pref"])] = str(row["value"])

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f'for spoilers | {LISTEN_TO} help'))

    global admin
    admin = await client.fetch_user(int(ADMIN_ID))

@client.event
async def on_guild_join(guild):
    url=f'https://discordbotlist.com/api/v1/bots/{STATS_ID}/stats'
    headers = {
        "Authorization": STATS_TOKEN,
        "Content-Type": 'application/json'
    }
    payload = json.dumps({
        "guilds": len(client.guilds)
    })
    requests.request("POST", url, headers=headers, data=payload)

    notify_me = f'MoveBot was added to {guild.name} ({guild.member_count} members)! Currently in {len(client.guilds)} servers.'
    await admin.send(notify_me)

@client.event
async def on_guild_remove(guild):
    url=f'https://discordbotlist.com/api/v1/bots/{STATS_ID}/stats'
    headers = {
        "Authorization": STATS_TOKEN,
        "Content-Type": 'application/json'
    }
    payload = json.dumps({
        "guilds": len(client.guilds)
    })
    requests.request("POST", url, headers=headers, data=payload)

    notify_me = f'MoveBot was removed from {guild.name} ({guild.member_count} members)! Currently in {len(client.guilds)} servers.'
    await admin.send(notify_me)

@client.event
async def on_message(msg_in):
    if msg_in.author == client.user:
        return

    if msg_in.author.bot:
        return

    guild_id = msg_in.guild.id
    txt_channel = msg_in.channel
    if msg_in.content.startswith("!mv reset"):
        with sqlite3.connect("settings.db") as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.cursor()) as cursor:
                cursor.execute("DELETE FROM prefs WHERE guild_id = ?", (guild_id,))
        if guild_id in prefs:
            prefs.pop(guild_id)
        await txt_channel.send("All preferences reset to default")
    elif msg_in.content.startswith(LISTEN_TO):
        params = msg_in.content.split(maxsplit=3)

        # !mv help
        if len(params) < 2 or params[1] == 'help':
            e = discord.Embed(title="MoveBot Help")
            e.description = \
                "This bot can move messages in two different ways.\n" + \
                "*Moving messages requires to have the 'Manage messages' permission.*\n\n" + \
                "**Method 1: Using the target message's ID**\n" + \
                "!mv [messageID] [#targetChannelOrThread] [optional message]\n\n" + \
                "**Method 2: Replying to the target message**\n" + \
                "!mv [#targetChannelOrThread] [optional message]\n\n" + \
                "**Preferences**\n" + \
                "You can set bot preferences like so:\n" + \
                "!mv pref [preference name] [preference value]\n\n" + \
                "name: notify_dm\n" + \
                "value: '0' (Sends move message in channel) '1' (Sends move message as a DM)\n\n" + \
                "name: move_message\n" + \
                "value: main message sent to the user.\n" + \
                "variables: MESSAGE_USER, DESTINATION_CHANNEL, MOVER_USER\n\n" + \
                "*Feel free to contact **N3X4S#6792** for any question or suggestion!*"
            await msg_in.author.send(embed=e)

        # !mv pref [pref_name] [pref_value]
        elif params[1] == "pref":
            if len(params) == 2:
                error_msg = f"No preference name was provided. Options: {', '.join(available_prefs)}"
            elif len(params) < 4:
                error_msg = "An invalid preference format was provided. !mv pref [preference name] [preference value]"
            elif params[2] not in available_prefs:
                error_msg = f"An invalid preference name was provided. Options: {', '.join(available_prefs)}"
            else:
                with sqlite3.connect("settings.db") as connection:
                    connection.row_factory = sqlite3.Row
                    with closing(connection.cursor()) as cursor:
                        cursor.execute("INSERT OR IGNORE INTO prefs(guild_id, pref) VALUES(?, ?)", (guild_id, params[2]))
                        cursor.execute(f"UPDATE prefs SET value = ? WHERE guild_id = ? AND pref = ?", (params[3], guild_id, params[2]))
                if guild_id not in prefs:
                    prefs[guild_id] = {}
                prefs[guild_id][params[2]] = params[3]
                error_msg = f"Pref: {params[2]} Updated to {params[3]}"
            await txt_channel.send(error_msg)

        # !mv [msgID] [#channel] [optional message]
        else:
            if msg_in.author.guild_permissions.manage_messages:
                error_msg = ''
                channel_param = 2
                try:
                    if msg_in.reference is not None:
                        moved_msg = await txt_channel.fetch_message(msg_in.reference.message_id)
                        channel_param = 1
                    else:
                        moved_msg = await txt_channel.fetch_message(params[1])
                except:
                    error_msg = error_msg + 'An invalid message ID was provided. You can ignore the message ID by executing the **move** command as a reply to the target message'

                try:
                    target_channel = msg_in.guild.get_channel_or_thread(int(params[channel_param].strip('<#').strip('>')))
                except:
                    error_msg = error_msg + "An invalid channel was provided. "

                if error_msg:
                    await txt_channel.send(error_msg)
                else:
                    r = Route('POST', '/channels/{channel_id}/webhooks', channel_id=target_channel.parent_id if isinstance(target_channel, Thread) else target_channel.id)
                    data = await target_channel._state.http.request(r, json={'name': str(moved_msg.author.display_name)})
                    wb = Webhook.from_state(data, state=target_channel._state)
                    files = []
                    for file in moved_msg.attachments:
                        f = io.BytesIO()
                        await file.save(f)
                        files.append(discord.File(f, filename=file.filename))

                    if isinstance(target_channel, Thread):
                        await wb.send(content=moved_msg.content, avatar_url=moved_msg.author.avatar, embeds=moved_msg.embeds, files=files, thread=target_channel)
                    else:
                        await wb.send(content=moved_msg.content, avatar_url=moved_msg.author.avatar, embeds=moved_msg.embeds, files=files)
                    await wb.delete()

                    extra = f'\n\n{params[channel_param + 1]}' if len(params) > channel_param + 1 else ''
                    if guild_id in prefs and "move_message" in prefs[guild_id] and prefs[guild_id]["move_message"]:
                        notice_msg = prefs[guild_id]["move_message"]
                    else:
                        notice_msg = default_msg
                    notice_msg = notice_msg.replace("MESSAGE_USER", f"<@!{moved_msg.author.id}>") \
                        .replace("DESTINATION_CHANNEL", params[channel_param]) \
                        .replace("MOVER_USER", f"<@!{msg_in.author.id}>")

                    notice_msg = f'{notice_msg}{extra}'
                    if guild_id in prefs and "notify_dm" in prefs[guild_id] and prefs[guild_id]["notify_dm"] == "1":
                        await msg_in.author.send(notice_msg)
                    else:
                        await txt_channel.send(notice_msg)
                    await msg_in.delete()
                    await moved_msg.delete()

#end
client.run(TOKEN)
