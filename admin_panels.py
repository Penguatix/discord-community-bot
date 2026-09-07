import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import sqlite3

async def process_invite_reward(bot, guild: discord.Guild, verified_member: discord.Member):
    """Processes invitation rewards silently when a user verifies."""
    conn = sqlite3.connect("profile.db", timeout=15)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT inviter_id FROM invite_tracking 
            WHERE guild_id = ? AND invited_id = ? AND rewarded = 0
        """, (guild.id, verified_member.id))
        row = cursor.fetchone()
    except Exception:
        row = None
    finally:
        conn.close() 

    if row:
        inviter_id = row[0]
        reward_amount = 10 

        # Add points using reputation cog if active
        rep_cog = bot.get_cog("ReputationSystem")
        if rep_cog:
            if hasattr(rep_cog, "get_rep_setting"):
                custom_amt = rep_cog.get_rep_setting(guild.id, "invite_reward")
                if custom_amt:
                    reward_amount = custom_amt
            
            new_score, _ = rep_cog._modify_points(guild.id, inviter_id, reward_amount, is_interaction=False, update_chat_date=False)
            inviter_member = guild.get_member(inviter_id)
            if inviter_member:
                await rep_cog._update_rep_roles(inviter_member, new_score)
        else:
            # Fallback direct database injection
            conn2 = sqlite3.connect("profile.db", timeout=15)
            c2 = conn2.cursor()
            c2.execute("""
                INSERT INTO reputation (guild_id, user_id, points)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET points = points + ?
            """, (guild.id, inviter_id, reward_amount, reward_amount))
            conn2.commit()
            conn2.close()

        # Mark as rewarded
        conn3 = sqlite3.connect("profile.db", timeout=15)
        c3 = conn3.cursor()
        c3.execute("UPDATE invite_tracking SET rewarded = 1 WHERE guild_id = ? AND invited_id = ?", (guild.id, verified_member.id))
        conn3.commit()
        conn3.close()

        # Send DM confirmation to the inviter
        inviter = guild.get_member(inviter_id)
        if inviter:
            try:
                embed = discord.Embed(
                    title="🎉 Invite Reward Unlocked!",
                    description=f"Your invite **{verified_member.mention}** completed verification in **{guild.name}**!\n"
                                f"You have been awarded **`+{reward_amount} Rep`**.",
                    color=discord.Color.green()
                )
                await inviter.send(embed=embed)
            except Exception: pass

class CustomRulesModal(discord.ui.Modal):
    """Modal for writing custom server rules."""
    def __init__(self):
        super().__init__(title="Custom Server Rules")
        self.title_input = discord.ui.TextInput(
            label="Rules Title:",
            style=discord.TextStyle.short,
            default="📜 OFFICIAL SERVER RULES",
            max_length=200,
            required=True
        )
        self.rules_text = discord.ui.TextInput(
            label="Enter your server rules:",
            style=discord.TextStyle.paragraph,
            placeholder="1. Be respectful...\n2. No spamming...\n(Use markdown like **bold** for formatting)",
            max_length=3500,
            required=True
        )
        self.add_item(self.title_input)
        self.add_item(self.rules_text)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.title_input.value,
            description=self.rules_text.value,
            color=discord.Color.gold()
        )
        await interaction.response.send_message("✅ Custom rules deployed.", ephemeral=True)
        await interaction.channel.send(embed=embed)

class VerificationGateView(discord.ui.View):
    """Interactive button view for server entry verification."""
    def __init__(self, btn_label: str = "Verify Age & Unlock Server (18+)", btn_emoji: str = "🔞"):
        super().__init__(timeout=None)
        for item in self.children:
            if getattr(item, "custom_id", "") == "gate_verify_btn":
                item.label = btn_label[:80] 
                try: item.emoji = btn_emoji
                except Exception: item.emoji = "✅" 

    @discord.ui.button(label="Verify & Unlock Server", style=discord.ButtonStyle.green, emoji="✅", custom_id="gate_verify_btn")
    async def verify_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        now = datetime.now(timezone.utc)
        
        # Security account age constraint
        if (now - member.created_at) < timedelta(days=7):
            await interaction.followup.send("❌ **Security Alert:** Your account must be at least **7 days old** to verify.", ephemeral=True)
            return
            
        try:
            verify_role_id = interaction.client.get_config(guild.id, 'verify_role_id')
            if not verify_role_id or not str(verify_role_id).strip().isdigit():
                await interaction.followup.send("❌ **Configuration Fault:** Verification role is missing or malformed for this server. Ask an admin to use `/setup set-role`.", ephemeral=True)
                return
                
            role = guild.get_role(int(verify_role_id))
            if not role:
                await interaction.followup.send("❌ **Configuration Fault:** System could not locate the verified role inside the server list.", ephemeral=True)
                return
                
            if role in member.roles:
                await interaction.followup.send("✅ Security Node: Already verified.", ephemeral=True)
                return
                
            await member.add_roles(role)
            
            # Remove unverified role if mapped
            unverify_role_id = interaction.client.get_config(guild.id, 'unverified_role_id')
            if unverify_role_id and str(unverify_role_id).strip().isdigit():
                unrole = guild.get_role(int(unverify_role_id))
                if unrole and unrole in member.roles:
                    try: await member.remove_roles(unrole)
                    except Exception: pass

            await process_invite_reward(interaction.client, guild, member)

            await interaction.followup.send("🎉 **Access Granted!** Channels unlocked!", ephemeral=True)
            
            general_chan_id = interaction.client.get_config(guild.id, 'general_channel_id')
            if general_chan_id and str(general_chan_id).strip().isdigit():
                try:
                    chan = interaction.client.get_channel(int(general_chan_id))
                    if chan: await chan.send(f"👋 Welcome to the server, **{member.name}**!")
                except Exception: pass
                
        except discord.Forbidden:
            await interaction.followup.send("❌ **Hierarchy Error:** The bot cannot manage roles for this user. Move the bot's integration role higher in your Server Settings.", ephemeral=True)
        except Exception as e:
            print(f"❌ Verification Gate Exception Log: {e}")
            await interaction.followup.send(f"❌ **Internal Error:** An unhandled error occurred while applying roles.", ephemeral=True)

class FriendsHubControlView(discord.ui.View):
    """Interactive queue button for platonic matchmaking."""
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Find a Friend", style=discord.ButtonStyle.success, emoji="🤝", custom_id="friends_find_match_btn")
    async def find_friend_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        hub_channel = interaction.channel
        guild_id = guild.id
        
        if guild_id not in interaction.client.friends_queue:
            interaction.client.friends_queue[guild_id] = []

        # Leave queue
        if user.id in interaction.client.friends_queue[guild_id]:
            interaction.client.db_remove_from_friends_queue(guild_id, user.id) 
            await interaction.response.send_message("❌ **Queue Left:** You have removed yourself from the queue.", ephemeral=True)
            return
            
        for m in interaction.client.active_matches.values():
            if user.id in m["users"]:
                await interaction.response.send_message("❌ Room conflict: You currently occupy an active matchmaking thread.", ephemeral=True); return
                
        # Connect match
        if interaction.client.friends_queue[guild_id]:
            partner_id = interaction.client.friends_queue[guild_id][0]
            interaction.client.db_remove_from_friends_queue(guild_id, partner_id) 
            partner = guild.get_member(partner_id)
            
            if not partner:
                await interaction.response.send_message("⚠️ Candidate disconnected from network cache. Re-indexing loop...", ephemeral=True); return
                
            await interaction.response.send_message("🤝 **Pairing Found!** Deploying private chat space...", ephemeral=True)
            
            try:
                friend_thread = await hub_channel.create_thread(name="💬-friend-chat", type=discord.ChannelType.private_thread, invitable=False)
                await friend_thread.add_user(user)
                await friend_thread.add_user(partner)
                
                interaction.client.db_add_active_match(friend_thread.id, user.id, partner_id, "friends") 
                
                await friend_thread.send("✨ **Private Social Thread Online!**")
                await friend_thread.send(f"👋 Welcome **{user.name}** and **{partner.name}**!\n\n**Room Operations:** Use the control dashboard interface below to disconnect or file reports.", view=interaction.client.MatchRoomControlView())
            except Exception as e: print(f"Friend thread error: {e}")
        else:
            interaction.client.db_add_to_friends_queue(guild_id, user.id) 
            await interaction.response.send_message("🕵️ **Queue Entered!** Standing by for the next active user. Press the button again if you want to leave.", ephemeral=True)

class SupportHubControlView(discord.ui.View):
    """Interactive button to spawn 1-on-1 support tickets."""
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Open a Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="support_open_ticket_btn")
    async def open_ticket_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        hub_channel = interaction.channel
        await interaction.response.defer(ephemeral=True)
        try:
            ticket_thread = await hub_channel.create_thread(name=f"🎫┃ticket-{user.name}", type=discord.ChannelType.private_thread, invitable=False)
            await ticket_thread.add_user(user)
            await interaction.followup.send(f"✅ **Ticket Created!** Access link: {ticket_thread.jump_url}", ephemeral=True)
            
            support_role_id = interaction.client.get_config(guild.id, 'support_role_id')
            mention_prefix = ""
            if support_role_id and str(support_role_id).strip().isdigit():
                role = guild.get_role(int(support_role_id))
                if role:
                    mention_prefix = f"{role.mention} "
            
            await ticket_thread.send(
                f"{mention_prefix}🛡️ **Help Desk & Support Hub** 🛡️\n"
                f"Hello **{user.name}**, thank you for reaching out.\n\n"
                f"Please type your suggestions, reports, or questions directly below.\n\n"
                f"⚠️ *Click the button below to lock and save this archive.*", 
                view=interaction.client.TicketRoomControlView()
            )
        except Exception as e: print(f"Ticket open fault: {e}")

class AdminPanels(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    @app_commands.command(name="botstats", description="Admin Only: Shows how many servers and users the engine is currently serving!")
    @commands.has_permissions(administrator=True)
    async def botstats(self, interaction: discord.Interaction):
        """Displays global stats across all connected servers."""
        total_servers = len(interaction.client.guilds)
        total_members = sum(guild.member_count for guild in interaction.client.guilds if guild.member_count)
        
        embed = discord.Embed(
            title="📈 Network Reach",
            description="Here is the current live network data!",
            color=discord.Color.blurple()
        )
        embed.add_field(name="🌍 Total Servers", value=f"**{total_servers:,}** servers", inline=True)
        embed.add_field(name="👥 Total Users", value=f"**{total_members:,}** users", inline=True)
        
        if interaction.client.user.avatar:
            embed.set_thumbnail(url=interaction.client.user.avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="purge", description="Admin Only: Bulk delete a specified chunk of recent messages from this channel.")
    @app_commands.describe(amount="The number of recent messages to permanently delete from chat logs (Max: 100).")
    @commands.has_permissions(administrator=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        """Deletes large batches of messages instantly."""
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ **Validation Error:** Please select a message evaluation scope between **1** and **100** items.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            purged_pool = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(f"🧹 **Scrub Sequence Successful:** Permanently removed **{len(purged_pool)}** messages from the channel history timeline.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ **Access Denied:** The engine does not possess `Manage Messages` integration clearances in this channel role layout.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ **Purge Fault Anomaly:** Execution pipeline dropped with processing code error: `{e}`", ephemeral=True)

    @app_commands.command(name="spawn-rules", description="Admin Only: Deploys a server rules embed panel.")
    @app_commands.describe(mode="Select a rule preset or write your own custom rules.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="🔞 18+ Adult Rules", value="18plus"),
        app_commands.Choice(name="✅ All Ages (SFW) Rules", value="all_ages"),
        app_commands.Choice(name="✍️ Custom Rules", value="custom")
    ])
    @commands.has_permissions(administrator=True)
    async def spawn_rules(self, interaction: discord.Interaction, mode: app_commands.Choice[str] = None):
        """Drops a static embed block for server rules."""
        selected_mode = mode.value if mode else "18plus"
        
        if selected_mode == "custom":
            await interaction.response.send_modal(CustomRulesModal())
            return
            
        await interaction.response.send_message("✅ Server Rules interface deployed.", ephemeral=True)
        
        if selected_mode == "18plus":
            embed = discord.Embed(
                title="🛡️ OFFICIAL RULES (18+) 🛡️",
                description="Welcome to the server. To preserve a safe, mature, and comfortable atmosphere for all members, everyone must strictly respect and follow our code of conduct.",
                color=discord.Color.red()
            )
            embed.add_field(name="1. 🔞 Strict Age Requirement (18+)", value="This server is a dedicated network for adults. Lying about your age, harboring minors, or facilitating access for underage accounts will result in an immediate ban.", inline=False)
            embed.add_field(name="2. 🤝 Toxicity Control & Respect", value="Harassment, hate speech, racism, sexism, or discrimination is strictly prohibited. Keep interactions civil, mature, and constructive.", inline=False)
            embed.add_field(name="3. 🔒 Privacy & Boundaries", value="Do not share anyone's real name, photos, or private details without explicit consent.", inline=False)
            embed.add_field(name="4. 🚫 No Advertisement or Spamming", value="Flooding channels, mass-tagging members, or distributing unauthorized advertisement links is completely banned.", inline=False)
            embed.add_field(name="5. 🛠️ Administrative Discretion", value="Our administration team has ultimate authority over moderation cases.", inline=False)
        else:
            embed = discord.Embed(
                title="📜 OFFICIAL RULES (ALL AGES) 📜",
                description="Welcome to the community! We are a Safe For Work (SFW) and family-friendly server. Please follow these rules to keep the environment safe and fun for everyone.",
                color=discord.Color.green()
            )
            embed.add_field(name="1. 🤝 Be Respectful & Kind", value="Treat everyone with respect. Harassment, bullying, hate speech, or discrimination of any kind is strictly prohibited.", inline=False)
            embed.add_field(name="2. 👨‍👩‍👧‍👦 Keep It SFW (Safe For Work)", value="This is an all-ages environment. Explicit content, NSFW imagery, gore, or highly inappropriate language will result in an immediate ban.", inline=False)
            embed.add_field(name="3. 🔒 Protect Privacy", value="Do not share personal, sensitive, or real-life information about yourself or others.", inline=False)
            embed.add_field(name="4. 🚫 No Spam or Unapproved Ads", value="Do not flood the chat with repeated messages, mass-tag users, or send unapproved promotional links.", inline=False)
            embed.add_field(name="5. 🛠️ Administrative Discretion", value="Moderators reserve the right to remove content or users that disrupt the peace of the community.", inline=False)
            
        await interaction.channel.send(embed=embed)

    @app_commands.command(name="spawn-gate", description="Admin Only: Deploys the entry gate verification panel card.")
    @app_commands.describe(
        mode="Select gate mode: 🔞 18+ Adult Gate or ✅ Standard Member Verification.",
        custom_label="Optional: Custom text for the button (e.g. 'Unlock Channels').",
        custom_emoji="Optional: Custom emoji for the button (e.g. '🔓')."
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="🔞 18+ Adult Verification", value="18plus"),
        app_commands.Choice(name="✅ Standard Member Verification", value="standard")
    ])
    @commands.has_permissions(administrator=True)
    async def spawn_gate(
        self, 
        interaction: discord.Interaction, 
        mode: app_commands.Choice[str] = None, 
        custom_label: str = None, 
        custom_emoji: str = None
    ):
        """Drops the server verification button panel."""
        await interaction.response.defer(ephemeral=True)
        selected_mode = mode.value if mode else "18plus"
        
        if selected_mode == "18plus":
            btn_label = custom_label or "Verify Age & Unlock Server (18+)"
            btn_emoji = custom_emoji or "🔞"
            gate_msg = (
                "🛑 **Welcome to the Server Entry Gateway** 🛑\n\n"
                "This server operates as an explicit 18+ community network. Access requires affirmation status.\n\n"
                "👇 **Click the button below to execute verification checkpoints:**\n"
                "• Automatically checks for account age requirements.\n"
                "• Grants the `Verified` role mapping instantly.\n"
                "• Unlocks full platform viewing clearances.\n\n"
                "⚠️ **CRITICAL SECURITY WARNING:** Do NOT type any text inside this channel. Sending any message here will cause the engine to classify your account as an automated spam bot and you will be instantly **kicked** from the platform. Only click the verification button below."
            )
        else:
            btn_label = custom_label or "Verify Account & Join Server"
            btn_emoji = custom_emoji or "✅"
            gate_msg = (
                "🛡️ **Welcome to the Server Entry Gateway** 🛡️\n\n"
                "To gain full access to the community channels and lounges, please complete verification below.\n\n"
                "👇 **Click the button below to execute verification checkpoints:**\n"
                "• Grants the `Verified` role mapping instantly.\n"
                "• Unlocks full platform viewing clearances.\n\n"
                "⚠️ **CRITICAL SECURITY WARNING:** Do NOT type any text inside this channel. Sending any message here will cause the engine to classify your account as an automated spam bot and you will be instantly **kicked** from the platform. Only click the verification button below."
            )

        try:
            view = VerificationGateView(btn_label=btn_label, btn_emoji=btn_emoji)
            await interaction.channel.send(gate_msg, view=view)
            await interaction.followup.send("✅ Verification Gate interface successfully deployed.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ **Permission Error:** The bot does not have `Send Messages` permission in this channel! Please adjust your channel settings and try again.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ **Discord API Error:** `{e.text}`\n*(If you used a custom emoji, make sure you format it correctly!)*", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ **Internal Code Error:** `{str(e)}`", ephemeral=True)

    @app_commands.command(name="spawn-friends-hub", description="Admin Only: Deploys the platonic friends finder network panel")
    @commands.has_permissions(administrator=True)
    async def spawn_friends_hub(self, interaction: discord.Interaction):
        """Drops the matchmaking queue panel."""
        await interaction.response.send_message("✅ Platonic Friend Hub deployed.", ephemeral=True)
        await interaction.channel.send(
            "🤝 **The Platonic Friend Finder Station** 🤝\n\n"
            "Looking for a gaming partner, hobby enthusiast, or just want to chat with someone new?\n"
            "This space matches users chronologically as they enter the pool.\n\n"
            "👇 **Tap below to find a connection:**\n"
            "• **`Find a Friend`**: Instantly jumps into the live friend queue pool.\n\n"
            "⚠️ *Write-locked channel framework.*",
            view=FriendsHubControlView()
        )

    @app_commands.command(name="spawn-support-hub", description="Admin Only: Deploys the standalone support ticket panel")
    @commands.has_permissions(administrator=True)
    async def spawn_support_hub(self, interaction: discord.Interaction):
        """Drops the ticket generator panel."""
        await interaction.response.send_message("✅ Standalone Support Hub deployed.", ephemeral=True)
        await interaction.channel.send(
            "🛠️ **Help Desk & Support Hub** 🛠️\n\n"
            "Have a server suggestion? Need to file a player report? Missing a premium role trait?\n"
            "Click below to generate a private 1-on-1 assistance workspace thread connected straight to management.\n\n"
            "👇 **Tap below to initialize help channels:**\n"
            "• **`Open a Ticket`**: Instantly deploys a dynamic private ticket thread.\n\n"
            "⚠️ *Write-locked channel framework.*",
            view=SupportHubControlView()
        )

    @app_commands.command(name="invites", description="Admin Only: Check who invited a member and if reputation points were awarded.")
    @app_commands.describe(target="The member you want to look up.")
    @commands.has_permissions(administrator=True)
    async def check_invites(self, interaction: discord.Interaction, target: discord.Member):
        """Queries the database to trace an invite origin."""
        conn = sqlite3.connect("profile.db")
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT inviter_id, rewarded FROM invite_tracking WHERE guild_id = ? AND invited_id = ?", (interaction.guild.id, target.id,))
            row = cursor.fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
            
        if not row:
            await interaction.response.send_message(f"📭 No invite tracking data found for **{target.mention}**. They may have joined before tracking was enabled, or bypassed standard invite links.", ephemeral=True)
            return
            
        inviter_id, rewarded = row
        inviter = interaction.guild.get_member(inviter_id)
        inviter_mention = inviter.mention if inviter else f"User Left Server (`{inviter_id}`)"
        
        status = "✅ Reputation Points Awarded" if rewarded else "⏳ Points Not Awarded Yet (Pending Verification)"
        
        embed = discord.Embed(
            title="🔍 Invite Tracking Record",
            color=discord.Color.blue()
        )
        embed.add_field(name="Target Member", value=target.mention, inline=False)
        embed.add_field(name="Invited By", value=inviter_mention, inline=False)
        embed.add_field(name="Reward Status", value=status, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="force-invite", description="Admin Only: Manually link a joining member to an inviter and grant points.")
    @app_commands.describe(inviter="The member who sent the invite.", invited="The member who joined.")
    @commands.has_permissions(administrator=True)
    async def force_invite(self, interaction: discord.Interaction, inviter: discord.Member, invited: discord.Member):
        """Admin override to manually log an invite transaction."""
        DB_FILE = "profile.db"
        guild_id = interaction.guild.id
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT inviter_id FROM invite_tracking WHERE guild_id = ? AND invited_id = ?", (guild_id, invited.id,))
        if cursor.fetchone():
            conn.close()
            await interaction.response.send_message(f"❌ **{invited.mention}** is already linked to an inviter in the database.", ephemeral=True)
            return
            
        cursor.execute("INSERT INTO invite_tracking (guild_id, invited_id, inviter_id, rewarded) VALUES (?, ?, ?, 1)", (guild_id, invited.id, inviter.id))
        conn.commit()
        conn.close()
        
        rep_cog = interaction.client.get_cog("ReputationSystem")
        if rep_cog:
            invite_reward = rep_cog.get_rep_setting(guild_id, "invite_reward")
            new_score, _ = rep_cog._modify_points(guild_id, inviter.id, invite_reward, is_interaction=False, update_chat_date=False)
            await rep_cog._update_rep_roles(inviter, new_score)
        else:
            invite_reward = 15
        
        embed = discord.Embed(
            title="🔗 Invite Manually Tracked",
            description=f"Successfully linked **{invited.name}** to **{inviter.name}**.\n\n"
                        f"**{inviter.mention}** has been granted **`+{invite_reward} Rep`**.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Revokes reputation points from an inviter if the person they invited leaves."""
        guild_id = member.guild.id
        if not member.guild or not self.bot.is_feature_enabled(guild_id, 'reputation_enabled'): return
        
        DB_FILE = "profile.db"
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT inviter_id, rewarded FROM invite_tracking WHERE guild_id = ? AND invited_id = ?", (guild_id, member.id,))
        row = cursor.fetchone()
        
        if row and row[1] == 1: 
            inviter_id = row[0]
            
            rep_cog = self.bot.get_cog("ReputationSystem")
            if rep_cog:
                invite_reward = rep_cog.get_rep_setting(guild_id, "invite_reward")
                rep_cog._modify_points(guild_id, inviter_id, -invite_reward, is_interaction=False, update_chat_date=False)
                
                inviter = member.guild.get_member(inviter_id)
                if inviter:
                    cursor.execute("SELECT points FROM reputation WHERE guild_id = ? AND user_id = ?", (guild_id, inviter_id))
                    rep_row = cursor.fetchone()
                    if rep_row:
                        await rep_cog._update_rep_roles(inviter, rep_row[0])
                        
            cursor.execute("DELETE FROM invite_tracking WHERE guild_id = ? AND invited_id = ?", (guild_id, member.id,))
            conn.commit()
            
        conn.close()

async def setup(bot): await bot.add_cog(AdminPanels(bot))