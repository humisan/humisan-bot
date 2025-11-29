import discord
from discord.ext import commands
from typing import Optional
import traceback
from utils.logger import setup_logger

logger = setup_logger(__name__)

async def get_member(ctx: commands.Context, member_id_or_name: str) -> Optional[discord.Member]:
    """Get a member by ID or mention"""
    try:
        # Try to get by mention
        members = await commands.MemberConverter().convert(ctx, member_id_or_name)
        return members
    except commands.BadArgument:
        try:
            # Try to get by ID
            member_id = int(member_id_or_name)
            return ctx.guild.get_member(member_id)
        except ValueError:
            # Try to get by name
            return discord.utils.get(ctx.guild.members, name=member_id_or_name)

def get_member_embed(member: discord.Member) -> discord.Embed:
    """Create an embed with member information"""
    embed = discord.Embed(
        title=f"User Information - {member.name}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
    embed.add_field(name="User ID", value=member.id, inline=False)
    embed.add_field(name="Username", value=member.name, inline=False)
    embed.add_field(name="Joined", value=member.joined_at.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
    embed.add_field(name="Account Created", value=member.created_at.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
    embed.add_field(name="Roles", value=', '.join([role.mention for role in member.roles[1:]]) or "None", inline=False)
    return embed

def create_error_embed(error: str, details: str = "") -> discord.Embed:
    """Create an error embed"""
    embed = discord.Embed(
        title="❌ エラーが発生しました",
        description=error,
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    if details:
        embed.add_field(name="詳細", value=details, inline=False)
    return embed

def create_success_embed(title: str, description: str = "") -> discord.Embed:
    """Create a success embed"""
    embed = discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )
    return embed

async def send_error_to_discord(bot: commands.Bot, error_title: str, error_message: str, error_type: str = "エラー"):
    """Send error message to Discord error log channel and console"""
    try:
        # Console に出力
        logger.error(f"{error_type} - {error_title}: {error_message}")

        # Discord のエラーログチャンネルに送信
        error_channel_id = int(__import__('os').getenv('ERROR_LOG_CHANNEL_ID', 0))
        if error_channel_id:
            try:
                error_channel = bot.get_channel(error_channel_id)
                if error_channel:
                    embed = create_error_embed(error_title, error_message[:4096])  # Discord の文字制限に対応
                    await error_channel.send(embed=embed)
            except Exception as channel_error:
                logger.error(f"Failed to send error to Discord channel: {str(channel_error)}")
    except Exception as e:
        logger.error(f"Failed to send error notification: {str(e)}")
