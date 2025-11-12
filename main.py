import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()

# Configure bot intents
intents = discord.Intents.default()
# message_content intent is not required for slash commands
# intents.message_content = True

# Create bot instance (command_prefix is unused now; all commands are slash commands)
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    """Called when the bot is ready"""
    print(f'{bot.user.name} is online!')
    print(f'Bot ID: {bot.user.id}')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} application command(s).')
    except Exception as e:
        print(f'Failed to sync application commands: {e}')
    print('------')


# Slash command: /ping
@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f'Pong! {round(bot.latency * 1000)}ms', ephemeral=True)


# Slash command: /hello
@bot.tree.command(name="hello", description="Say hello")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f'Hello, {interaction.user.mention}!')


# Slash command: /info
@bot.tree.command(name="info", description="Show bot information")
async def info(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Bot Info",
        description=f"Hello! I am {bot.user.name}.",
        color=0x00ff00
    )
    embed.add_field(name="Servers", value=len(bot.guilds), inline=True)
    embed.add_field(name="Users (cached)", value=len(bot.users), inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)

    await interaction.response.send_message(embed=embed)


# Slash command: /greet [name]
@bot.tree.command(name="greet", description="Send a greeting (optionally to a specific name)")
@app_commands.describe(name="Name to greet; if omitted, greets you")
async def greet(interaction: discord.Interaction, name: Optional[str] = None):
    target = name or interaction.user.display_name
    await interaction.response.send_message(f'Hello, {target}!')


# Application command error handler
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    print(f'App command error: {error}')
    message = "An error occurred while executing that command."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception as e:
        print(f'Failed to send error response: {e}')


if __name__ == '__main__':
    # Get bot token from environment
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')

    if TOKEN is None:
        print("Error: DISCORD_BOT_TOKEN is not set.")
        print("1. Create a .env file in the project root")
        print("2. Add: DISCORD_BOT_TOKEN=your_bot_token_here")
    else:
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            print("Error: Invalid bot token.")
        except Exception as e:
            print(f"Unexpected error: {e}")