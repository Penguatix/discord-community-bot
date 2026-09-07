import os
import json
import random
import sqlite3
import asyncio
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta

# --- PERSISTENT WORDLE VIEWS ---

class WordleJoinView(discord.ui.View):
    """View containing the button for users to join an active Wordle game."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="🎮", custom_id="wordle_join_btn")
    async def join_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge the interaction immediately to prevent timeouts
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        
        # Connect to the local database
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        
        # Verify the game is actually active and fetch configuration
        c.execute("SELECT word, max_chances, end_time FROM wordle_games WHERE guild_id = ?", (guild_id,))
        game = c.fetchone()
        if not game:
            conn.close()
            await interaction.followup.send("❌ This game session has already ended or timed out.", ephemeral=True)
            return
            
        word, max_chances, end_time_str = game
        end_timestamp = int(datetime.fromisoformat(end_time_str).timestamp())
        
        # Check if the user is already participating in this specific game
        c.execute("SELECT thread_id FROM wordle_players WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        if c.fetchone():
            conn.close()
            await interaction.followup.send("❌ You are already participating in this Wordle game!", ephemeral=True)
            return
            
        try:
            # Create a private thread specifically for this user's gameplay
            thread = await interaction.channel.create_thread(
                name=f"Wordle - {interaction.user.name}",
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            await thread.add_user(interaction.user)
            
            # Register the new user into the active game database
            now_str = datetime.now(timezone.utc).isoformat()
            c.execute("INSERT INTO wordle_players (thread_id, guild_id, user_id, guesses, join_time) VALUES (?, ?, ?, ?, ?)",
                      (thread.id, guild_id, user_id, "[]", now_str))
            conn.commit()
            
            # Send the initial game board interface
            embed = discord.Embed(
                title="🟩 🟨 ⬛ WORDLE ⬛ 🟨 🟩",
                description=f"Welcome to Wordle! The host chose a **{len(word)}-letter** word.\n"
                            f"You have **{max_chances}** chances to guess it.\n\n"
                            f"⏳ **Time Remaining:** <t:{end_timestamp}:R>\n\n"
                            f"👇 *Type your guess directly in this thread!*",
                color=discord.Color.blue()
            )
            await thread.send(embed=embed, view=WordleInGameView())
            
            # Update the main public leaderboard message
            cog = interaction.client.get_cog("PublicCommands")
            if cog: await cog.update_wordle_main_message(guild_id)
            
            await interaction.followup.send(f"✅ Joined! Head over to {thread.mention} to play.", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I lack `Create Private Threads` permission in this channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send("❌ **Error:** Failed to initialize your game instance.", ephemeral=True)
        finally:
            conn.close()


class WordleInGameView(discord.ui.View):
    """View containing the button to back out of an active Wordle game."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Leave Game", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="wordle_leave_btn")
    async def leave_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge the interaction immediately to prevent timeouts
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        
        # Mark the user as finished and having left in the database
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        c.execute("UPDATE wordle_players SET finished = 1, has_left = 1 WHERE thread_id = ?", (interaction.channel.id,))
        conn.commit()
        conn.close()
        
        # Delete the private thread to clean up
        try: await interaction.channel.delete()
        except Exception: pass
        
        # Update the main menu leaderboard to reflect their departure
        cog = interaction.client.get_cog("PublicCommands")
        if cog: 
            await cog.update_wordle_main_message(guild_id)
            await cog.check_all_finished(guild_id)


class PublicCommands(commands.Cog):
    """Core cog for handling public utility, social, and game commands."""
    def __init__(self, bot):
        self.bot = bot
        
        # Generic HTTP headers to bypass basic API scraping blocks
        self.headers = {
            "User-Agent": "GenericBot/1.0 (Discord API Application)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

        # Sets to track active game channels and tasks
        self.active_guess_games = set()
        self.wordle_tasks = {}
        
        # Initialize Wordle DB tables and recovery processes on load
        self._init_wordle_db()
        self.bot.loop.create_task(self.restore_active_wordles())

        # External logic maps for public API categories
        self.RATING_MAP = {"casual": "pg", "deep": "pg13", "spicy": "r"}
        
        # Local fallback banks for API downtimes
        self.TRUTHS = {
            "casual": ["What's an embarrassing gaming habit or guilty pleasure show you secretly love? 🎮", "What was your first impression of this server when you joined? 🤔"],
            "deep": ["What is your biggest dealbreaker when looking for a romantic partner or close friend? 🔒", "What is a fear or insecurity you rarely talk about with others? 💭"],
            "spicy": ["What is your biggest romantic turn-on or preference that you don't usually admit? 🔥", "Have you ever had an intense crush on someone inside a Discord server before? 🔞"]
        }
        self.DARES = {
            "casual": ["Send your absolute favorite meme or reaction image into the current channel right now.", "Reveal the current desktop wallpaper or mobile phone background configuration you use."],
            "deep": ["Share a piece of personal advice or wisdom that completely changed how you look at relationships.", "Write a short, heartfelt 3-sentence appreciation message to someone currently active in the chat."],
            "spicy": ["Send a safe, text-based flirtatious pick-up line directed at the person who challenged you or your crush.", "Confess who your current biggest server crush or favorite conversationalist is right now."]
        }
        self.ICEBREAKERS = [
            "What is your absolute favorite way to spend a lazy weekend? ☕",
            "If you could travel anywhere in the world right now, where would you go? ✈️",
            "What's a gaming title you've logged the most hours on this year? 🎮"
        ]
        self.WYR_QUESTIONS = ["Be able to fly or be invisible?", "Live without music or without movies?", "Always speak your mind or never speak again?"]

    async def _fetch_tod_prompt(self, tod_type: str, category: str) -> str:
        """Fetches a Truth or Dare prompt from the public API with automatic local fallback."""
        rating = self.RATING_MAP.get(category, "pg")
        endpoint = f"https://api.truthordarebot.xyz/v1/{tod_type}?rating={rating}"
        timeout = aiohttp.ClientTimeout(total=3)
        
        try:
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                async with session.get(endpoint) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        question = data.get("question")
                        if question: return question
        except Exception as e:
            print(f"⚠️ ToD API Fetch Failed: {e}")

        local_bank = self.TRUTHS if tod_type == "truth" else self.DARES
        return random.choice(local_bank[category])

    async def _fetch_wyr_prompt(self) -> str:
        """Procedurally mashes two random scenarios from a GitHub database to form a Would You Rather dilemma."""
        endpoint = "https://raw.githubusercontent.com/Jabrils/BEST-Would-You-Rather-Game/master/WYR_database.json"
        timeout = aiohttp.ClientTimeout(total=3)
        
        try:
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                async with session.get(endpoint) as resp:
                    if resp.status == 200:
                        text_data = await resp.text()
                        data = json.loads(text_data)
                        if isinstance(data, list) and len(data) >= 2:
                            items = random.sample(data, 2)
                            opt1 = items[0].get("scene", "").strip().rstrip(".")
                            opt2 = items[1].get("scene", "").strip().rstrip(".")
                            if opt1 and opt2:
                                opt2 = opt2[0].lower() + opt2[1:]
                                return f"Would you rather {opt1} or {opt2}?"
        except Exception as e:
            print(f"⚠️ GitHub WYR Procedural Generation Failed: {e}")

        return random.choice(self.WYR_QUESTIONS)

    async def _fetch_icebreaker_prompt(self) -> str:
        """Fetches a random icebreaker question from the API."""
        endpoint = "https://api.truthordarebot.xyz/v1/truth?rating=pg"
        timeout = aiohttp.ClientTimeout(total=3)
        
        try:
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                async with session.get(endpoint) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        question = data.get("question")
                        if question: return question
        except Exception as e:
            print(f"⚠️ Icebreaker API Fetch Failed: {e}")

        return random.choice(self.ICEBREAKERS)

    def _init_wordle_db(self):
        """Initializes the database tables required for the Wordle mini-game."""
        conn = sqlite3.connect("profile.db")
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wordle_games (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER,
                host_id INTEGER,
                word TEXT,
                max_chances INTEGER,
                end_time TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wordle_players (
                thread_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER,
                guesses TEXT,
                finished INTEGER DEFAULT 0,
                time_taken REAL DEFAULT 0.0,
                has_left INTEGER DEFAULT 0,
                join_time TEXT
            )
        ''')
        conn.commit()
        conn.close()

    async def restore_active_wordles(self):
        """Restores countdown timers for any active Wordle games upon bot reboot."""
        await self.bot.wait_until_ready()
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        c.execute("SELECT guild_id, end_time FROM wordle_games")
        games = c.fetchall()
        conn.close()
        
        now = datetime.now(timezone.utc)
        for g_id, end_time_str in games:
            end_time = datetime.fromisoformat(end_time_str)
            sleep_secs = (end_time - now).total_seconds()
            if sleep_secs > 0:
                task = asyncio.create_task(self.wordle_timer_task(g_id, sleep_secs))
                self.wordle_tasks[g_id] = task
            else:
                await self.cleanup_wordle(g_id)

    async def wordle_timer_task(self, guild_id, sleep_secs):
        """Sleeps for the duration of the Wordle game and handles cleanup."""
        await asyncio.sleep(sleep_secs)
        await self.cleanup_wordle(guild_id)

    def evaluate_wordle(self, guess: str, secret: str) -> str:
        """Determines the color matrix (Green, Yellow, Black) for a Wordle guess."""
        result = ['⬛'] * len(secret)
        secret_chars = list(secret)
        guess_chars = list(guess)

        # First pass: Check for exact positional matches (Green)
        for i in range(len(secret)):
            if guess_chars[i] == secret_chars[i]:
                result[i] = '🟩'
                secret_chars[i] = None 
                guess_chars[i] = None

        # Second pass: Check for correct letters in wrong positions (Yellow)
        for i in range(len(secret)):
            if guess_chars[i] is not None and guess_chars[i] in secret_chars:
                result[i] = '🟨'
                secret_chars[secret_chars.index(guess_chars[i])] = None 

        return "".join(result)

    async def update_wordle_main_message(self, guild_id, is_final=False):
        """Updates the main public Wordle leaderboard embed dynamically."""
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        c.execute("SELECT channel_id, message_id, host_id, word, max_chances, end_time FROM wordle_games WHERE guild_id = ?", (guild_id,))
        game = c.fetchone()
        if not game:
            conn.close()
            return
        
        channel_id, message_id, host_id, word, max_chances, end_time_str = game
        
        c.execute("SELECT user_id, guesses, finished, time_taken, has_left FROM wordle_players WHERE guild_id = ?", (guild_id,))
        players = c.fetchall()
        conn.close()
        
        guild = self.bot.get_guild(guild_id)
        if not guild: return
        channel = guild.get_channel(channel_id)
        if not channel: return
        try: msg = await channel.fetch_message(message_id)
        except discord.NotFound: return
            
        winners, losers, in_progress, left = [], [], [], []
        
        # Categorize all players into arrays for the leaderboard formatting
        for p in players:
            u_id, guesses_json, finished, time_taken, has_left = p
            guesses = json.loads(guesses_json) if guesses_json else []
            
            if has_left: 
                left.append(u_id)
            elif not finished: 
                in_progress.append(u_id)
            else:
                is_winner = any(str(g[0]).strip().upper() == str(word).strip().upper() for g in guesses)
                if is_winner:
                    winners.append((u_id, len(guesses), time_taken))
                else:
                    losers.append((u_id, len(guesses)))
                    
        # Sort winners by fewest guesses, then by completion speed
        winners.sort(key=lambda x: (x[1], x[2]))
        
        embed = discord.Embed(
            title="🟩 🟨 ⬛ MULTIPLAYER WORDLE ⬛ 🟨 🟩",
            color=discord.Color.green() if is_final else discord.Color.blurple()
        )
        
        if is_final:
            embed.title = "🟩 WORDLE GAME OVER 🟩"
            embed.description = f"The game has ended! The secret word was: **`{word}`**\n\n"
        else:
            end_time = datetime.fromisoformat(end_time_str)
            timestamp = int(end_time.timestamp())
            embed.description = f"**<@{host_id}>** has started a Wordle game!\n\n"
            embed.description += f"**Word Length:** `{len(word)}` letters\n"
            embed.description += f"**Max Chances:** `{max_chances}`\n"
            embed.description += f"**Ends:** <t:{timestamp}:R>\n\n"
            
        embed.description += f"👥 **Participants:** `{len(players)}`\n\n**🏆 Session Leaderboard:**\n"
        
        # Format the leaderboard output
        if not players: 
            embed.description += "*Waiting for players to join...*"
        else:
            rank = 1
            for w in winners:
                embed.description += f"🥇 **{rank}.** <@{w[0]}> — `{w[1]}` guesses ({w[2]:.1f}s)\n"
                rank += 1
            for l in losers:
                embed.description += f"💀 <@{l[0]}> — *Failed* (`{l[1]}` guesses)\n"
            for u in left:
                embed.description += f"🚪 <@{u}> — *Left the game*\n"
            if not is_final:
                for ip in in_progress:
                    embed.description += f"⏳ <@{ip}> — *In progress...*\n"
                    
        try:
            if is_final: await msg.edit(embed=embed, view=None)
            else: await msg.edit(embed=embed)
        except Exception: pass

    async def cleanup_wordle(self, guild_id):
        """Removes all Wordle thread channels and cleans up the active DB session."""
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        
        c.execute("SELECT * FROM wordle_games WHERE guild_id = ?", (guild_id,))
        if not c.fetchone():
            conn.close()
            return
            
        c.execute("SELECT thread_id FROM wordle_players WHERE guild_id = ? AND finished = 0", (guild_id,))
        unfinished_threads = c.fetchall()
        
        c.execute("UPDATE wordle_players SET finished = 1 WHERE guild_id = ? AND finished = 0", (guild_id,))
        conn.commit()
        
        # Delete any remaining private threads to prevent clutter
        guild = self.bot.get_guild(guild_id)
        if guild:
            for (t_id,) in unfinished_threads:
                try:
                    thread = guild.get_thread(t_id) or await guild.fetch_channel(t_id)
                    await thread.delete()
                except Exception: pass
        
        await self.update_wordle_main_message(guild_id, is_final=True)
        
        c.execute("DELETE FROM wordle_games WHERE guild_id = ?", (guild_id,))
        c.execute("DELETE FROM wordle_players WHERE guild_id = ?", (guild_id,))
        conn.commit()
        conn.close()
        
        if guild_id in self.wordle_tasks:
            self.wordle_tasks[guild_id].cancel()
            del self.wordle_tasks[guild_id]

    async def check_all_finished(self, guild_id):
        """Checks if all players are finished to end the Wordle session early."""
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        c.execute("SELECT count(*) FROM wordle_players WHERE guild_id = ? AND finished = 0", (guild_id,))
        unfinished = c.fetchone()[0]
        c.execute("SELECT count(*) FROM wordle_players WHERE guild_id = ?", (guild_id,))
        total = c.fetchone()[0]
        conn.close()
        
        if total > 0 and unfinished == 0:
            await self.cleanup_wordle(guild_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for user guesses inside their private Wordle threads."""
        # Ignore bots and non-thread messages
        if message.author.bot or not message.guild: return
        if not isinstance(message.channel, discord.Thread): return
        
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        c.execute("SELECT user_id, guild_id, guesses, finished, join_time FROM wordle_players WHERE thread_id = ?", (message.channel.id,))
        player = c.fetchone()
        
        # Validate that the thread belongs to an active player
        if not player:
            conn.close()
            return
            
        user_id, guild_id, guesses_json, finished, join_time_str = player
        
        if finished == 1 or message.author.id != user_id:
            conn.close()
            return
            
        c.execute("SELECT word, max_chances, end_time FROM wordle_games WHERE guild_id = ?", (guild_id,))
        game = c.fetchone()
        if not game:
            conn.close()
            return
            
        word, max_chances, end_time_str = game
        end_timestamp = int(datetime.fromisoformat(end_time_str).timestamp())
        guess = message.content.upper().strip()
        
        # Enforce valid word format
        if not guess.isalpha() or len(guess) != len(word):
            conn.close()
            await message.delete(delay=1)
            warning = await message.channel.send(f"⚠️ **Invalid Guess:** Your word must be exactly **{len(word)} letters** and contain only alphabets!")
            await warning.delete(delay=4)
            return
            
        guesses = json.loads(guesses_json) if guesses_json else []
        color_result = self.evaluate_wordle(guess, word)
        guesses.append([guess, color_result])
        
        won = (guess == word)
        lost = (len(guesses) >= max_chances)
        ended = won or lost
        
        time_taken = 0.0
        if ended:
            join_time = datetime.fromisoformat(join_time_str)
            time_taken = (datetime.now(timezone.utc) - join_time).total_seconds()
            
        # Save the new guess data
        c.execute("UPDATE wordle_players SET guesses = ?, finished = ?, time_taken = ? WHERE thread_id = ?", 
                  (json.dumps(guesses), 1 if ended else 0, time_taken, message.channel.id))
        conn.commit()
        conn.close()
        
        if ended:
            try: await message.channel.delete()
            except Exception: pass
            
            await self.update_wordle_main_message(guild_id)
            await self.check_all_finished(guild_id)
        else:
            # Build and send the updated game board
            board_text = ""
            for g, cr in guesses: board_text += f"`{g}`\n{cr}\n\n"
            
            embed = discord.Embed(
                title="Your Wordle Board", 
                description=board_text + f"⏳ **Time Remaining:** <t:{end_timestamp}:R>", 
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Chances remaining: {max_chances - len(guesses)}")
            await message.channel.send(embed=embed, view=WordleInGameView())

    # -------------------------------------------------------------
    # 📚 COMMAND DIRECTORY
    # -------------------------------------------------------------
    @app_commands.command(name="help", description="Displays a directory of all public commands and games in this server.")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.user.id))
    async def public_help(self, interaction: discord.Interaction):
        """Renders the standard user help directory mapping available features."""
        guild_id = interaction.guild.id if interaction.guild else None
        
        rep_on = interaction.client.is_feature_enabled(guild_id, 'reputation_enabled') if guild_id else True
        social_on = interaction.client.is_feature_enabled(guild_id, 'social_enabled') if guild_id else True

        embed = discord.Embed(
            title="🛠️ Server Command Directory 🛠️",
            description="Here are all active public modules and commands available in this server:",
            color=discord.Color.from_rgb(173, 216, 230)
        )

        utilities = [
            "• `/help` — View this command directory.",
            "• `/ping` — Verify connection speeds & gateway latency.",
            "• `/serverinfo` — Audit live server stats and boost metrics."
        ]
        
        if social_on:
            utilities.append("• `/confess` — Drop an anonymous confession securely into chat.")
            utilities.append("• `/deadchat` — Ping the community role to revive chat.")
            utilities.append("• `/vcping` — Ping the voice role to form a squad lobby.")
            
        embed.add_field(
            name="🛠️ Public Utilities",
            value="\n".join(utilities),
            inline=False
        )
        
        if social_on:
            games = [
                "• `/icebreaker` — Pull a random engaging conversation starter.",
                "• `/wouldyourather` — Poses a Would You Rather dilemma.",
                "• `/tod` — Truth or Dare challenge (Casual, Deep, Spicy).",
                "• `/wordle` — Host a private multiplayer Wordle game (4-6 letters).",
                "• `/guessword` — Host a timed secret word guessing game in chat.",
                "• `/affinity` — Check ship/compatibility score with a member."
            ]
            embed.add_field(
                name="🎮 Social & Games",
                value="\n".join(games),
                inline=False
            )

        if rep_on:
            rep_cmds = [
                "• `/rep` — Inspect your reputation score, leaderboard rank, & title.",
                "• `/replb` — Display the server reputation leaderboard.",
                "• `/streak` — View daily chat check-in streak count.",
                "• `/steal` — Gamble and attempt to steal Rep XP from another user!"
            ]
            embed.add_field(
                name="📊 Activity & Reputation Standings",
                value="\n".join(rep_cmds),
                inline=False
            )

        if social_on:
            embed.add_field(
                name="🎭 Expressive Actions (Standalone)",
                value="`blush`, `bored`, `clap`, `confused`, `cringe`, `cry`, `dance`, `facepalm`, `happy`, "
                      "`laugh`, `lurk`, `nod`, `pout`, `shrug`, `sleep`, "
                      "`smile`, `smug`, `think`, `yawn`\n"
                      "*👉 Triggers an expressive anime GIF card matching your mood.*",
                inline=False
            )
            embed.add_field(
                name="🤝 Interactive Actions (Target @member)",
                value="`baka`, `bite`, `bonk`, `cuddle`, `feed`, `handhold`, `handshake`, "
                      "`highfive`, `hug`, `kick`, `kiss`, `love`, `pat`, `peck`, `poke`, "
                      "`punch`, `run`, `shoot`, `slap`, `stare`, `thumbsup`, `tickle`, "
                      "`warm`, `wave`, `wink`, `yeet`\n"
                      "*👉 Interact directly with another member in chat.*",
                inline=False
            )

        embed.set_footer(text=f"Requested by {interaction.user.name} ┃ Cooldown: 10s")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup-help", description="Admin Only: Displays all setup, configuration, and panel deployment commands.")
    @commands.has_permissions(administrator=True)
    async def setup_help(self, interaction: discord.Interaction):
        """Renders the administrator configuration overview directory."""
        embed = discord.Embed(
            title="🛡️ Admin Setup Directory 🛡️",
            description="Here are all administrative configuration, moderation, and panel deployment commands:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="⚙️ Server Configuration (`/setup`)",
            value="• `/setup set-role` — Bind system roles (Verified, Support, Bump, Deadchat, Voice, etc.).\n"
                  "• `/setup set-channel` — Bind system channels (Welcome, Verification, Logging).\n"
                  "• `/setup toggle-feature` — Enable or disable bot modules (Reputation, Social).",
            inline=False
        )

        embed.add_field(
            name="📊 Reputation & Invite Management (`/setup-rep`)",
            value="• `/setup-rep view` — View current reputation settings and thresholds.\n"
                  "• `/setup-rep points` — Adjust point rewards, interaction limits, & chat pacing.\n"
                  "• `/setup-rep penalties` — Adjust Inactivity decay, steal limits, & mod penalties.\n"
                  "• `/setup-rep thresholds` — Set rank thresholds and min/max score bounds.\n"
                  "• `/setup-rep role` — Bind rank thresholds & streak milestones to server roles.\n"
                  "• `/setup-rep recover` — Manually adjust a member's reputation points.\n"
                  "• `/setup-rep force-invite` — Manually link an invited user to an inviter.",
            inline=False
        )

        mod_tools = [
            "• `/purge` — Bulk delete up to 100 recent messages from the current channel.",
            "• `/invites` — Inspect who invited a member and check their reward status.",
            "• `/botstats` — View live global network metrics (Servers & Users)."
        ]

        embed.add_field(
            name="🧹 Moderation & Utility Tools",
            value="\n".join(mod_tools),
            inline=False
        )

        spawners = [
            "• `/spawn-rules` — Deploys a customizable server rules embed panel.",
            "• `/spawn-gate` — Deploys the 18+ or standard entry verification gate.",
            "• `/spawn-friends-hub` — Deploys the platonic friends finder network panel.",
            "• `/spawn-support-hub` — Deploys the standalone support ticket panel."
        ]

        embed.add_field(
            name="📌 Control Panel Spawners",
            value="\n".join(spawners),
            inline=False
        )

        embed.set_footer(text=f"Admin Guide ┃ Requested by {interaction.user.name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------------------------------
    # 💬 PUBLIC UTILITIES & GAMES
    # -------------------------------------------------------------
    @app_commands.command(name="confess", description="Submit an anonymous confession to the chat.")
    @app_commands.describe(message="The confession you want to share anonymously.")
    @app_commands.checks.cooldown(1, 120.0, key=lambda i: str(i.user.id))
    async def confess(self, interaction: discord.Interaction, message: str):
        """Drops an anonymous embed block securely to chat."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used inside a server channel.", ephemeral=True)
            return

        if not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social features are turned off in this server.", ephemeral=True)
            return

        # Neutralize role or user pings for safety
        clean_message = discord.utils.escape_mentions(message)

        if len(clean_message) > 3000:
            await interaction.response.send_message("❌ Your confession is too long! Please keep it concise.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🤐 Anonymous Confession",
            description=clean_message,
            color=discord.Color.dark_theme()
        )
        embed.set_footer(text="Identity completely hidden.")

        await interaction.response.send_message("✅ Your confession has been safely and anonymously dropped into the chat.", ephemeral=True)
        await interaction.channel.send(embed=embed)

    @app_commands.command(name="affinity", description="Vibe check! Calculate a fun ship/compatibility score with another member.")
    @app_commands.describe(member="Select the server member you want to vibe check.")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.user.id))
    async def affinity(self, interaction: discord.Interaction, member: discord.Member):
        """A fun generator evaluating alignment between two users' rep points."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return

        if not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social & party games are currently turned off in this server.", ephemeral=True)
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message("🎭 **Self-Affinity:** You love yourself 100%! Self-care is perfect.", ephemeral=False)
            return

        conn = sqlite3.connect("profile.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, points FROM reputation WHERE guild_id = ? AND user_id IN (?, ?)", (interaction.guild.id, interaction.user.id, member.id))
        rows = cursor.fetchall()
        conn.close()

        rep_dict = {row[0]: row[1] for row in rows}
        rep1 = rep_dict.get(interaction.user.id, 0)
        rep2 = rep_dict.get(member.id, 0)

        # Mathematical similarity calculation mapping
        diff = abs(rep1 - rep2)
        factor = max(0.0, 1.0 - (diff / 400.0))

        pair_seed = min(interaction.user.id, member.id) + max(interaction.user.id, member.id)
        random.seed(pair_seed)
        
        min_bound = int(50 * factor)
        max_bound = int(40 + (60 * factor))
        score = random.randint(min_bound, max_bound)
        random.seed()

        # Build outcome card
        if score >= 85:
            title = "🔥 PERFECT MATCH! 🔥"
            desc = f"### Compatibility Score: `{score}%` \n\n**{interaction.user.mention}** and **{member.mention}** are highly compatible! Your reputations are closely aligned and you are an unshakeable match."
            color = discord.Color.green()
        elif score >= 40:
            title = "✨ DECENT VIBES ✨"
            desc = f"### Compatibility Score: `{score}%` \n\n**{interaction.user.mention}** and **{member.mention}** have a decent mix, but it definitely needs some work. Your standing differences leave a spark here!"
            color = discord.Color.gold()
        else:
            title = "💀 TOTAL MISMATCH 💀"
            desc = f"### Compatibility Score: `{score}%` \n\n**{interaction.user.mention}** and **{member.mention}** are a terrible match. Your massive reputation gap causes total conflict. Avoid eye contact!"
            color = discord.Color.red()
            
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_footer(text=f"Shipped by {interaction.user.name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="streak", description="Check your or another member's consecutive daily chat activity records.")
    @app_commands.describe(member="Optional: Select another server member to check their activity streak.")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.user.id))
    async def check_streak(self, interaction: discord.Interaction, member: discord.Member = None):
        """Displays database recorded messaging streaks for a target."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'reputation_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Chat tracking is currently turned off in this server.", ephemeral=True)
            return

        target = member or interaction.user

        if target.bot:
            await interaction.response.send_message("❌ **Bot Account:** Automated bot accounts do not track chat streaks.", ephemeral=True)
            return

        conn = sqlite3.connect("profile.db")
        cursor = conn.cursor()
        cursor.execute("SELECT current_streak, last_chat_date FROM chat_streaks WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, target.id))
        row = cursor.fetchone()
        conn.close()
        
        today_str = datetime.now(timezone.utc).date().isoformat()
        yesterday_str = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        
        if not row or (row[1] != today_str and row[1] != yesterday_str):
            score = 0
        else:
            score = row[0]

        is_self = (target.id == interaction.user.id)
        heading_title = "📅 Consecutive Activity Record" if is_self else f"📅 {target.name}'s Activity Record"
        sub_text = "Keep chatting every single day to unlock higher milestone status roles!" if is_self else f"**{target.mention}** is staying active in the chat!"
            
        embed = discord.Embed(
            title=heading_title,
            description=f"### Current Streak: `{score} Days Active` \n\n{sub_text}",
            color=discord.Color.from_rgb(147, 112, 219)
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="deadchat", description="Pings the community notification role to revive the room.")
    @app_commands.checks.cooldown(1, 7200.0, key=lambda i: (i.guild_id))
    async def dead_chat(self, interaction: discord.Interaction):
        """Triggers the 'dead_chat' configured server ping role."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return

        dead_chat_role_id = interaction.client.get_config(interaction.guild.id, 'dead_chat_role_id')
        
        if not dead_chat_role_id or not str(dead_chat_role_id).strip().isdigit():
            await interaction.response.send_message("❌ **Configuration Error:** The Dead Chat role has not been mapped for this server yet. Ask an admin to set it up with `/setup set-role`.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(dead_chat_role_id))
        if not role:
            await interaction.response.send_message("❌ **Role Error:** Could not locate the configured Dead Chat role on this server.", ephemeral=True)
            return

        msg_text = (
            f"{role.mention}\n\n"
            f"🔔 **THE CHAT IS DEAD...** 🔔\n"
            f"The channels have gotten a bit quiet! {interaction.user.mention} is calling everyone back.\n\n"
            f"Come jump into the conversation and revive the chat! ✨"
        )
        await interaction.response.send_message(content=msg_text)

    @app_commands.command(name="vcping", description="Squad up! Pings the voice role to invite members to join a live voice channel lobby.")
    @app_commands.checks.cooldown(1, 7200.0, key=lambda i: (i.guild_id))
    async def vc_ping(self, interaction: discord.Interaction):
        """Triggers the 'vc_ping' configured server role."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used inside a server.", ephemeral=True)
            return

        vc_ping_role_id = interaction.client.get_config(interaction.guild.id, 'vc_ping_role_id')
        
        if not vc_ping_role_id or not str(vc_ping_role_id).strip().isdigit():
            await interaction.response.send_message("❌ **Configuration Error:** The Voice Ping role has not been mapped for this server yet. Ask an admin to set it up with `/setup set-role`.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(vc_ping_role_id))
        if not role:
            await interaction.response.send_message("❌ **Role Error:** Could not locate the configured Voice Channel role on this server.", ephemeral=True)
            return

        msg_text = (
            f"{role.mention}\n\n"
            f"🎧 **VOICE LOBBY FORMING** 🎧\n"
            f"🔊 **{interaction.user.name}** is opening up a squad session or chilling in voice channels!\n\n"
            f"Un-mute your mic and jump right in to join."
        )
        await interaction.response.send_message(content=msg_text)

    @app_commands.command(name="ping", description="Check the application engine's real-time connection latency.")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.user.id))
    async def ping(self, interaction: discord.Interaction):
        """Pulls the gateway connection execution speed in milliseconds."""
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 **Pong!** Gateway communication velocity is sitting at `{latency_ms}ms`.")

    @app_commands.command(name="serverinfo", description="View detailed architectural metadata and stats about this server.")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.user.id))
    async def server_info(self, interaction: discord.Interaction):
        """Provides a statistical overview mapped to the current server API payload."""
        guild = interaction.guild
        created_date = guild.created_at.strftime("%B %d, %Y")
        
        embed = discord.Embed(
            title=f"📊 {guild.name} Server Dashboard",
            color=discord.Color.from_rgb(173, 216, 230),
            timestamp=datetime.now(timezone.utc)
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        embed.add_field(name="👑 Ownership", value=f"{guild.owner.mention if guild.owner else 'Unresolved'}", inline=True)
        embed.add_field(name="📅 Established", value=f"`{created_date}`", inline=True)
        embed.add_field(name="🆔 Snowflake Key", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="👥 Live Citizens", value=f"`{guild.member_count:,}` accounts", inline=True)
        embed.add_field(name="🚀 Boost Progression", value=f"Tier `{guild.premium_tier}` ({guild.premium_subscription_count} Boosts)", inline=True)
        embed.add_field(name="🔒 Guard Clearance", value=f"Level `{guild.verification_level}`", inline=True)
        
        embed.set_footer(text=f"Queried by {interaction.user.name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="icebreaker", description="Start a conversation! Drops a random, engaging icebreaker question.")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.user.id))
    async def icebreaker(self, interaction: discord.Interaction):
        """Fetches and drops a public icebreaker prompt into the main chat."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social & party games are turned off in this server.", ephemeral=True)
            return

        await interaction.response.defer()
        question = await self._fetch_icebreaker_prompt()

        embed = discord.Embed(
            title="💬 ICEBREAKERS 💬",
            description=f"### {question}",
            color=discord.Color.from_rgb(173, 216, 230)
        )
        embed.set_footer(text=f"Sparked by {interaction.user.name}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="wouldyourather", description="Poses a procedurally generated Would You Rather dilemma.")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.user.id))
    async def would_you_rather(self, interaction: discord.Interaction):
        """Provides a game of binary dilemma choices."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social & party games are turned off in this server.", ephemeral=True)
            return

        await interaction.response.defer()
        question = await self._fetch_wyr_prompt()

        embed = discord.Embed(
            title="🤔 WOULD YOU RATHER...",
            description=f"### {question}",
            color=discord.Color.from_rgb(173, 216, 230)
        )
        embed.set_footer(text=f"Presented to {interaction.user.name}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="wordle", description="Host a multiplayer Wordle game! Participants join their own private thread to guess the secret word.")
    @app_commands.describe(word="The secret word (4 to 6 letters). Time limits scale automatically.")
    @app_commands.checks.cooldown(1, 15.0, key=lambda i: (i.guild_id)) 
    async def wordle_game(self, interaction: discord.Interaction, word: str):
        """Initializes a multiplayer Wordle game wrapper linked to local private threads."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social & party games are turned off in this server.", ephemeral=True)
            return

        word = word.strip().upper()

        if not (4 <= len(word) <= 6):
            await interaction.response.send_message("❌ The secret word must be exactly between **4** and **6** letters long.", ephemeral=True)
            return

        if not word.isalpha():
            await interaction.response.send_message("❌ The secret word can only contain standard alphabetical letters.", ephemeral=True)
            return

        time_limit = 120
        if len(word) == 5: time_limit = 240
        elif len(word) == 6: time_limit = 360

        guild_id = interaction.guild.id
        
        conn = sqlite3.connect("profile.db")
        c = conn.cursor()
        c.execute("SELECT * FROM wordle_games WHERE guild_id = ?", (guild_id,))
        if c.fetchone():
            conn.close()
            await interaction.response.send_message("❌ There is already an active Wordle game running in this server! Please wait for it to finish.", ephemeral=True)
            return

        await interaction.response.defer()
        c.execute("DELETE FROM wordle_players WHERE guild_id = ?", (guild_id,))
        
        now = datetime.now(timezone.utc)
        end_time = now + timedelta(seconds=time_limit)
        max_chances = len(word) + 1
        
        c.execute("INSERT INTO wordle_games (guild_id, channel_id, message_id, host_id, word, max_chances, end_time) VALUES (?, ?, 0, ?, ?, ?, ?)",
                  (guild_id, interaction.channel.id, interaction.user.id, word, max_chances, end_time.isoformat()))
        conn.commit()

        embed = discord.Embed(
            title="🟩 🟨 ⬛ MULTIPLAYER WORDLE ⬛ 🟨 🟩",
            description=f"**{interaction.user.mention}** has started a Wordle game!\n\n"
                        f"**Word Length:** `{len(word)}` letters\n"
                        f"**Max Chances:** `{max_chances}`\n"
                        f"**Time Limit:** `{time_limit}s`\n\n"
                        f"👥 **Participants:** `0`\n\n"
                        f"**🏆 Session Leaderboard:**\n*Waiting for players to join...*",
            color=discord.Color.blurple()
        )
        await interaction.followup.send(embed=embed, view=WordleJoinView())
        msg = await interaction.original_response()
        
        c.execute("UPDATE wordle_games SET message_id = ? WHERE guild_id = ?", (msg.id, guild_id))
        conn.commit()
        conn.close()

        task = asyncio.create_task(self.wordle_timer_task(guild_id, time_limit))
        self.wordle_tasks[guild_id] = task

    @app_commands.command(name="guessword", description="Host a classic word guessing game! Set a secret word and a time limit for chat to guess.")
    @app_commands.describe(word="The secret word others need to guess.", time_limit="Time limit in seconds (10 to 300).")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.channel_id))
    async def guess_word(self, interaction: discord.Interaction, word: str, time_limit: int = 60):
        """Initializes a local game where players drop string guesses linearly in chat."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social & party games are turned off in this server.", ephemeral=True)
            return
            
        if interaction.channel_id in self.active_guess_games:
            await interaction.response.send_message("❌ A guessing game is already currently active in this channel! Please wait for it to finish.", ephemeral=True)
            return

        if not (10 <= time_limit <= 300):
            await interaction.response.send_message("❌ The time limit must be set between `10` and `300` seconds.", ephemeral=True)
            return

        if len(word) > 30:
            await interaction.response.send_message("❌ The secret word is too long! Please keep it under 30 characters.", ephemeral=True)
            return

        if not word.replace(" ", "").isalpha():
            await interaction.response.send_message("❌ The secret word can only contain standard letters and spaces.", ephemeral=True)
            return

        self.active_guess_games.add(interaction.channel_id)
        word_chars = list(word)
        revealed_indices = set([i for i, char in enumerate(word_chars) if char == " "])
        letter_count = len(word.replace(" ", ""))
        
        # Build the hidden word display for the hint generator
        def get_display_word():
            display = []
            for i, char in enumerate(word_chars):
                if char == " ": display.append("  ") 
                elif i in revealed_indices: display.append(char.upper())
                else: display.append("_")
            return " ".join(display)

        embed = discord.Embed(
            title="🔤 GUESS THE WORD!",
            description=f"**{interaction.user.mention}** is hosting a secret word guessing game!\n\n"
                        f"**Word:** `{get_display_word()}`\n"
                        f"**Length:** `{letter_count}` letters\n"
                        f"**Time Remaining:** `{time_limit}` seconds\n\n"
                        f"*Start typing your guesses into the chat!*",
            color=discord.Color.from_rgb(173, 216, 230)
        )
        await interaction.response.send_message(embed=embed)
        game_msg = await interaction.original_response()

        async def hint_loop():
            num_hints = max(1, letter_count // 2)
            if num_hints >= letter_count: num_hints = max(0, letter_count - 1)
            if num_hints == 0: return

            interval = time_limit / (num_hints + 1)
            unrevealed = [i for i, c in enumerate(word_chars) if c != " "]

            for _ in range(num_hints):
                await asyncio.sleep(interval)
                if not unrevealed: break
                
                idx = random.choice(unrevealed)
                unrevealed.remove(idx)
                revealed_indices.add(idx)
                
                hint_embed = discord.Embed(
                    title="🔤 GUESS THE WORD! (Hint Dropped 💡)",
                    description=f"**{interaction.user.mention}** is hosting a secret word guessing game!\n\n"
                                f"**Word:** `{get_display_word()}`\n"
                                f"**Length:** `{letter_count}` letters\n"
                                f"**Total Time Given:** `{time_limit}` seconds\n\n"
                                f"*Start typing your guesses into the chat!*",
                    color=discord.Color.gold() 
                )
                try: await game_msg.edit(embed=hint_embed)
                except discord.NotFound: break 
                    
        hint_task = asyncio.create_task(hint_loop())

        def check_guess(m):
            return (m.channel.id == interaction.channel_id and m.author.id != interaction.user.id and m.content.lower().strip() == word.lower().strip())

        try:
            msg = await self.bot.wait_for('message', check=check_guess, timeout=time_limit)
            win_embed = discord.Embed(
                title="🎉 WE HAVE A WINNER!",
                description=f"**{msg.author.mention}** successfully guessed the secret word!\n\nThe word was: **`{word.upper()}`**",
                color=discord.Color.green()
            )
            await interaction.channel.send(embed=win_embed)
            
        except asyncio.TimeoutError:
            lose_embed = discord.Embed(
                title="⏳ TIME'S UP!",
                description=f"Nobody was able to guess the word in time!\n\nThe word was: **`{word.upper()}`**",
                color=discord.Color.red()
            )
            await interaction.channel.send(embed=lose_embed)
            
        finally:
            hint_task.cancel() 
            self.active_guess_games.remove(interaction.channel_id)

    @app_commands.command(name="tod", description="Truth or Dare! Pick a categorized social challenge for yourself or someone else.")
    @app_commands.describe(choice="Select whether you want a Truth question or a Dare task.", category="Select the intensity level context of the prompt description.", member="Optional: Target another user to give them this specific prompt.")
    @app_commands.choices(choice=[app_commands.Choice(name="Truth", value="truth"), app_commands.Choice(name="Dare", value="dare")], category=[app_commands.Choice(name="Casual ☕", value="casual"), app_commands.Choice(name="Deep 🔮", value="deep"), app_commands.Choice(name="Spicy 🔞", value="spicy")])
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.user.id))
    async def truth_or_dare(self, interaction: discord.Interaction, choice: app_commands.Choice[str], category: app_commands.Choice[str], member: discord.Member = None):
        """Builds a classic Truth or Dare response fetched from the API logic."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social & party games are turned off in this server.", ephemeral=True)
            return

        await interaction.response.defer()
        
        choice_val = choice.value if hasattr(choice, 'value') else str(choice)
        category_val = category.value if hasattr(category, 'value') else str(category)

        prompt = await self._fetch_tod_prompt(choice_val, category_val)

        colors = {"casual": discord.Color.green(), "deep": discord.Color.purple(), "spicy": discord.Color.red()}
        embed_color = colors.get(category_val, discord.Color.blue())
        
        choice_display = "TRUTH" if choice_val == "truth" else "DARE"
        category_display_map = {"casual": "CASUAL ☕", "deep": "DEEP 🔮", "spicy": "SPICY 🔞"}
        category_display = category_display_map.get(category_val, category_val.upper())
        
        title_card = f"🎲 {category_display} ┃ {choice_display}"

        category_name_simple = category_val.capitalize()
        choice_name_simple = choice_val.capitalize()

        if member is None or member.id == interaction.user.id:
            msg_content = None
            msg_description = f"**{interaction.user.mention}** stepped up and claimed a **{category_name_simple} {choice_name_simple}** challenge!\n\n### {prompt}"
            footer_note = "Answer honestly or complete the task to clear your turn!"
        else:
            msg_content = member.mention
            msg_description = f"**{interaction.user.mention}** handed a **{category_name_simple} {choice_name_simple}** challenge over to {member.mention}!\n\n### {prompt}"
            footer_note = f"Your move, {member.name}! Respond or complete the task to pass the torch."

        embed = discord.Embed(title=title_card, description=msg_description, color=embed_color)
        embed.set_footer(text=footer_note)
        await interaction.followup.send(content=msg_content, embed=embed)

    @dead_chat.error
    @vc_ping.error
    @ping.error
    @server_info.error
    @icebreaker.error
    @would_you_rather.error
    @wordle_game.error
    @guess_word.error
    @truth_or_dare.error
    @confess.error
    @affinity.error
    @check_streak.error
    @public_help.error  
    @setup_help.error
    async def command_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error interceptor to handle cooldowns gracefully and output debug traces to console."""
        if isinstance(error, app_commands.CommandOnCooldown):
            hours = int(error.retry_after // 3600)
            minutes = int((error.retry_after % 3600) // 60)
            seconds = int(error.retry_after % 60)
            time_left = f"{hours}h {minutes}m" if hours > 0 else (f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s")
            await interaction.response.send_message(f"⏳ **Rate Limit Intercept:** This module is cooling down. Please wait **{time_left}** before utilizing this endpoint execution again.", ephemeral=True)
        else:
            print(f"Public utility cog error: {error}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ **Internal Execution Error:** An unhandled layout exception occurred while executing this command.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ **Internal Execution Error:** Something went wrong while parsing this command sequence.", ephemeral=True)
            except Exception:
                pass

async def setup(bot):
    cog = PublicCommands(bot)
    await bot.add_cog(cog)
    bot.add_view(WordleJoinView())
    bot.add_view(WordleInGameView())