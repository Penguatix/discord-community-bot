import sqlite3
import discord
from discord.ext import commands
from discord import app_commands

DB_FILE = "profile.db"

class ServerConfig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    group = app_commands.Group(name="setup", description="Server configuration and feature toggles.")

    @group.command(name="set-role", description="Bind a core system role for this server.")
    @app_commands.choices(setting=[
        app_commands.Choice(name="Verified 18+ Role", value="verify_role_id"),
        app_commands.Choice(name="Unverified Gate Role", value="unverified_role_id"),
        app_commands.Choice(name="Support Staff Role", value="support_role_id"),
        app_commands.Choice(name="Bump Ping Role", value="bump_role_id"),
        app_commands.Choice(name="Dead Chat Ping Role", value="dead_chat_role_id"),
        app_commands.Choice(name="Voice Lobby Ping Role", value="vc_ping_role_id")
    ])
    @commands.has_permissions(administrator=True)
    async def set_role(self, interaction: discord.Interaction, setting: app_commands.Choice[str], role: discord.Role):
        """Saves a crucial system role into the specific guild's database layout."""
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute(f"INSERT INTO guild_settings (guild_id, {setting.value}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {setting.value} = excluded.{setting.value}", (interaction.guild.id, str(role.id)))
        conn.commit(); conn.close()
        await interaction.response.send_message(f"✅ **{setting.name}** has been securely mapped to {role.mention} for this server.", ephemeral=True)
        
    @group.command(name="set-channel", description="Bind a core system channel for this server.")
    @app_commands.choices(setting=[
        app_commands.Choice(name="General/Welcome Channel", value="general_channel_id"),
        app_commands.Choice(name="Verification Gate Channel", value="verify_channel_id"),
        app_commands.Choice(name="System Logging Channel", value="log_channel_id")
    ])
    @commands.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, setting: app_commands.Choice[str], channel: discord.TextChannel):
        """Saves a crucial channel into the specific guild's database layout."""
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute(f"INSERT INTO guild_settings (guild_id, {setting.value}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {setting.value} = excluded.{setting.value}", (interaction.guild.id, str(channel.id)))
        conn.commit(); conn.close()
        await interaction.response.send_message(f"✅ **{setting.name}** has been securely mapped to {channel.mention} for this server.", ephemeral=True)

    @group.command(name="toggle-feature", description="Enable or disable a specific bot module in this server.")
    @app_commands.choices(module=[
        app_commands.Choice(name="Reputation & Chat Streaks", value="reputation_enabled"),
        app_commands.Choice(name="Social Interaction Commands", value="social_enabled")
    ])
    @app_commands.choices(state=[
        app_commands.Choice(name="Enable (Turn On)", value=1),
        app_commands.Choice(name="Disable (Turn Off)", value=0)
    ])
    @commands.has_permissions(administrator=True)
    async def toggle_feature(self, interaction: discord.Interaction, module: app_commands.Choice[str], state: app_commands.Choice[int]):
        """Modifies boolean values for large core architecture modules."""
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute(f"INSERT INTO guild_features (guild_id, {module.value}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {module.value} = excluded.{module.value}", (interaction.guild.id, state.value))
        conn.commit(); conn.close()
        status = "🟢 ENABLED" if state.value == 1 else "🔴 DISABLED"
        await interaction.response.send_message(f"⚙️ **{module.name}** is now {status} for {interaction.guild.name}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ServerConfig(bot))