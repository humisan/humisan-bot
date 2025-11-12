import discord
from discord.ext import commands
from typing import Optional

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
