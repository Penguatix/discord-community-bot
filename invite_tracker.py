import sqlite3
import discord
from discord.ext import commands

DB_FILE = "profile.db"

class InviteTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Cache format: { guild_id: { "invite_code": {"uses": int, "inviter_id": int} } }
        self.invite_cache = {}

    async def _update_guild_cache(self, guild: discord.Guild):
        """Fetches and caches all current invites for a guild."""
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {
                inv.code: {
                    "uses": inv.uses,
                    "inviter_id": inv.inviter.id if inv.inviter else None
                }
                for inv in invites
            }
        except discord.Forbidden:
            print(f"⚠️ Missing 'Manage Server' permissions to track invites in {guild.name}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Initializes the invite cache for all guilds on bot startup."""
        for guild in self.bot.guilds:
            await self._update_guild_cache(guild)
        print("✅ Invite Tracker: All guild invite caches initialized.")

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        """Listens for newly created invites and adds them to cache immediately."""
        if invite.guild.id not in self.invite_cache:
            self.invite_cache[invite.guild.id] = {}
            
        self.invite_cache[invite.guild.id][invite.code] = {
            "uses": invite.uses,
            "inviter_id": invite.inviter.id if invite.inviter else None
        }

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Intercepts joining users, calculates which invite they clicked, and logs it."""
        guild = member.guild
        if member.bot: return

        old_cache = self.invite_cache.get(guild.id, {})
        
        try:
            current_invites = await guild.invites()
        except discord.Forbidden:
            return

        used_inviter_id = None
        new_cache = {}

        # 1. Check existing invites for an incremented use count
        for inv in current_invites:
            new_cache[inv.code] = {
                "uses": inv.uses,
                "inviter_id": inv.inviter.id if inv.inviter else None
            }
            if inv.code in old_cache:
                if inv.uses > old_cache[inv.code]["uses"]:
                    used_inviter_id = inv.inviter.id if inv.inviter else None

        # 2. Check for DELETED/SINGLE-USE links (the single-use invite trap fix)
        if not used_inviter_id:
            for code, cached_data in old_cache.items():
                if code not in new_cache:
                    # The invite vanished from Discord's API! It was a max_uses=1 link.
                    used_inviter_id = cached_data["inviter_id"]
                    break

        # Save the freshly fetched list back into the cache
        self.invite_cache[guild.id] = new_cache

        # Record to database if we resolved the inviter
        if used_inviter_id:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO invite_tracking (guild_id, invited_id, inviter_id, rewarded) VALUES (?, ?, ?, 0)",
                (guild.id, member.id, used_inviter_id)
            )
            conn.commit()
            conn.close()
            
            # Automatically trigger point rewards if member isn't unverified
            if hasattr(self.bot, "award_invite_points"):
                await self.bot.award_invite_points(member)

async def setup(bot):
    await bot.add_cog(InviteTracker(bot))