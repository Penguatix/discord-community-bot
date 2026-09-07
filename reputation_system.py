import os
import random
import asyncio
import sqlite3
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta

DB_FILE = "profile.db"

# Default Configuration Matrix
DEFAULT_REP_CONFIG = {
    "invite_reward": 15,
    "daily_chat_gain": 1,
    "streak_penalty": 15,
    "streak_3_bonus": 5,
    "streak_7_bonus": 15,
    "streak_30_bonus": 30,
    "warm_cmd_gain": 1,
    "chill_cmd_loss": 2,
    "interaction_burst_cap": 2,      
    "interaction_refresh_mins": 30,  
    "chat_cooldown_mins": 2,         
    "chat_hourly_cap": 10,           
    "chat_msg_min_length": 15,       
    "decay_days_threshold": 3,       
    "decay_amount": 2,               
    "steal_daily_cap": 10,         
    "steal_cooldown_mins": 2,     
    "reaction_penalty_threshold": 3, 
    "reaction_penalty_cooldown_mins": 10, 
    "reaction_penalty_amount": 3,    
    "mod_delete_penalty": 10,        
    "ticket_spam_penalty": 5,        
    "min_points": -100,
    "max_points": 500,
    "threshold_rank_1": 400,
    "threshold_rank_2": 250,
    "threshold_rank_3": 100,
    "threshold_rank_4": 20,
    "threshold_rank_5": 0,
    "threshold_penalty_1": -30,
    "threshold_penalty_2": -70
}

class CarePackageView(discord.ui.View):
    """Button intercept for random mystery care package drops."""
    def __init__(self, cog):
        super().__init__(timeout=15)
        self.cog = cog
        self.claimed_users = []
        self.rewards = [5, 3, 1]
        
    @discord.ui.button(label="Claim Drop!", style=discord.ButtonStyle.success, emoji="🎁")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.claimed_users:
            await interaction.response.send_message("❌ You already secured a supply cache from this drop!", ephemeral=True)
            return
        
        if len(self.claimed_users) >= 3:
            await interaction.response.send_message("❌ The package is already empty!", ephemeral=True)
            return
            
        reward = self.rewards[len(self.claimed_users)]
        self.claimed_users.append(user_id)
        
        new_score, _ = self.cog._modify_points(interaction.guild.id, user_id, reward, is_interaction=False, update_chat_date=False)
        await self.cog._update_rep_roles(interaction.user, new_score)
        
        await interaction.response.send_message(f"🎉 You secured a drop and instantly gained **`+{reward} Rep`**!", ephemeral=True)
        
        if len(self.claimed_users) == 3:
            button.disabled = True
            self.stop()
            try:
                embed = interaction.message.embeds[0]
                embed.title = "🎁 Care Package Emptied!"
                embed.description = "All 3 supplies have been fully claimed!"
                embed.color = discord.Color.dark_grey()
                await interaction.message.edit(embed=embed, view=self)
            except Exception: pass

class ReputationSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.WARM_COMMANDS = [
            "hug", "cuddle", "warm", "smile", "happy", "pat", "feed", "handhold",
            "blowkiss", "kiss", "peck", "thumbsup", "wave", "wink", "teehee", "clap",
            "handshake", "highfive", "poke", "tickle"
        ]
        self.CHILL_COMMANDS = [
            "slap", "bonk", "yeet", "kick", "punch", "bite", "shoot", "tableflip",
            "angry", "pout"
        ]
        
        self.active_frenzies = {}       
        self.frenzy_cooldowns = {}      
        self.last_event_time = {}       
        self.steal_cooldowns = {}    
        self.global_reaction_penalty_cd = {} 

        self.bot.award_invite_points = self.award_invite_points
        self.bot.get_rep_setting = self.get_rep_setting
        
        self._init_rep_db()
        
        if not self.rep_role_syncer_loop.is_running():
            self.rep_role_syncer_loop.start()

    def _init_rep_db(self):
        """Initializes main reputation array tables and tracks generic data columns."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reputation (
                guild_id INTEGER DEFAULT 0, user_id INTEGER, points INTEGER DEFAULT 0,
                last_chat_date TEXT, daily_gain_count INTEGER DEFAULT 0,
                cmd_points_available INTEGER DEFAULT 2, last_cmd_time TEXT,
                chat_points_this_hour INTEGER DEFAULT 0, last_chat_reward_time TEXT,
                current_hour_window TEXT, last_decay_date TEXT,
                steals_attempted_today INTEGER DEFAULT 0, last_steal_date TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invite_tracking (
                guild_id INTEGER DEFAULT 0,
                invited_id INTEGER,
                inviter_id INTEGER,
                rewarded INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, invited_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_rep_config (
                guild_id INTEGER PRIMARY KEY,
                invite_reward INTEGER DEFAULT 15, daily_chat_gain INTEGER DEFAULT 1,
                streak_penalty INTEGER DEFAULT 15, streak_3_bonus INTEGER DEFAULT 5,
                streak_7_bonus INTEGER DEFAULT 15, streak_30_bonus INTEGER DEFAULT 30,
                warm_cmd_gain INTEGER DEFAULT 1, chill_cmd_loss INTEGER DEFAULT 2,
                daily_cmd_cap INTEGER DEFAULT 15, interaction_burst_cap INTEGER DEFAULT 2,
                interaction_refresh_mins INTEGER DEFAULT 30, chat_cooldown_mins INTEGER DEFAULT 2,
                chat_hourly_cap INTEGER DEFAULT 10, chat_msg_min_length INTEGER DEFAULT 15,
                min_points INTEGER DEFAULT -100, max_points INTEGER DEFAULT 500,
                threshold_rank_1 INTEGER DEFAULT 400, threshold_rank_2 INTEGER DEFAULT 250,
                threshold_rank_3 INTEGER DEFAULT 100, threshold_rank_4 INTEGER DEFAULT 20,
                threshold_rank_5 INTEGER DEFAULT 0, threshold_penalty_1 INTEGER DEFAULT -30,
                threshold_penalty_2 INTEGER DEFAULT -70, rep_rank_1_role_id TEXT,
                rep_rank_2_role_id TEXT, rep_rank_3_role_id TEXT, rep_rank_4_role_id TEXT,
                rep_rank_5_role_id TEXT, rep_penalty_1_role_id TEXT, rep_penalty_2_role_id TEXT,
                rep_penalty_3_role_id TEXT, streak_3_role_id TEXT, streak_7_role_id TEXT, streak_30_role_id TEXT,
                decay_days_threshold INTEGER DEFAULT 3, decay_amount INTEGER DEFAULT 2,
                steal_daily_cap INTEGER DEFAULT 3, steal_cooldown_mins INTEGER DEFAULT 5,
                reaction_penalty_threshold INTEGER DEFAULT 3, reaction_penalty_cooldown_mins INTEGER DEFAULT 10,
                reaction_penalty_amount INTEGER DEFAULT 3, mod_delete_penalty INTEGER DEFAULT 10,
                ticket_spam_penalty INTEGER DEFAULT 5
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_rep_setting(self, guild_id: int, key: str):
        """Grabs configuration setting natively from SQLite."""
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT {key} FROM guild_rep_config WHERE guild_id = ?", (guild_id,))
            row = cursor.fetchone()
            if row and row[0] is not None: return row[0]
        except sqlite3.OperationalError: pass
        finally: conn.close()
        
        return DEFAULT_REP_CONFIG.get(key)

    def _set_rep_setting(self, guild_id: int, key: str, value):
        """Secure setting override mechanism."""
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO guild_rep_config (guild_id) VALUES (?)", (guild_id,))
        cursor.execute(f"UPDATE guild_rep_config SET {key} = ? WHERE guild_id = ?", (value, guild_id))
        
        if "streak_" in key:
            cursor.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
            try: cursor.execute(f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?", (str(value), guild_id))
            except sqlite3.OperationalError: pass

        conn.commit(); conn.close()

    async def apply_admin_penalty(self, guild_id: int, user_id: int, amount: int, member: discord.Member = None):
        """Direct mathematical adjustment wrapper for punishment events."""
        new_score, _ = self._modify_points(guild_id, user_id, -abs(amount), is_interaction=False)
        if member: await self._update_rep_roles(member, new_score)

    async def _update_rep_roles(self, member: discord.Member, current_points: int):
        """Audits user points mapping against the rank role hierarchy ladder."""
        if member.bot: return

        unverify_role_id = self.bot.get_config(member.guild.id, 'unverified_role_id')
        has_unverified = False
        if unverify_role_id and str(unverify_role_id).strip().isdigit():
            unrole = member.guild.get_role(int(unverify_role_id))
            if unrole and unrole in member.roles: has_unverified = True

        guild_id = member.guild.id
        t_rank_1 = self.get_rep_setting(guild_id, "threshold_rank_1")
        t_rank_2 = self.get_rep_setting(guild_id, "threshold_rank_2")
        t_rank_3 = self.get_rep_setting(guild_id, "threshold_rank_3")
        t_rank_4 = self.get_rep_setting(guild_id, "threshold_rank_4")
        t_rank_5 = self.get_rep_setting(guild_id, "threshold_rank_5")
        t_pen_1  = self.get_rep_setting(guild_id, "threshold_penalty_1")
        t_pen_2  = self.get_rep_setting(guild_id, "threshold_penalty_2")

        matrix = {
            "rank_1": (self.get_rep_setting(guild_id, "rep_rank_1_role_id"), current_points >= t_rank_1 and not has_unverified),
            "rank_2": (self.get_rep_setting(guild_id, "rep_rank_2_role_id"), t_rank_2 <= current_points < t_rank_1 and not has_unverified),
            "rank_3": (self.get_rep_setting(guild_id, "rep_rank_3_role_id"), t_rank_3 <= current_points < t_rank_2 and not has_unverified),
            "rank_4": (self.get_rep_setting(guild_id, "rep_rank_4_role_id"), t_rank_4 <= current_points < t_rank_3 and not has_unverified),
            "rank_5": (self.get_rep_setting(guild_id, "rep_rank_5_role_id"), t_rank_5 <= current_points < t_rank_4 and not has_unverified),      
            "pen_1":  (self.get_rep_setting(guild_id, "rep_penalty_1_role_id"), t_pen_1 <= current_points < t_rank_5 and not has_unverified),       
            "pen_2":  (self.get_rep_setting(guild_id, "rep_penalty_2_role_id"), t_pen_2 <= current_points < t_pen_1 and not has_unverified),     
            "pen_3":  (self.get_rep_setting(guild_id, "rep_penalty_3_role_id"), current_points < t_pen_2 and not has_unverified)               
        }

        add_pool, remove_pool = [], []
        for key, (role_id, condition) in matrix.items():
            if not role_id or not str(role_id).strip().isdigit(): continue
            try:
                role_obj = member.guild.get_role(int(role_id))
                if role_obj:
                    if condition: add_pool.append(role_obj)
                    else: remove_pool.append(role_obj)
            except (ValueError, TypeError): continue

        try:
            actual_add = [r for r in add_pool if r not in member.roles]
            actual_remove = [r for r in remove_pool if r in member.roles]
            if actual_add: await member.add_roles(*actual_add)
            if actual_remove: await member.remove_roles(*actual_remove)
        except discord.Forbidden: pass

    def _modify_points(self, guild_id: int, user_id: int, amount: int, is_interaction: bool = False, update_chat_date: bool = False) -> tuple[int, bool]:
        """Core math processor for all dynamic point rewards."""
        now = datetime.now(timezone.utc)
        today_str = now.date().isoformat()
        
        min_pts = self.get_rep_setting(guild_id, "min_points")
        max_pts = self.get_rep_setting(guild_id, "max_points")
        burst_cap = self.get_rep_setting(guild_id, "interaction_burst_cap") or 2
        refresh_mins = max(1, self.get_rep_setting(guild_id, "interaction_refresh_mins") or 30)

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT points, last_chat_date, cmd_points_available, last_cmd_time FROM reputation WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            row = cursor.fetchone()
        except sqlite3.OperationalError:
            cursor.execute("SELECT points, last_chat_date FROM reputation WHERE user_id = ?", (user_id,))
            old_row = cursor.fetchone()
            row = (old_row[0], old_row[1], burst_cap, None) if old_row else None

        if not row:
            available = burst_cap - 1 if is_interaction else burst_cap
            last_cmd = now.isoformat()
            new_score = max(min_pts, min(max_pts, amount))
            l_chat = today_str if update_chat_date else None
            
            cursor.execute("INSERT OR REPLACE INTO reputation (guild_id, user_id, points, last_chat_date, cmd_points_available, last_cmd_time) VALUES (?, ?, ?, ?, ?, ?)",
                           (guild_id, user_id, new_score, l_chat, available, last_cmd))
            conn.commit(); conn.close()
            return new_score, True

        points, last_chat_date = row[0], row[1]
        cmd_points_available = row[2] if len(row) > 2 and row[2] is not None else burst_cap
        last_cmd_time = row[3] if len(row) > 3 else None

        if last_cmd_time:
            try:
                last_time = datetime.fromisoformat(last_cmd_time)
                mins_passed = (now - last_time).total_seconds() / 60
                if mins_passed >= refresh_mins:
                    recovered = int(mins_passed // refresh_mins)
                    cmd_points_available = min(burst_cap, cmd_points_available + recovered)
                    
                    if cmd_points_available == burst_cap: last_cmd_time = now.isoformat()
                    else:
                        last_time += timedelta(minutes=recovered * refresh_mins)
                        last_cmd_time = last_time.isoformat()
            except Exception:
                cmd_points_available = burst_cap
                last_cmd_time = now.isoformat()
        else:
            cmd_points_available = burst_cap
            last_cmd_time = now.isoformat()

        if update_chat_date: last_chat_date = today_str

        applied = True
        if is_interaction:
            if cmd_points_available > 0:
                cmd_points_available -= 1
                new_score = max(min_pts, min(max_pts, points + amount))
            else:
                new_score = points
                applied = False
        else:
            new_score = max(min_pts, min(max_pts, points + amount))

        cursor.execute("UPDATE reputation SET points = ?, last_chat_date = ?, cmd_points_available = ?, last_cmd_time = ? WHERE guild_id = ? AND user_id = ?",
                       (new_score, last_chat_date, cmd_points_available, last_cmd_time, guild_id, user_id))
        conn.commit(); conn.close()
        
        return new_score, applied

    def _update_chat_stats(self, guild_id, user_id, chat_pts_hr, last_rew_time, hr_window):
        """Logs chat limits per hour to prevent manual system spam abuse."""
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("UPDATE reputation SET chat_points_this_hour = ?, last_chat_reward_time = ?, current_hour_window = ? WHERE guild_id = ? AND user_id = ?", 
                       (chat_pts_hr, last_rew_time, hr_window, guild_id, user_id))
        conn.commit(); conn.close()

    async def award_invite_points(self, member: discord.Member):
        """Evaluates entry links and rewards valid points securely to inviters."""
        if member.bot: return
        if not self.bot.is_feature_enabled(member.guild.id, 'reputation_enabled'): return

        guild_id = member.guild.id
        invite_reward = self.get_rep_setting(guild_id, "invite_reward")

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("SELECT inviter_id, rewarded FROM invite_tracking WHERE guild_id = ? AND invited_id = ?", (guild_id, member.id))
        row = cursor.fetchone()

        if row:
            inviter_id, rewarded = row
            if not rewarded:
                unverify_role_id = self.bot.get_config(guild_id, 'unverified_role_id')
                inviter_member = member.guild.get_member(inviter_id)

                if unverify_role_id and str(unverify_role_id).strip().isdigit():
                    unrole = member.guild.get_role(int(unverify_role_id))
                    if unrole and unrole in member.roles:
                        conn.close()
                        return

                cursor.execute("UPDATE invite_tracking SET rewarded = 1 WHERE guild_id = ? AND invited_id = ?", (guild_id, member.id))
                conn.commit(); conn.close()

                fresh_score, _ = self._modify_points(guild_id, inviter_id, invite_reward)
                if inviter_member: await self._update_rep_roles(inviter_member, fresh_score)
            else: conn.close()
        else: conn.close()

    # -------------------------------------------------------------
    # 🎭 RANDOM EVENTS & CHAT LOGIC
    # -------------------------------------------------------------
    async def _check_random_events(self, message: discord.Message, guild_id: int, now: datetime):
        """Internal probability check triggering random chat drop sequences."""
        last_event = self.last_event_time.get(guild_id)
        if last_event and (now - last_event).total_seconds() < 1800:
            return  
            
        chance = random.random()
        
        if chance < 0.02:
            self.last_event_time[guild_id] = now
            self.active_frenzies[guild_id] = now + timedelta(seconds=15)
            self.frenzy_cooldowns[guild_id] = {}
            
            embed = discord.Embed(
                title="🔥 CHAT FRENZY! 🔥",
                description="The room suddenly surges with energy! Chatting (15+ chars) for the next **15 seconds** grants **2x Bonus Rep** per message!\n\n*(Anti-Spam active: 4s gap required between messages)*",
                color=discord.Color.red()
            )
            try: await message.channel.send(embed=embed)
            except Exception: pass
            
        elif chance < 0.04:
            self.last_event_time[guild_id] = now
            embed = discord.Embed(
                title="🎁 MYSTERY CARE PACKAGE DROPPED! 🎁",
                description="A supply cache has materialized! Only the **first 3 people** to claim it get bonus reputation points!\n\n🥇 `+5 Rep` | 🥈 `+3 Rep` | 🥉 `+1 Rep`",
                color=discord.Color.green()
            )
            view = CarePackageView(self)
            try: 
                msg = await message.channel.send(embed=embed, view=view)
                await asyncio.sleep(15)
                if not view.is_finished():
                    view.stop()
                    try:
                        embed.title = "📦 Care Package Despawned..."
                        embed.description = "The uncollected supplies have disappeared."
                        embed.color = discord.Color.light_grey()
                        await msg.edit(embed=embed, view=None)
                    except Exception: pass
            except Exception: pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Validates all raw messaging attributes to safely filter reputation scoring routines."""
        if not message.guild or message.author.bot: return
        guild_id = message.guild.id
        user_id = message.author.id
        
        if not self.bot.is_feature_enabled(guild_id, 'reputation_enabled'): return
        
        unverify_role_id = self.bot.get_config(guild_id, 'unverified_role_id')
        if unverify_role_id and str(unverify_role_id).strip().isdigit():
            unrole = message.guild.get_role(int(unverify_role_id))
            if unrole and unrole in message.author.roles: return

        msg_len = len(message.content.strip())
        min_len = self.get_rep_setting(guild_id, "chat_msg_min_length") or 15
        if msg_len < min_len: return 
        
        now = datetime.now(timezone.utc)
        
        frenzy_end = self.active_frenzies.get(guild_id)
        if frenzy_end and now < frenzy_end:
            user_frenzy_last = self.frenzy_cooldowns.setdefault(guild_id, {}).get(user_id)
            if not user_frenzy_last or (now - user_frenzy_last).total_seconds() >= 4:
                self.frenzy_cooldowns[guild_id][user_id] = now
                new_score, _ = self._modify_points(guild_id, user_id, 2, is_interaction=False, update_chat_date=False)
                await self._update_rep_roles(message.author, new_score)
            return 

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        try:
            cursor.execute("SELECT points, last_chat_date, chat_points_this_hour, last_chat_reward_time, current_hour_window FROM reputation WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            rep_row = cursor.fetchone()
        except sqlite3.OperationalError: rep_row = None
            
        today_str = now.date().isoformat()
        yesterday_str = (now.date() - timedelta(days=1)).isoformat()
        
        if not rep_row: points, last_chat_date, chat_pts_hr, last_rew_time, hr_window = 0, None, 0, None, None
        else:
            points = rep_row[0]
            last_chat_date = rep_row[1]
            chat_pts_hr = rep_row[2] if len(rep_row) > 2 and rep_row[2] is not None else 0
            last_rew_time = rep_row[3] if len(rep_row) > 3 else None
            hr_window = rep_row[4] if len(rep_row) > 4 else None
            
        if hr_window:
            try:
                hr_time = datetime.fromisoformat(hr_window)
                if now > hr_time + timedelta(hours=1):
                    chat_pts_hr = 0
                    hr_window = now.isoformat()
            except ValueError:
                chat_pts_hr = 0
                hr_window = now.isoformat()
        else:
            chat_pts_hr = 0
            hr_window = now.isoformat()
            
        hourly_cap = self.get_rep_setting(guild_id, "chat_hourly_cap") or 10
        cooldown_mins = self.get_rep_setting(guild_id, "chat_cooldown_mins") or 2
        
        can_earn_chat_rep = False
        if chat_pts_hr < hourly_cap:
            if not last_rew_time: can_earn_chat_rep = True
            else:
                try:
                    last_time = datetime.fromisoformat(last_rew_time)
                    if now >= last_time + timedelta(minutes=cooldown_mins): can_earn_chat_rep = True
                except ValueError: can_earn_chat_rep = True
                    
        is_first_msg_today = (last_chat_date != today_str)
        
        if not can_earn_chat_rep and not is_first_msg_today:
            cursor.close(); conn.close()
            await self._check_random_events(message, guild_id, now)
            return
            
        base_gain = 0
        penalty_applied = False
        bonus_applied = 0
        
        if is_first_msg_today:
            base_gain += self.get_rep_setting(guild_id, "daily_chat_gain")
            streak_penalty = self.get_rep_setting(guild_id, "streak_penalty")
            
            if last_chat_date != yesterday_str and last_chat_date is not None:
                base_gain -= streak_penalty
                penalty_applied = True
            else:
                cursor.execute("SELECT current_streak, last_chat_date FROM chat_streaks WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
                s_row = cursor.fetchone()
                curr_streak = s_row[0] if s_row else 0
                new_streak = curr_streak + 1
                
                s3_bonus = self.get_rep_setting(guild_id, "streak_3_bonus")
                s7_bonus = self.get_rep_setting(guild_id, "streak_7_bonus")
                s30_bonus = self.get_rep_setting(guild_id, "streak_30_bonus")
                
                if new_streak == 3: base_gain += s3_bonus; bonus_applied = s3_bonus
                elif new_streak == 7: base_gain += s7_bonus; bonus_applied = s7_bonus
                elif new_streak == 30: base_gain += s30_bonus; bonus_applied = s30_bonus
                
            last_chat_date = today_str
            
        if can_earn_chat_rep:
            base_gain += 1
            chat_pts_hr += 1
            last_rew_time = now.isoformat()
            
        cursor.close(); conn.close()
        
        if base_gain != 0:
            self._update_chat_stats(guild_id, user_id, chat_pts_hr, last_rew_time, hr_window)
            new_score, _ = self._modify_points(guild_id, user_id, base_gain, update_chat_date=is_first_msg_today)
            await self._update_rep_roles(message.author, new_score)
            
            try:
                if penalty_applied:
                    embed = discord.Embed(title="🚨 Inactivity Penalty", description=f"**{message.author.name}** broke their consecutive daily chat streak! **`-{self.get_rep_setting(guild_id, 'streak_penalty')} Reputation Points`**.", color=discord.Color.blue())
                    await message.channel.send(embed=embed, delete_after=12)
                elif bonus_applied > 0:
                    embed = discord.Embed(title="🎉 Streak Milestone Bonus", description=f"**{message.author.name}** unlocked a chat streak milestone! Your consistency is rewarded: **`+{bonus_applied} Bonus Rep`**.", color=discord.Color.orange())
                    await message.channel.send(embed=embed, delete_after=12)
            except Exception: pass
            
        await self._check_random_events(message, guild_id, now)

    # -------------------------------------------------------------
    # 🧊 REACTION, MODERATION, & INTERACTION PENALTIES
    # -------------------------------------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Imposes server-configured points losses if enough users down-vote a specific message block."""
        if not payload.guild_id: return
        if not self.bot.is_feature_enabled(payload.guild_id, 'reputation_enabled'): return
        if payload.emoji.name not in ["🚩", "👎"]: return

        guild_id = payload.guild_id
        
        cd_mins = self.get_rep_setting(guild_id, "reaction_penalty_cooldown_mins") or 10
        last_penalty = self.global_reaction_penalty_cd.get(guild_id)
        now = datetime.now(timezone.utc)
        
        if last_penalty and (now - last_penalty).total_seconds() < (cd_mins * 60): return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(payload.channel_id)
        if not channel: return
        try:
            message = await channel.fetch_message(payload.message_id)
            if message.author.bot: return
            
            unique_reactors = set()
            for reaction in message.reactions:
                if reaction.emoji in ["🚩", "👎"]:
                    async for user in reaction.users():
                        if not user.bot and user.id != message.author.id:
                            unique_reactors.add(user.id)
            
            threshold = self.get_rep_setting(guild_id, "reaction_penalty_threshold") or 3
            
            if len(unique_reactors) >= threshold:
                self.global_reaction_penalty_cd[guild_id] = now
                penalty = self.get_rep_setting(guild_id, "reaction_penalty_amount") or 3
                new_score, _ = self._modify_points(guild_id, message.author.id, -penalty, is_interaction=False)
                member = guild.get_member(message.author.id)
                if member: await self._update_rep_roles(member, new_score)
                
                embed = discord.Embed(description=f"🚨 The community voted against {message.author.mention}... **`-{penalty} Rep`**", color=discord.Color.blue())
                await message.reply(embed=embed, delete_after=10)
        except Exception: pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Scans the audit log sequence and drops rep if a message was destroyed by a Moderator."""
        if not message.guild or message.author.bot: return
        guild_id = message.guild.id
        if not self.bot.is_feature_enabled(guild_id, 'reputation_enabled'): return

        await asyncio.sleep(2) 
        now = datetime.now(timezone.utc)
        
        try:
            async for entry in message.guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=3):
                if entry.target and entry.target.id == message.author.id and entry.user.id != message.author.id:
                    if (now - entry.created_at).total_seconds() < 15:
                        penalty = self.get_rep_setting(guild_id, "mod_delete_penalty") or 10
                        new_score, _ = self._modify_points(guild_id, message.author.id, -penalty, is_interaction=False)
                        
                        member = message.guild.get_member(message.author.id)
                        if member: await self._update_rep_roles(member, new_score)
                        
                        warning = await message.channel.send(f"{message.author.mention} ⚠️ Your message was deleted by moderation. You have lost **{penalty} Reputation Points**.")
                        await warning.delete(delay=20)
                        return
        except Exception: pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Deducts interaction limits organically from the main system limits."""
        if interaction.type != discord.InteractionType.application_command or interaction.user.bot: return
        if not interaction.guild: return
        guild_id = interaction.guild.id
        if not self.bot.is_feature_enabled(guild_id, 'reputation_enabled'): return
        
        cmd_name = interaction.command.name
        user_id = interaction.user.id

        target_member = None
        if hasattr(interaction, "data") and "options" in interaction.data:
            for option in interaction.data["options"]:
                if option.get("type") == 6 and "value" in option:
                    target_id = int(option["value"])
                    target_member = interaction.guild.get_member(target_id)
                    break

        if target_member:
            if target_member.id == user_id or target_member.bot: return

        warm_gain = self.get_rep_setting(guild_id, "warm_cmd_gain")
        chill_loss = self.get_rep_setting(guild_id, "chill_cmd_loss")

        change = 0
        if cmd_name in self.WARM_COMMANDS: change = warm_gain
        elif cmd_name in self.CHILL_COMMANDS: change = -chill_loss

        if change != 0:
            new_score, applied = self._modify_points(guild_id, user_id, change, is_interaction=True)
            if applied: await self._update_rep_roles(interaction.user, new_score)

    # -------------------------------------------------------------
    # ⚙️ BACKGROUND LOOPS (FROSTBITE DECAY INCLUDED)
    # -------------------------------------------------------------
    @tasks.loop(hours=1)
    async def rep_role_syncer_loop(self):
        """Actively checks global inactivity thresholds for heavy decay."""
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            if not self.bot.is_feature_enabled(guild.id, 'reputation_enabled'): continue

            conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
            try:
                cursor.execute("SELECT user_id, points, last_chat_date, last_decay_date FROM reputation WHERE guild_id = ?", (guild.id,))
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                conn.close()
                continue

            today_str = datetime.now(timezone.utc).date().isoformat()
            decay_thresh = self.get_rep_setting(guild.id, "decay_days_threshold") or 3
            decay_amt = self.get_rep_setting(guild.id, "decay_amount") or 2

            for row in rows:
                u_id, points, last_chat_date = row[0], row[1], row[2]
                last_decay_date = row[3] if len(row) > 3 else None
                
                if last_chat_date and points > 0:
                    try:
                        days_inactive = (datetime.now(timezone.utc).date() - datetime.fromisoformat(last_chat_date).date()).days
                        if days_inactive >= decay_thresh and last_decay_date != today_str:
                            new_points = max(0, points - decay_amt) 
                            cursor.execute("UPDATE reputation SET points = ?, last_decay_date = ? WHERE guild_id = ? AND user_id = ?", 
                                          (new_points, today_str, guild.id, u_id))
                            
                            member = guild.get_member(u_id)
                            if member: await self._update_rep_roles(member, new_points)
                    except ValueError: pass

            for member in guild.members:
                if member.bot: continue
                cursor.execute("SELECT points FROM reputation WHERE guild_id = ? AND user_id = ?", (guild.id, member.id))
                r = cursor.fetchone()
                points = r[0] if r else 0
                await self._update_rep_roles(member, points)

            conn.commit(); conn.close()

    # -------------------------------------------------------------
    # 🪵 PUBLIC SLASH UTILITIES
    # -------------------------------------------------------------
    @app_commands.command(name="steal", description="Gambling Mini-game: Attempt to steal Rep points. 60% chance to succeed, 40% chance to fail!")
    @app_commands.describe(target="Optional: The member you want to rob. If blank, target is randomized.")
    async def steal_game(self, interaction: discord.Interaction, target: discord.Member = None):
        """Allows users to bet directly against another user's balance map."""
        guild_id = interaction.guild.id
        if not self.bot.is_feature_enabled(guild_id, 'reputation_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Reputation tracking is currently turned off.", ephemeral=True)
            return
            
        user_id = interaction.user.id

        if target is None:
            unverify_role_id = self.bot.get_config(guild_id, 'unverified_role_id')
            unverify_id = int(unverify_role_id) if unverify_role_id and str(unverify_role_id).strip().isdigit() else None

            valid_targets = [
                m for m in interaction.guild.members 
                if not m.bot 
                and m.id != user_id 
                and (not unverify_id or not m.get_role(unverify_id))
            ]
            
            if not valid_targets:
                await interaction.response.send_message("❌ **No Targets Found:** There are no active verified members to steal from!", ephemeral=True)
                return
            target = random.choice(valid_targets)

        now = datetime.now(timezone.utc)
        cd_mins = self.get_rep_setting(guild_id, "steal_cooldown_mins") or 5
        daily_cap = self.get_rep_setting(guild_id, "steal_daily_cap") or 3
        
        last_throw = self.steal_cooldowns.setdefault(guild_id, {}).get(user_id)
        if last_throw and (now - last_throw).total_seconds() < (cd_mins * 60):
            mins_left = int(cd_mins - ((now - last_throw).total_seconds() / 60))
            await interaction.response.send_message(f"⏳ **Cooldown Active:** You are laying low. Wait `{mins_left}m` before trying another heist.", ephemeral=True)
            return

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("SELECT steals_attempted_today, last_steal_date FROM reputation WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = cursor.fetchone()
        
        today_str = now.date().isoformat()
        throws_today = row[0] if row and row[0] is not None else 0
        last_date = row[1] if row and len(row) > 1 else None
        
        if last_date != today_str: throws_today = 0
            
        if throws_today >= daily_cap:
            conn.close()
            await interaction.response.send_message(f"🛑 **Daily Limit Hit:** You have attempted enough heists today! Come back tomorrow.", ephemeral=True)
            return
            
        throws_today += 1
        cursor.execute("UPDATE reputation SET steals_attempted_today = ?, last_steal_date = ? WHERE guild_id = ? AND user_id = ?", (throws_today, today_str, guild_id, user_id))
        conn.commit(); conn.close()
        
        self.steal_cooldowns[guild_id][user_id] = now
        
        if random.random() < 0.60:
            new_s_user, _ = self._modify_points(guild_id, user_id, 2, is_interaction=False)
            new_s_targ, _ = self._modify_points(guild_id, target.id, -2, is_interaction=False)
            await self._update_rep_roles(interaction.user, new_s_user)
            await self._update_rep_roles(target, new_s_targ)
            
            embed = discord.Embed(
                title="💰 HEIST SUCCESSFUL!", 
                description=f"**{interaction.user.name}** successfully stole points from {target.mention}!\n\n"
                            f"**{interaction.user.name}** gained `+2 Rep`\n"
                            f"**{target.name}** lost `-2 Rep`", 
                color=discord.Color.green()
            )
        else:
            new_s_user, _ = self._modify_points(guild_id, user_id, -3, is_interaction=False)
            await self._update_rep_roles(interaction.user, new_s_user)
            
            embed = discord.Embed(
                title="🚨 CAUGHT!", 
                description=f"**{interaction.user.name}** got caught trying to pickpocket {target.mention}!\n\n"
                            f"**{interaction.user.name}** lost `-3 Rep`", 
                color=discord.Color.red()
            )

        await interaction.response.send_message(embed=embed)

    def _get_current_interaction_points(self, guild_id: int, user_id: int) -> tuple[int, int]:
        """Provides a safe read for command limitation bounds."""
        burst_cap = self.get_rep_setting(guild_id, "interaction_burst_cap") or 2
        refresh_mins = max(1, self.get_rep_setting(guild_id, "interaction_refresh_mins") or 30)

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        try: cursor.execute("SELECT cmd_points_available, last_cmd_time FROM reputation WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)); row = cursor.fetchone()
        except sqlite3.OperationalError: row = None
        conn.close()

        if not row: return burst_cap, 0
        
        available = row[0] if row[0] is not None else burst_cap
        last_time_str = row[1] if len(row) > 1 else None

        if last_time_str:
            try:
                last_time = datetime.fromisoformat(last_time_str)
                now = datetime.now(timezone.utc)
                mins_passed = (now - last_time).total_seconds() / 60
                if mins_passed >= refresh_mins:
                    recovered = int(mins_passed // refresh_mins)
                    available = min(burst_cap, available + recovered)
                
                if available < burst_cap:
                    mins_to_next = refresh_mins - (mins_passed % refresh_mins)
                    return available, int(mins_to_next)
            except Exception: pass
        return available, 0

    @app_commands.command(name="rep", description="View your current reputation score and title standing.")
    async def view_rep(self, interaction: discord.Interaction, member: discord.Member = None):
        """Renders out a full status embed for any member directly to screen."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'reputation_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Reputation tracking is currently turned off in this server.", ephemeral=True)
            return
        await interaction.response.defer()

        target = member or interaction.user
        if target.bot:
            await interaction.followup.send("❌ Automated bot accounts do not possess reputation metrics.")
            return

        guild_id = interaction.guild.id if interaction.guild else None
        unverify_role_id = interaction.client.get_config(guild_id, 'unverified_role_id') if guild_id else None
        if unverify_role_id and str(unverify_role_id).strip().isdigit() and interaction.guild:
            unrole = interaction.guild.get_role(int(unverify_role_id))
            if unrole and unrole in target.roles:
                await interaction.followup.send("❌ Unverified members do not possess reputation profiles.")
                return

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        try: cursor.execute("SELECT points FROM reputation WHERE guild_id = ? AND user_id = ?", (guild_id, target.id)); row = cursor.fetchone()
        except sqlite3.OperationalError: cursor.execute("SELECT points FROM reputation WHERE user_id = ?", (target.id,)); row = cursor.fetchone()

        score = row[0] if row else 0

        try:
            cursor.execute("SELECT user_id FROM reputation WHERE guild_id = ? ORDER BY points DESC", (guild_id,))
            all_rankings = [r[0] for r in cursor.fetchall()]
        except sqlite3.OperationalError: all_rankings = []
        conn.close()

        rank_str = f"#{all_rankings.index(target.id) + 1}" if target.id in all_rankings else "Unranked"

        t_rank_1 = self.get_rep_setting(guild_id, "threshold_rank_1") if guild_id else 400
        t_rank_2 = self.get_rep_setting(guild_id, "threshold_rank_2") if guild_id else 250
        t_rank_3 = self.get_rep_setting(guild_id, "threshold_rank_3") if guild_id else 100
        t_rank_4 = self.get_rep_setting(guild_id, "threshold_rank_4") if guild_id else 20
        t_rank_5 = self.get_rep_setting(guild_id, "threshold_rank_5") if guild_id else 0
        t_pen_1  = self.get_rep_setting(guild_id, "threshold_penalty_1") if guild_id else -30
        t_pen_2  = self.get_rep_setting(guild_id, "threshold_penalty_2") if guild_id else -70
        
        burst_cap = self.get_rep_setting(guild_id, "interaction_burst_cap") or 2
        avail, mins_next = self._get_current_interaction_points(guild_id, target.id)
        refresh_text = f" (Refreshes in {mins_next}m)" if avail < burst_cap else ""

        if score >= t_rank_1: title = "🏆 Legendary"
        elif score >= t_rank_2: title = "☀️ Epic"
        elif score >= t_rank_3: title = "🔥 Active"
        elif score >= t_rank_4: title = "👍 Regular"
        elif score >= t_rank_5: title = "🌱 Newcomer"
        elif score >= t_pen_1: title = "⚠️ Warned"
        elif score >= t_pen_2: title = "🛑 Outcast"
        else: title = "⛔ Exiled"

        embed = discord.Embed(
            title=f"⭐ {target.name}'s Rep Profile Dashboard",
            description=f"### Reputation Score: `{score} Points` \n"
                        f"**Server Leaderboard Rank:** `{rank_str}`\n"
                        f"**Current Standing:** **{title}**\n\n"
                        f"**Interaction Points:** `{avail} / {burst_cap}` claimable{refresh_text}",
            color=discord.Color.from_rgb(173, 216, 230)
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="replb", description="View the highest reputation leaders active inside the server.")
    async def leaderboard(self, interaction: discord.Interaction):
        """Extracts the top 10 members and builds a ranking embed."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'reputation_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Reputation tracking is currently turned off in this server.", ephemeral=True)
            return

        await interaction.response.defer()
        
        guild_id = interaction.guild.id
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        try: cursor.execute("SELECT user_id, points FROM reputation WHERE guild_id = ? ORDER BY points DESC", (guild_id,)); rows = cursor.fetchall()
        except sqlite3.OperationalError: rows = []
        conn.close()

        if not rows:
            await interaction.followup.send("📭 Leaderboard records are completely empty for this server.")
            return

        unverify_role_id = interaction.client.get_config(guild_id, 'unverified_role_id')
        embed = discord.Embed(title=f"👑 Server Reputation Leaderboard", color=discord.Color.gold())
        
        count = 1
        for user_id, points in rows:
            if count > 10: break
            member = interaction.guild.get_member(user_id)
            if member and not member.bot:
                if unverify_role_id and str(unverify_role_id).strip().isdigit():
                    unrole = interaction.guild.get_role(int(unverify_role_id))
                    if unrole and unrole in member.roles: continue
                        
                embed.add_field(name=f"{count}. {member.name}", value=f"Score: `{points} XP` ┃ Position Rank: `#{count}`", inline=False)
                count += 1

        if count == 1:
            await interaction.followup.send("📭 No verified human server citizens have points logged yet.")
            return
            
        await interaction.followup.send(embed=embed)

    # -------------------------------------------------------------
    # ⚙️ ADMIN REPUTATION CUSTOMIZATION SLASH COMMANDS
    # -------------------------------------------------------------
    rep_admin = app_commands.Group(name="setup-rep", description="Admin settings to customize reputation values, caps, and milestone roles.")

    @rep_admin.command(name="view", description="Admin Only: View current server reputation settings and milestone thresholds.")
    @commands.has_permissions(administrator=True)
    async def view_rep_config(self, interaction: discord.Interaction):
        """Readout block for configuration parameters currently configured."""
        guild_id = interaction.guild.id
        embed = discord.Embed(title=f"⚙️ Reputation Configuration Dashboard", color=discord.Color.blue())

        embed.add_field(
            name="📊 Dynamic Point Rewards",
            value=f"• **Verified Invite:** `+{self.get_rep_setting(guild_id, 'invite_reward')}`\n"
                  f"• **Warm Actions:** `+{self.get_rep_setting(guild_id, 'warm_cmd_gain')}`\n"
                  f"• **Chill Actions:** `-{self.get_rep_setting(guild_id, 'chill_cmd_loss')}`\n"
                  f"• **Interaction Claim Cap:** `{self.get_rep_setting(guild_id, 'interaction_burst_cap')} pts`\n"
                  f"• **Interaction Refresh:** `1 pt every {self.get_rep_setting(guild_id, 'interaction_refresh_mins')} mins`",
            inline=False
        )
        embed.add_field(
            name="💬 Paced Chat Rewards",
            value=f"• **First Msg of Day:** `+{self.get_rep_setting(guild_id, 'daily_chat_gain')}`\n"
                  f"• **Cooldown Between Points:** `{self.get_rep_setting(guild_id, 'chat_cooldown_mins')} mins`\n"
                  f"• **Hourly Chat Cap:** `{self.get_rep_setting(guild_id, 'chat_hourly_cap')} pts/hour`",
            inline=False
        )
        embed.add_field(
            name="📉 Inactivity & Bad Faith Penalties",
            value=f"• **Streak Break Penalty:** `-{self.get_rep_setting(guild_id, 'streak_penalty')}`\n"
                  f"• **Inactivity Decay:** `-{self.get_rep_setting(guild_id, 'decay_amount')}/day` after `{self.get_rep_setting(guild_id, 'decay_days_threshold')}` silent days\n"
                  f"• **Mod Deletion Penalty:** `-{self.get_rep_setting(guild_id, 'mod_delete_penalty')}`\n"
                  f"• **Invalid Ticket Penalty:** `-{self.get_rep_setting(guild_id, 'ticket_spam_penalty')}`\n"
                  f"• **Reaction Penalty:** `-{self.get_rep_setting(guild_id, 'reaction_penalty_amount')}` if `{self.get_rep_setting(guild_id, 'reaction_penalty_threshold')}` users react 🚩",
            inline=False
        )
        embed.add_field(
            name="⭐ Milestone Streak Bonuses",
            value=f"• **Day 3 Bonus:** `+{self.get_rep_setting(guild_id, 'streak_3_bonus')}` (Role: <@&{self.get_rep_setting(guild_id, 'streak_3_role_id')}>)\n"
                  f"• **Day 7 Bonus:** `+{self.get_rep_setting(guild_id, 'streak_7_bonus')}` (Role: <@&{self.get_rep_setting(guild_id, 'streak_7_role_id')}>)\n"
                  f"• **Day 30 Bonus:** `+{self.get_rep_setting(guild_id, 'streak_30_bonus')}` (Role: <@&{self.get_rep_setting(guild_id, 'streak_30_role_id')}>)",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rep_admin.command(name="points", description="Admin Only: Customize point gain, penalty, interaction limits, and paced chat rewards.")
    @commands.has_permissions(administrator=True)
    async def set_rep_points(
        self, interaction: discord.Interaction, 
        invite_reward: int = None, daily_chat_gain: int = None, streak_penalty: int = None,
        warm_gain: int = None, chill_loss: int = None, interaction_cap: int = None, interaction_refresh: int = None,
        chat_cooldown_mins: int = None, chat_hourly_cap: int = None, chat_min_chars: int = None
    ):
        """Allows tuning specific parameters connected directly to regular user inputs."""
        guild_id = interaction.guild.id; updates = []
        if invite_reward is not None: self._set_rep_setting(guild_id, "invite_reward", invite_reward); updates.append(f"Invite Reward: `{invite_reward}`")
        if daily_chat_gain is not None: self._set_rep_setting(guild_id, "daily_chat_gain", daily_chat_gain); updates.append(f"Daily Chat: `{daily_chat_gain}`")
        if streak_penalty is not None: self._set_rep_setting(guild_id, "streak_penalty", streak_penalty); updates.append(f"Streak Loss: `{streak_penalty}`")
        if warm_gain is not None: self._set_rep_setting(guild_id, "warm_cmd_gain", warm_gain); updates.append(f"Warm Gain: `{warm_gain}`")
        if chill_loss is not None: self._set_rep_setting(guild_id, "chill_cmd_loss", chill_loss); updates.append(f"Chill Loss: `{chill_loss}`")
        if interaction_cap is not None: self._set_rep_setting(guild_id, "interaction_burst_cap", interaction_cap); updates.append(f"Interaction Burst Cap: `{interaction_cap}`")
        if interaction_refresh is not None: self._set_rep_setting(guild_id, "interaction_refresh_mins", interaction_refresh); updates.append(f"Interaction Refresh: `{interaction_refresh} mins`")
        if chat_cooldown_mins is not None: self._set_rep_setting(guild_id, "chat_cooldown_mins", chat_cooldown_mins); updates.append(f"Chat Cooldown: `{chat_cooldown_mins} mins`")
        if chat_hourly_cap is not None: self._set_rep_setting(guild_id, "chat_hourly_cap", chat_hourly_cap); updates.append(f"Chat Hourly Cap: `{chat_hourly_cap}`")
        if chat_min_chars is not None: self._set_rep_setting(guild_id, "chat_msg_min_length", chat_min_chars); updates.append(f"Chat Min Chars: `{chat_min_chars}`")

        if not updates: await interaction.response.send_message("❌ No parameters were changed.", ephemeral=True); return
        await interaction.response.send_message(f"✅ **Reputation Settings Updated:**\n" + "\n".join([f"• {u}" for u in updates]), ephemeral=True)

    @rep_admin.command(name="penalties", description="Admin Only: Customize decay, heist limits, and moderation penalties.")
    @commands.has_permissions(administrator=True)
    async def set_rep_penalties(
        self, interaction: discord.Interaction, 
        decay_days: int = None, decay_amount: int = None,
        steal_cap: int = None, steal_cooldown: int = None,
        react_thresh: int = None, react_cooldown: int = None, react_penalty: int = None,
        mod_delete_penalty: int = None, ticket_penalty: int = None
    ):
        """Allows tuning specific parameters connected directly to moderator inputs and bad behavior."""
        guild_id = interaction.guild.id; updates = []
        if decay_days is not None: self._set_rep_setting(guild_id, "decay_days_threshold", decay_days); updates.append(f"Decay Starts After: `{decay_days} days`")
        if decay_amount is not None: self._set_rep_setting(guild_id, "decay_amount", decay_amount); updates.append(f"Decay Daily Drain: `-{decay_amount}`")
        if steal_cap is not None: self._set_rep_setting(guild_id, "steal_daily_cap", steal_cap); updates.append(f"Steal Cap: `{steal_cap}/day`")
        if steal_cooldown is not None: self._set_rep_setting(guild_id, "steal_cooldown_mins", steal_cooldown); updates.append(f"Steal Cooldown: `{steal_cooldown}m`")
        if react_thresh is not None: self._set_rep_setting(guild_id, "reaction_penalty_threshold", react_thresh); updates.append(f"Reaction Threshold: `{react_thresh}`")
        if react_cooldown is not None: self._set_rep_setting(guild_id, "reaction_penalty_cooldown_mins", react_cooldown); updates.append(f"Reaction Global Cooldown: `{react_cooldown}m`")
        if react_penalty is not None: self._set_rep_setting(guild_id, "reaction_penalty_amount", react_penalty); updates.append(f"Reaction Penalty: `-{react_penalty}`")
        if mod_delete_penalty is not None: self._set_rep_setting(guild_id, "mod_delete_penalty", mod_delete_penalty); updates.append(f"Mod Deletion Penalty: `-{mod_delete_penalty}`")
        if ticket_penalty is not None: self._set_rep_setting(guild_id, "ticket_spam_penalty", ticket_penalty); updates.append(f"Ticket Spam Penalty: `-{ticket_penalty}`")

        if not updates: await interaction.response.send_message("❌ No parameters were changed.", ephemeral=True); return
        await interaction.response.send_message(f"✅ **Penalty Settings Updated:**\n" + "\n".join([f"• {u}" for u in updates]), ephemeral=True)

    @rep_admin.command(name="thresholds", description="Admin Only: Customize rank threshold scores and score bounds.")
    @commands.has_permissions(administrator=True)
    async def set_rep_thresholds(self, interaction: discord.Interaction, min_points: int = None, max_points: int = None, rank_1: int = None, rank_2: int = None, rank_3: int = None, rank_4: int = None, rank_5: int = None, penalty_1: int = None, penalty_2: int = None):
        """Allows direct modifications of limits that handle the core role allocations."""
        guild_id = interaction.guild.id; updates = []
        if min_points is not None: self._set_rep_setting(guild_id, "min_points", min_points); updates.append(f"Min Points: `{min_points}`")
        if max_points is not None: self._set_rep_setting(guild_id, "max_points", max_points); updates.append(f"Max Points: `{max_points}`")
        if rank_1 is not None: self._set_rep_setting(guild_id, "threshold_rank_1", rank_1); updates.append(f"Rank 1: `{rank_1}`")
        if rank_2 is not None: self._set_rep_setting(guild_id, "threshold_rank_2", rank_2); updates.append(f"Rank 2: `{rank_2}`")
        if rank_3 is not None: self._set_rep_setting(guild_id, "threshold_rank_3", rank_3); updates.append(f"Rank 3: `{rank_3}`")
        if rank_4 is not None: self._set_rep_setting(guild_id, "threshold_rank_4", rank_4); updates.append(f"Rank 4: `{rank_4}`")
        if rank_5 is not None: self._set_rep_setting(guild_id, "threshold_rank_5", rank_5); updates.append(f"Rank 5: `{rank_5}`")
        if penalty_1 is not None: self._set_rep_setting(guild_id, "threshold_penalty_1", penalty_1); updates.append(f"Penalty Tier 1: `{penalty_1}`")
        if penalty_2 is not None: self._set_rep_setting(guild_id, "threshold_penalty_2", penalty_2); updates.append(f"Penalty Tier 2: `{penalty_2}`")

        if not updates: await interaction.response.send_message("❌ No parameters were changed.", ephemeral=True); return
        await interaction.response.send_message(f"✅ **Reputation Thresholds Updated:**\n" + "\n".join([f"• {u}" for u in updates]), ephemeral=True)

    @rep_admin.command(name="role", description="Admin Only: Bind a specific milestone rank or streak achievement to a server role.")
    @app_commands.choices(target_role=[
        app_commands.Choice(name="Rank 1 Role (Highest)", value="rep_rank_1_role_id"),
        app_commands.Choice(name="Rank 2 Role", value="rep_rank_2_role_id"),
        app_commands.Choice(name="Rank 3 Role", value="rep_rank_3_role_id"),
        app_commands.Choice(name="Rank 4 Role", value="rep_rank_4_role_id"),
        app_commands.Choice(name="Rank 5 Role", value="rep_rank_5_role_id"),
        app_commands.Choice(name="Penalty 1 Role", value="rep_penalty_1_role_id"),
        app_commands.Choice(name="Penalty 2 Role", value="rep_penalty_2_role_id"),
        app_commands.Choice(name="Penalty 3 Role (Lowest)", value="rep_penalty_3_role_id"),
        app_commands.Choice(name="Day 3 Streak Role", value="streak_3_role_id"),
        app_commands.Choice(name="Day 7 Streak Role", value="streak_7_role_id"),
        app_commands.Choice(name="Day 30 Streak Role", value="streak_30_role_id")
    ])
    @commands.has_permissions(administrator=True)
    async def set_rep_role(self, interaction: discord.Interaction, target_role: app_commands.Choice[str], role: discord.Role):
        """Allows binding specific rank boundaries to live discord roles inside the host server."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        self._set_rep_setting(guild_id, target_role.value, str(role.id))
        await interaction.followup.send(f"✅ **Milestone/Streak Role Mapped:** **{target_role.name}** bound to {role.mention} (`{role.id}`).", ephemeral=True)

    @rep_admin.command(name="recover", description="Admin Only: Manually grant points to a user to recover lost data.")
    @app_commands.describe(target="The member receiving the points.", amount="The number of points to add (use negative to deduct).")
    @commands.has_permissions(administrator=True)
    async def recover_points(self, interaction: discord.Interaction, target: discord.Member, amount: int):
        """Injects direct rep math over specific targets natively."""
        guild_id = interaction.guild.id
        new_score, _ = self._modify_points(guild_id, target.id, amount, is_interaction=False, update_chat_date=False)
        await self._update_rep_roles(target, new_score)
        
        action_word = "Granted" if amount >= 0 else "Deducted"
        sign = "+" if amount >= 0 else ""
        
        embed = discord.Embed(
            title="🛠️ Reputation Data Recovered",
            description=f"Manual adjustment successfully applied for **{target.mention}**.\n\n"
                        f"**Adjustment:** `{sign}{amount} Rep`\n"
                        f"**New Total Score:** `{new_score} Rep`",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ReputationSystem(bot))