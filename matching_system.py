import os
import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands, tasks

DB_FILE = "profile.db"

# -------------------------------------------------------------
# PRIVATE ACTIVE WORKSPACE ROOM CONTROLS
# -------------------------------------------------------------
class MatchRoomControlView(discord.ui.View):
    """Button suite appended to every active Match Room thread."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="End Chat Gracefully", style=discord.ButtonStyle.secondary, emoji="🛑", custom_id="end_chat_btn")
    async def end_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Immediately destroys the thread upon execution."""
        thread = interaction.channel
        bot = interaction.client
        if thread.id not in bot.active_matches:
            await interaction.response.send_message("❌ Session tracking context lost.", ephemeral=True)
            return
            
        await interaction.response.send_message("🛑 **Chat session dissolved by user.** Room self-destructing in 5 seconds...")
        bot.db_remove_active_match(thread.id) 
        await asyncio.sleep(5)
        await thread.delete()

    @discord.ui.button(label="Report Bad Behavior", style=discord.ButtonStyle.danger, emoji="⚠️", custom_id="report_match_btn")
    async def report_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Kicks out thread members, locks the channel, and dumps the archive directly to staff."""
        thread = interaction.channel
        reporter = interaction.user
        guild = interaction.guild
        bot = interaction.client
        
        if thread.id not in bot.active_matches:
            await interaction.response.send_message("❌ Registry validation fault.", ephemeral=True)
            return

        button.disabled = True
        await interaction.response.send_message("⚠️ **Safety dispatch logged.** Securing the room immediately.", ephemeral=True)
        
        try: await interaction.message.edit(view=self)
        except Exception: pass

        match_info = bot.active_matches.get(thread.id, {})
        matched_user_ids = match_info.get("users", [])
        room_type = match_info.get("type", "unknown").upper()
        bot.db_remove_active_match(thread.id) 

        for user_id in matched_user_ids:
            target_member = guild.get_member(user_id)
            if target_member:
                try: await thread.remove_user(target_member)
                except Exception: pass

        try: await thread.edit(name=f"🚨-{room_type.lower()}-report-{reporter.name}", locked=True)
        except Exception as e: print(f"⚠️ Thread lock failure: {e}")

        staff_embed = discord.Embed(
            title="🚨 Emergency Preservation Log",
            description=f"**Reported By:** {reporter.mention} (`{reporter.id}`)\n"
                        f"**Status:** Users removed. Room isolated successfully.\n"
                        f"**Evidence Check:** Scroll upwards to audit history.",
            color=discord.Color.red()
        )
        await thread.send(embed=staff_embed)

        log_chan_id = bot.get_config(guild.id, 'log_channel_id') if guild else None
        if log_chan_id and str(log_chan_id).strip().isdigit():
            try:
                log_channel = guild.get_channel(int(log_chan_id)) or bot.get_channel(int(log_chan_id))
                if log_channel:
                    embed = discord.Embed(
                        title=f"🚨 New [{room_type}] Chat Room Report Filed",
                        color=discord.Color.red(),
                        description=f"**Filed By:** {reporter.mention}\n👉 **[Click Here to Enter the Thread]({thread.jump_url})**"
                    )
                    await log_channel.send(embed=embed)
            except Exception as e: print(f"⚠️ Log system write fail: {e}")

# -------------------------------------------------------------
# SUPPORT TICKET DELETION MODAL (ADMIN ONLY)
# -------------------------------------------------------------
class DeleteTicketModal(discord.ui.Modal):
    """Text box modal that intercepts and saves deletion reasons directly to logs."""
    def __init__(self):
        super().__init__(title="Delete Ticket (Admin Only)")
        self.reason_input = discord.ui.TextInput(
            label="Reason for ticket deletion:",
            style=discord.TextStyle.paragraph,
            placeholder="e.g., Not valuable / Invalid ticket / Resolved without archive",
            max_length=200,
            required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        thread = interaction.channel
        admin = interaction.user
        guild = interaction.guild
        bot = interaction.client
        reason = self.reason_input.value

        await interaction.response.defer(ephemeral=True)

        log_chan_id = bot.get_config(guild.id, 'log_channel_id') if guild else None
        if log_chan_id and str(log_chan_id).strip().isdigit():
            try:
                log_channel = guild.get_channel(int(log_chan_id)) or bot.get_channel(int(log_chan_id))
                if log_channel:
                    embed = discord.Embed(
                        title="🗑️ Support Ticket Force Deleted",
                        color=discord.Color.dark_red(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="🎫 Ticket Name", value=f"`{thread.name}`", inline=True)
                    embed.add_field(name="🛡️ Actioned By", value=admin.mention, inline=True)
                    embed.add_field(name="📝 Reason", value=reason, inline=False)
                    await log_channel.send(embed=embed)
            except Exception as e: print(f"⚠️ Ticket deletion log write failure: {e}")

        try:
            await interaction.followup.send("🗑️ **Ticket deleted.** Thread self-destructing...", ephemeral=True)
        except Exception: pass

        await asyncio.sleep(1)
        try:
            await thread.delete()
        except Exception as e: print(f"⚠️ Ticket thread deletion fault: {e}")

class TicketRoomControlView(discord.ui.View):
    """Persistent controls dropped into newly generated support tickets."""
    def __init__(self):
        super().__init__(timeout=None)

    async def is_staff_or_admin(self, interaction: discord.Interaction):
        """Cross-checks whether the executing user owns proper clearance."""
        if interaction.user.guild_permissions.administrator:
            return True
        
        bot = interaction.client
        guild = interaction.guild
        
        support_role_id = bot.get_config(guild.id, 'support_role_id')
        
        if support_role_id and str(support_role_id).strip().isdigit():
            target_id = int(support_role_id)
            user_role_ids = [role.id for role in interaction.user.roles]
            if target_id in user_role_ids:
                return True
                
        return False

    @discord.ui.button(label="Close & Save Ticket", style=discord.ButtonStyle.success, emoji="🔒", custom_id="close_save_ticket_btn")
    async def close_ticket_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Converts an active ticket thread to a read-only archive."""
        if not await self.is_staff_or_admin(interaction):
            await interaction.response.send_message("❌ **Permission Denied:** You need the designated Staff role or Administrator permissions to manage support tickets.", ephemeral=True)
            return
        
        thread = interaction.channel
        closer = interaction.user
        guild = interaction.guild
        bot = interaction.client

        button.disabled = True
        await interaction.response.send_message("🔒 **Ticket processing...** Locking conversation history container.")

        try: await interaction.message.edit(view=self)
        except Exception: pass

        try:
            async for member in thread.history(limit=100):
                if member.author.bot: continue
                try: await thread.remove_user(member.author)
                except Exception: pass
        except Exception: pass

        try:
            clean_name = thread.name.replace("🎫┃ticket-", "")
            await thread.edit(name=f"✅┃closed-{clean_name}", locked=True)
        except Exception as e: print(f"⚠️ Ticket thread lock failure: {e}")

        log_chan_id = bot.get_config(guild.id, 'log_channel_id') if guild else None
        if log_chan_id and str(log_chan_id).strip().isdigit():
            try:
                log_channel = guild.get_channel(int(log_chan_id)) or bot.get_channel(int(log_chan_id))
                if log_channel:
                    embed = discord.Embed(
                        title="🎫 Server Support Ticket Archived",
                        color=discord.Color.blue(),
                        description=f"**Actioned By:** {closer.mention}\n👉 **[Click Here to Inspect Full Ticket History]({thread.jump_url})**"
                    )
                    await log_channel.send(embed=embed)
            except Exception as e: print(f"⚠️ Support logging write failure: {e}")

    @discord.ui.button(label="Delete Ticket", style=discord.ButtonStyle.secondary, emoji="🗑️", custom_id="delete_ticket_btn")
    async def delete_ticket_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Triggers the modal deletion interceptor."""
        if not await self.is_staff_or_admin(interaction):
            await interaction.response.send_message("❌ **Permission Denied:** You need the designated Staff role or Administrator permissions to force delete tickets.", ephemeral=True)
            return

        await interaction.response.send_modal(DeleteTicketModal())

    @discord.ui.button(label="Delete & Penalize (Spam)", style=discord.ButtonStyle.danger, emoji="⚠️", custom_id="ticket_penalize_btn")
    async def delete_and_penalize(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Forces immediate destruction alongside a heavy database point removal if Rep engine active."""
        if not await self.is_staff_or_admin(interaction):
            await interaction.response.send_message("❌ **Permission Denied:** You need the designated Staff role or Administrator permissions to execute a penalty wipe.", ephemeral=True)
            return
            
        await interaction.response.send_message("🗑️ **Scrubbing Archive:** Processing penalty and closing...", ephemeral=True)
        
        rep_cog = interaction.client.get_cog("ReputationSystem")
        thread_creator_name = interaction.channel.name.split("-")[-1]
        penalty_amount = 5
        
        if rep_cog:
            guild_id = interaction.guild.id
            penalty_amount = rep_cog.get_rep_setting(guild_id, "ticket_spam_penalty") or 5
            
            target_member = discord.utils.get(interaction.guild.members, name=thread_creator_name)
            if target_member:
                await rep_cog.apply_admin_penalty(guild_id, target_member.id, penalty_amount, target_member)
        
        log_chan_id = interaction.client.get_config(interaction.guild.id, 'log_channel_id')
        if log_chan_id and str(log_chan_id).strip().isdigit():
            log_chan = interaction.guild.get_channel(int(log_chan_id))
            if log_chan:
                try:
                    await log_chan.send(f"⚠️ **Ticket Spam Neutralized:** Staff member {interaction.user.mention} forcibly deleted an invalid support ticket created by `{thread_creator_name}`. They were penalized **`-{penalty_amount} Rep`**.")
                except Exception: pass
                
        await asyncio.sleep(1)
        try:
            await interaction.channel.delete()
        except discord.Forbidden:
            pass

# -------------------------------------------------------------
# CORE LOGIC EXTENSION COG
# -------------------------------------------------------------
class MatchingSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
         
        self.bot.friends_queue = {}    
        self.bot.active_matches = {}     

        # Route system bindings dynamically onto the main bot client object
        self.bot.db_add_to_friends_queue = self.db_add_to_friends_queue
        self.bot.db_remove_from_friends_queue = self.db_remove_from_friends_queue
        self.bot.db_add_active_match = self.db_add_active_match
        self.bot.db_remove_active_match = self.db_remove_active_match
        self.bot.db_update_match_activity = self.db_update_match_activity
        self.bot.purge_user_guild_data = self.purge_user_guild_data

        # Bind View structures back onto the client payload skeleton
        self.bot.MatchRoomControlView = MatchRoomControlView
        self.bot.TicketRoomControlView = TicketRoomControlView

        # Fire background loops
        if not self.inactivity_sweeper.is_running():
            self.inactivity_sweeper.start()

    def cog_unload(self):
        self.inactivity_sweeper.stop()

    # --- Database State Mutation Helpers ---
    def db_add_to_friends_queue(self, guild_id, user_id):
        if guild_id not in self.bot.friends_queue: self.bot.friends_queue[guild_id] = []
        if user_id not in self.bot.friends_queue[guild_id]: self.bot.friends_queue[guild_id].append(user_id)
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO friends_queue (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        conn.commit(); conn.close()

    def db_remove_from_friends_queue(self, guild_id, user_id):
        if guild_id in self.bot.friends_queue and user_id in self.bot.friends_queue[guild_id]: 
            self.bot.friends_queue[guild_id].remove(user_id)
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("DELETE FROM friends_queue WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        conn.commit(); conn.close()

    def db_add_active_match(self, thread_id, u1, u2, match_type):
        last_act = datetime.now(timezone.utc)
        self.bot.active_matches[thread_id] = {"users": [u1, u2], "last_activity": last_act, "type": match_type}
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO active_matches (thread_id, user1_id, user2_id, last_activity, match_type) VALUES (?, ?, ?, ?, ?)",
                       (thread_id, u1, u2, last_act.isoformat(), match_type))
        conn.commit(); conn.close()

    def db_remove_active_match(self, thread_id):
        self.bot.active_matches.pop(thread_id, None)
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("DELETE FROM active_matches WHERE thread_id = ?", (thread_id,))
        conn.commit(); conn.close()

    def db_update_match_activity(self, thread_id):
        if thread_id in self.bot.active_matches:
            last_act = datetime.now(timezone.utc)
            self.bot.active_matches[thread_id]["last_activity"] = last_act
            conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
            cursor.execute("UPDATE active_matches SET last_activity = ? WHERE thread_id = ?", (last_act.isoformat(), thread_id))
            conn.commit(); conn.close()

    def purge_user_guild_data(self, guild_id, user_id):
        """Only deletes local server progression when they leave a specific server."""
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("DELETE FROM friends_queue WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        cursor.execute("DELETE FROM chat_streaks WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        conn.commit(); conn.close()

    # -------------------------------------------------------------
    # TIMED CLEANUP RUNTIMES
    # -------------------------------------------------------------
    @tasks.loop(minutes=5)
    async def inactivity_sweeper(self):
        """Automatically scans matching threads for dead air and drops them."""
        if not self.bot.active_matches: return
        now = datetime.now(timezone.utc)
        
        warning_limit = timedelta(minutes=25)
        stagnation_limit = timedelta(minutes=30)
        
        dead_thread_ids = []
        warning_thread_ids = []
        
        for thread_id, match_data in self.bot.active_matches.items():
            last_act = match_data["last_activity"]
            
            if isinstance(last_act, str):
                try:
                    last_act = datetime.fromisoformat(last_act)
                    self.bot.active_matches[thread_id]["last_activity"] = last_act
                except ValueError:
                    continue 

            time_inactive = now - last_act
            
            if time_inactive > stagnation_limit:
                dead_thread_ids.append(thread_id)
            elif time_inactive > warning_limit and not match_data.get("warned", False):
                warning_thread_ids.append(thread_id)
                match_data["warned"] = True 

        for thread_id in warning_thread_ids:
            try:
                thread_obj = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                if thread_obj:
                    await thread_obj.send("⚠️ **Inactivity Warning:** This room has been quiet for a while. It will automatically close in **5 minutes** if no new messages are sent.")
            except discord.NotFound:
                self.db_remove_active_match(thread_id) 
            except discord.Forbidden:
                pass
            except Exception as e: 
                print(f"Sweeper warning loop err: {e}")

        for thread_id in dead_thread_ids:
            self.db_remove_active_match(thread_id) 
            try:
                thread_obj = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                if thread_obj:
                    await thread_obj.send("⏰ **Room Closed Due to Inactivity:** Session dropped due to 30+ minutes of silence.")
                    await asyncio.sleep(5)
                    await thread_obj.delete()
            except discord.NotFound:
                pass 
            except Exception as e: 
                print(f"Sweeper clean loop err: {e}")

async def setup(bot):
    await bot.add_cog(MatchingSystem(bot))