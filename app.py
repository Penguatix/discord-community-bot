import os
import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configure bot intents for message and member access
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Initialize the Discord bot client
bot = commands.Bot(command_prefix="/", intents=intents)

# Database file location
DB_FILE = "profile.db"

def init_db():
    """Initializes all necessary SQLite database tables for the bot."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create utility timer and queue tables
    cursor.execute('CREATE TABLE IF NOT EXISTS bump_timer (guild_id INTEGER PRIMARY KEY, bump_time TEXT, channel_id INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS friends_queue (guild_id INTEGER, user_id INTEGER, PRIMARY KEY (guild_id, user_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS active_matches (thread_id INTEGER PRIMARY KEY, user1_id INTEGER, user2_id INTEGER, last_activity TEXT, match_type TEXT)')
    
    # Create user chat streak tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_streaks (
            guild_id INTEGER DEFAULT 0, user_id INTEGER, current_streak INTEGER DEFAULT 0, last_chat_date TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
    ''')
    
    # Create global server configuration table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY, verify_role_id TEXT, unverified_role_id TEXT, support_role_id TEXT,
            general_channel_id TEXT, verify_channel_id TEXT, log_channel_id TEXT, bump_role_id TEXT,
            streak_3_role_id TEXT, streak_7_role_id TEXT, streak_30_role_id TEXT, dead_chat_role_id TEXT, vc_ping_role_id TEXT
        )
    ''')
    
    # Create feature toggle state table
    cursor.execute('CREATE TABLE IF NOT EXISTS guild_features (guild_id INTEGER PRIMARY KEY, reputation_enabled INTEGER DEFAULT 0, social_enabled INTEGER DEFAULT 1)')
    
    conn.commit()
    conn.close()

def get_config(guild_id: int, key: str):
    """Fetches a specific configuration setting for a guild."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT {key} FROM guild_settings WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
        if row and row[0]: return row[0]
    except sqlite3.OperationalError: pass
    finally: conn.close()
    return None

def is_feature_enabled(guild_id: int, feature_name: str) -> bool:
    """Checks if a specific module is toggled on for a guild."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT {feature_name} FROM guild_features WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
        if row is not None: return bool(row[0])
    except sqlite3.OperationalError: pass
    finally: conn.close()
    
    # Reputation is disabled by default to save resources
    if feature_name == 'reputation_enabled': return False
    return True

# Bind helper functions to the bot instance for global access
bot.get_config = get_config
bot.is_feature_enabled = is_feature_enabled

def load_queues_and_matches():
    """Restores active queues and chat rooms into memory from the database on startup."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Rebuild friends queue
    cursor.execute("SELECT guild_id, user_id FROM friends_queue")
    bot.friends_queue = {}
    for row in cursor.fetchall():
        g_id, u_id = row[0], row[1]
        if g_id not in bot.friends_queue: bot.friends_queue[g_id] = []
        bot.friends_queue[g_id].append(u_id)
        
    # Rebuild active matches dictionary
    cursor.execute("SELECT thread_id, user1_id, user2_id, last_activity, match_type FROM active_matches")
    rows = cursor.fetchall()
    bot.active_matches = {}
    for row in rows:
        bot.active_matches[row[0]] = {"users": [row[1], row[2]], "last_activity": datetime.fromisoformat(row[3]), "type": row[4]}
    
    conn.close()

async def assign_streak_roles(member: discord.Member, streak: int):
    """Assigns or removes streak reward roles based on a member's current streak."""
    guild_id = member.guild.id
    s3_id  = bot.get_config(guild_id, 'streak_3_role_id')
    s7_id  = bot.get_config(guild_id, 'streak_7_role_id')
    s30_id = bot.get_config(guild_id, 'streak_30_role_id')

    role3  = member.guild.get_role(int(s3_id))  if s3_id  and str(s3_id).strip().isdigit()  else None
    role7  = member.guild.get_role(int(s7_id))  if s7_id  and str(s7_id).strip().isdigit()  else None
    role30 = member.guild.get_role(int(s30_id)) if s30_id and str(s30_id).strip().isdigit() else None
    
    add_pool, remove_pool = [], []
    
    # Determine correct role thresholds
    if streak >= 30:
        if role30: add_pool.append(role30)
        if role7: remove_pool.append(role7)
        if role3: remove_pool.append(role3)
    elif streak >= 7:
        if role7: add_pool.append(role7)
        if role30: remove_pool.append(role30)
        if role3: remove_pool.append(role3)
    elif streak >= 3:
        if role3: add_pool.append(role3)
        if role30: remove_pool.append(role30)
        if role7: remove_pool.append(role7)
    else:
        if role3: remove_pool.append(role3)
        if role7: remove_pool.append(role7)
        if role30: remove_pool.append(role30)
        
    # Apply role updates cleanly
    try:
        actual_add = [r for r in add_pool if r and r not in member.roles]
        actual_remove = [r for r in remove_pool if r and r in member.roles]
        if actual_add: await member.add_roles(*actual_add)
        if actual_remove: await member.remove_roles(*actual_remove)
    except Exception as e: 
        print(f"⚠️ Streak Role Update Exception: {e}")

@tasks.loop(minutes=1)
async def bump_reminder_loop():
    """Checks the bump timer and pings the configured role when 2 hours have passed."""
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('SELECT guild_id, bump_time, channel_id FROM bump_timer')
    rows = cursor.fetchall()
    now = datetime.now(timezone.utc)
    
    for row in rows:
        guild_id, bump_time_str, channel_id = row
        bump_time = datetime.fromisoformat(bump_time_str)
        if now >= bump_time + timedelta(hours=2):
            channel = bot.get_channel(channel_id)
            if channel:
                guild = bot.get_guild(guild_id)
                bump_role_id = bot.get_config(guild_id, 'bump_role_id')
                role = guild.get_role(int(bump_role_id)) if bump_role_id and str(bump_role_id).strip().isdigit() else None
                mention = role.mention if role else "@here"
                try: await channel.send(f"⏰ {mention} **The 2-hour cooldown is over!** It's time to type `/bump` again!")
                except Exception: pass
            
            cursor.execute('DELETE FROM bump_timer WHERE guild_id = ?', (guild_id,))
            conn.commit()
    conn.close()

@tasks.loop(hours=2)
async def unverified_ghost_ping_loop():
    """Pings unverified members in the verification channel every two hours."""
    for guild in bot.guilds:
        v_chan_id = bot.get_config(guild.id, 'verify_channel_id')
        u_role_id = bot.get_config(guild.id, 'unverified_role_id')
        if not v_chan_id or not u_role_id: continue
        
        try:
            channel = guild.get_channel(int(v_chan_id))
            if channel:
                role = guild.get_role(int(u_role_id))
                if role:
                    ghost_ping = await channel.send(f"{role.mention} ⚠️ Remember to complete your verification checks to unlock the server!")
                    await ghost_ping.delete()
        except Exception as e: 
            print(f"⚠️ Ghost ping error for {guild.name}: {e}")

@tasks.loop(seconds=15)
async def status_cycler_loop():
    """Rotates the bot's rich presence status."""
    if not hasattr(status_cycler_loop, "index"):
        status_cycler_loop.index = 0

    server_count = len(bot.guilds)
    
    statuses = [
        discord.CustomActivity(name="Monitoring the server 🛡️"),
        discord.Activity(type=discord.ActivityType.playing, name=f"/help | {server_count} servers")
    ]

    current_activity = statuses[status_cycler_loop.index % len(statuses)]
    await bot.change_presence(activity=current_activity)
    status_cycler_loop.index += 1

@bot.event
async def on_member_join(member):
    """Assigns the unverified role to new members upon entry if configured."""
    u_role_id = bot.get_config(member.guild.id, 'unverified_role_id')
    if u_role_id and str(u_role_id).strip().isdigit():
        try:
            role = member.guild.get_role(int(u_role_id))
            if role: await member.add_roles(role)
        except Exception: pass

@bot.event
async def on_message(message):
    if not message.guild: return

    # Disboard bump tracking logic
    if message.author.id == 302050872383242240: 
        if message.embeds:
            for embed in message.embeds:
                if embed.description and "Bump done" in str(embed.description):
                    now_str = datetime.now(timezone.utc).isoformat()
                    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                    cursor.execute('REPLACE INTO bump_timer (guild_id, bump_time, channel_id) VALUES (?, ?, ?)', 
                                   (message.guild.id, now_str, message.channel.id))
                    conn.commit(); conn.close()
                    await message.channel.send("✅ **Bump logged!** I will ping the bumper role here in exactly 2 hours.")
        return 

    if message.author.bot:
        await bot.process_commands(message)
        return

    # Strict verification channel anti-spam filter
    v_chan_id = bot.get_config(message.guild.id, 'verify_channel_id')
    if v_chan_id and message.channel.id == int(v_chan_id):
        if not message.author.guild_permissions.administrator:
            try: 
                await message.delete()  
                invite = await message.channel.create_invite(max_age=86400, max_uses=1, unique=True, reason="Anti-bot gate reload voucher.")
                try: await message.author.send(f"⚠️ **Security Isolation Notice from {message.guild.name}:**\nYou were automatically removed because you typed inside the verification channel.\nPlease use this fresh invite link to join back, and **only click the verification button**: {invite.url}")
                except Exception: pass
                await message.author.kick(reason="Automated anti-bot protection trap.")
            except Exception: pass
            return

    # Streak processing system
    if bot.is_feature_enabled(message.guild.id, 'reputation_enabled'):
        today_str = datetime.now(timezone.utc).date().isoformat()
        yesterday_str = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        user_id = message.author.id
        guild_id = message.guild.id
        
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("SELECT current_streak, last_chat_date FROM chat_streaks WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        streak_row = cursor.fetchone()
        
        if not streak_row:
            cursor.execute("INSERT OR REPLACE INTO chat_streaks (guild_id, user_id, current_streak, last_chat_date) VALUES (?, ?, 1, ?)", (guild_id, user_id, today_str))
            conn.commit()
            await assign_streak_roles(message.author, 1)
        else:
            current_streak, last_chat_date = streak_row
            if last_chat_date == yesterday_str:
                new_streak = current_streak + 1
                cursor.execute("UPDATE chat_streaks SET current_streak = ?, last_chat_date = ? WHERE guild_id = ? AND user_id = ?", (new_streak, today_str, guild_id, user_id))
                conn.commit()
                await assign_streak_roles(message.author, new_streak)
            elif last_chat_date != today_str:
                cursor.execute("UPDATE chat_streaks SET current_streak = 1, last_chat_date = ? WHERE guild_id = ? AND user_id = ?", (today_str, guild_id, user_id))
                conn.commit()
                await assign_streak_roles(message.author, 1)
        conn.close()

    # Track activity for private matchmaking rooms
    if hasattr(bot, 'active_matches') and message.channel.id in bot.active_matches:
        bot.db_update_match_activity(message.channel.id) 
        
    await bot.process_commands(message)

@bot.event
async def on_member_remove(member):
    """Cleans up user data and active threads when they leave the server."""
    if hasattr(bot, "purge_user_guild_data"):
        bot.purge_user_guild_data(member.guild.id, member.id)

    for thread in member.guild.threads:
        if f"ticket-{member.name}" in thread.name or f"closed-{member.name}" in thread.name:
            try: await thread.delete()
            except Exception: pass

@bot.event
async def on_ready():
    """Bot initialization sequence."""
    init_db()
    load_queues_and_matches() 
    
    # Load persistent views so buttons work after reboots
    from admin_panels import VerificationGateView, FriendsHubControlView, SupportHubControlView
    bot.add_view(VerificationGateView())
    bot.add_view(FriendsHubControlView())
    bot.add_view(SupportHubControlView())
    
    bot.add_view(bot.MatchRoomControlView())
    bot.add_view(bot.TicketRoomControlView())
    
    # Start tasks
    if not bump_reminder_loop.is_running(): bump_reminder_loop.start()
    if not unverified_ghost_ping_loop.is_running(): unverified_ghost_ping_loop.start()
    if not status_cycler_loop.is_running(): status_cycler_loop.start()  

    print(f"🚀 Bot Engine Online! Serving {len(bot.guilds)} server(s).")
    print("🔄 Pushing command tree globally...")

    # Clear old guild-specific caches and execute a full global sync
    for guild in bot.guilds:
        try:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        except Exception:
            pass

    try:
        synced = await bot.tree.sync()
        print(f"⚡ Global sync complete: {len(synced)} slash command(s) active universally.")
    except Exception as e:
        print(f"⚠️ Global sync failure: {e}")

async def main():
    async with bot:
        # Load all cogs into the engine
        await bot.load_extension('server_config')
        await bot.load_extension('admin_panels')
        await bot.load_extension('public_commands')
        await bot.load_extension('interaction_commands')
        await bot.load_extension('reputation_system')
        await bot.load_extension('matching_system')
        await bot.load_extension('invite_tracker')
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())