import random
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

class InteractionCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        self.headers = {
            "User-Agent": "GenericBot/1.0 (Discord API Application)"
        }

        # 🌐 PRIMARY API: Waifu.pics
        self.WAIFU_MAP = {
            "bite": "bite", "blush": "blush", "bonk": "bonk", "cringe": "cringe", 
            "cuddle": "cuddle", "dance": "dance", "feed": "nom", "handhold": "handhold", 
            "happy": "happy", "highfive": "highfive", "hug": "hug", "kick": "kick", 
            "kiss": "kiss", "pat": "pat", "poke": "poke", "slap": "slap", "smile": "smile", 
            "smug": "smug", "wave": "wave", "wink": "wink", "yeet": "yeet", "cry": "cry"
        }

        # 🌐 SECONDARY API: Nekos.best
        self.NEKOS_BEST_MAP = {
            "baka": "baka", "bite": "bite", "blush": "blush", "bonk": "bonk", 
            "bored": "bored", "clap": "clap", "cuddle": "cuddle", "dance": "dance", 
            "facepalm": "facepalm", "feed": "feed", "handhold": "handhold", 
            "handshake": "handshake", "happy": "happy", "highfive": "highfive", 
            "hug": "hug", "kick": "kick", "kiss": "kiss", "laugh": "laugh", 
            "lurk": "lurk", "nod": "nod", "pat": "pat", "peck": "peck", "poke": "poke", 
            "pout": "pout", "punch": "punch", "shoot": "shoot", "shrug": "shrug", 
            "slap": "slap", "sleep": "sleep", "smile": "smile", "smug": "smug", 
            "stare": "stare", "think": "think", "thumbsup": "thumbsup", 
            "tickle": "tickle", "wave": "wave", "wink": "wink", "yawn": "yawn", 
            "yeet": "yeet", "cry": "cry"
        }

        # 🌐 TERTIARY API: OtakuGifs
        self.OTAKU_MAP = {
            "baka": "baka", "bite": "bite", "blush": "blush", "bonk": "bonk", 
            "bored": "bored", "clap": "clap", "confused": "confused", "cringe": "cringe", 
            "cuddle": "cuddle", "dance": "dance", "facepalm": "facepalm", "feed": "nom", 
            "handhold": "handhold", "handshake": "handshake", "happy": "happy", 
            "highfive": "highfive", "hug": "hug", "kick": "kick", "kiss": "kiss", 
            "laugh": "laugh", "love": "love", "lurk": "lurk", "nod": "nod", "pat": "pat", 
            "peck": "peck", "poke": "poke", "pout": "pout", "punch": "punch", "run": "run", 
            "shoot": "shoot", "shrug": "shrug", "slap": "slap", "sleep": "sleep", 
            "smile": "smile", "smug": "smirk", "stare": "stare", "think": "think", 
            "thumbsup": "thumbsup", "tickle": "tickle", "wave": "wave", "wink": "wink", 
            "yawn": "yawn", "yeet": "yeet", "cry": "cry"
        }

    async def _fetch_interaction_gif(self, command_name: str) -> str | None:
        """Attempts to fetch a clean anime reaction GIF from 3 different APIs sequentially."""
        timeout = aiohttp.ClientTimeout(total=3)
        
        # 1. Waifu.pics
        w_point = self.WAIFU_MAP.get(command_name)
        if w_point:
            try:
                async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                    async with session.get(f"https://api.waifu.pics/sfw/{w_point}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('url'): return data.get('url')
            except Exception: pass

        # 2. Nekos.best
        n_point = self.NEKOS_BEST_MAP.get(command_name)
        if n_point:
            try:
                async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                    async with session.get(f"https://nekos.best/api/v2/{n_point}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = data.get('results', [])
                            if results and results[0].get('url'): return results[0].get('url')
            except Exception: pass

        # 3. OtakuGifs
        o_point = self.OTAKU_MAP.get(command_name)
        if o_point:
            try:
                async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                    async with session.get(f"https://api.otakugifs.xyz/gif?reaction={o_point}&format=gif") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('url'): return data.get('url')
            except Exception: pass

        # 4. Fallbacks
        fallback_gifs = {
            "baka": ["https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExNmdvbGdxc3lxcndjbnczeXl0c3g0b2ttMGRueDBha2djazlpNWxoeiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/k63gNYkfIxbwY/giphy.gif"],
            "bite": ["https://media.giphy.com/media/Y4z9olnoVl5QI/giphy.gif"],
            "bonk": ["https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExa3J5d2EzNXRpbHFsM3p0ZWszamdnMWN3d2Mxa2JlMng4ZG9kYmY1aiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/30lxTuJueXE7C/giphy.gif"],
            "bored": ["https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExdW1oMWljeG5xcm8yOXFkejFyMGUzY2hieHo1ajNjM3NlM25hdHcxNyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ySdSWIAwD5QRi/giphy.gif"],
            "confused": ["https://media.giphy.com/media/l3q2K5jv8qmXwB16/giphy.gif"],
            "cringe": ["https://media.giphy.com/media/pMePjXUqNNND2/giphy.gif"],
            "cry": ["https://media.giphy.com/media/8YcgVQZYsIzz1g6qZt/giphy.gif"],
            "cuddle": ["https://media.giphy.com/media/QbkL9WuorOlgI/giphy.gif"],
            "dance": ["https://media.giphy.com/media/10hO3rDNqqg2Xe/giphy.gif"],
            "handshake": ["https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExeTU0NGhvOHhzMzk3YnkzbjluemJ1a2VkYjNvd284ZmltOWFsZWx6MSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/d1E2VyhFsxawRbeo/giphy.gif"],
            "happy": ["https://media.giphy.com/media/11s7Ke7jcNxCHS/giphy.gif"],
            "highfive": ["https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExeW8xeXVhaXBxaDVxenR0aGZ4NnFuYThvdnJsODh3ZmNzdWxvZjJ5YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/BFZvBtfvEbmp2ztBnv/giphy.gif"],
            "hug": ["https://media.giphy.com/media/3M4NpbLCTxBqU/giphy.gif"],
            "kick": ["https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExMjIzMWMzYmR1eDh0NG93aG13YWN3a29menU3ZjVtNzFhMjBodDc3aSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/wOly8pa4s4W88/giphy.gif"],
            "kiss": ["https://media.giphy.com/media/G3va31bZ9qZws/giphy.gif"],
            "love": ["https://media.giphy.com/media/xT0BKL21U5nnlW4m6k/giphy.gif"],
            "lurk": ["https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExYTFyaGo1dGh5NWhpanNoajZzbjFkMTU4MHFpc2F5dmdvZDFuNDI2byZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/T2zqVtt8ipCsyGu9kA/giphy.gif"],
            "nod": ["https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExbzltb251azZic3lsYTU3ZjQyemhya3NnMDJ3MnloZXFjMzhibDQ1YiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/zuevk0rZMzK5a/giphy.gif"],
            "pat": ["https://media.giphy.com/media/4HP0ddZnYAvsI/giphy.gif"],
            "peck": ["https://static2.klipy.com/ii/c3a19a0b747a76e98651f2b9a3cca5ff/86/cf/dpWUwbqY.gif"],
            "run": ["https://media.giphy.com/media/3o7ZetIsjtbkgNE1I4/giphy.gif"],
            "shoot": ["https://static2.klipy.com/ii/4493325008d34b7bf8cd6813cd5c1619/c4/b4/BozIUP5U4sLClEmB.gif"],
            "slap": ["https://media.giphy.com/media/Gf3AUz3eBNbTW/giphy.gif"],
            "smug": ["https://static2.klipy.com/ii/d6b0ce929193df3c242ac34b5654d2ce/6d/72/A1knuMlo.gif"],
            "think": ["https://static2.klipy.com/ii/4493325008d34b7bf8cd6813cd5c1619/c2/91/Uer6kwS7RPQ9bNHk8mC.gif"],
            "yeet": ["https://static2.klipy.com/ii/4e7bea9f7a3371424e6c16ebc93252fe/03/f3/JVZdAs1aJ9lQl.gif"]
        }
        
        if command_name in fallback_gifs:
            return random.choice(fallback_gifs[command_name])

        return None

    async def _run_expressive(self, interaction: discord.Interaction, command_name: str, text: str, color: discord.Color):
        """Helper to send expressive commands."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social interaction commands are currently turned off in this server.", ephemeral=True)
            return

        await interaction.response.defer()
        gif_url = await self._fetch_interaction_gif(command_name)
        embed = discord.Embed(description=text, color=color)
        if gif_url: embed.set_image(url=gif_url)
        await interaction.followup.send(embed=embed)

    async def _run_interactive(self, interaction: discord.Interaction, member: discord.Member, command_name: str, text: str, self_text: str, color: discord.Color):
        """Helper to send targeted interactive commands."""
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social interaction commands are currently turned off in this server.", ephemeral=True)
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message(self_text, ephemeral=False)
            return

        await interaction.response.defer()
        gif_url = await self._fetch_interaction_gif(command_name)
        embed = discord.Embed(description=text, color=color)
        if gif_url: embed.set_image(url=gif_url)
        await interaction.followup.send(content=member.mention, embed=embed)

    # -------------------------------------------------------------
    # 🎭 EXPRESSIVE STANDALONE COMMANDS
    # -------------------------------------------------------------
    @app_commands.command(name="blush", description="Expressive: Blush softly.")
    async def blush(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "blush", f"😳 **{interaction.user.name}** blushes softly.", discord.Color.from_rgb(255, 182, 193))

    @app_commands.command(name="bored", description="Expressive: Look around bored.")
    async def bored(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "bored", f"⏳ **{interaction.user.name}** sighs, looking rather bored.", discord.Color.light_grey())

    @app_commands.command(name="confused", description="Expressive: Look around completely lost and confused.")
    async def confused(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "confused", f"😵‍💫 **{interaction.user.name}** looks around, completely lost and confused.", discord.Color.purple())

    @app_commands.command(name="cringe", description="Expressive: Cringe hard.")
    async def cringe(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "cringe", f"😬 **{interaction.user.name}** visibly cringes...", discord.Color.dark_green())

    @app_commands.command(name="cry", description="Expressive: Let out some tears.")
    async def cry(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "cry", f"😭 **{interaction.user.name}** sheds a quiet tear.", discord.Color.blue())

    @app_commands.command(name="clap", description="Expressive: Cheer and clap enthusiastically.")
    async def clap(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "clap", f"👏 **{interaction.user.name}** cheers and claps enthusiastically!", discord.Color.gold())

    @app_commands.command(name="facepalm", description="Expressive: Facepalm at something ridiculous.")
    async def facepalm(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "facepalm", f"🤦 **{interaction.user.name}** facepalms at the sheer ridiculousness.", discord.Color.dark_grey())

    @app_commands.command(name="happy", description="Expressive: Beam with absolute delight.")
    async def happy(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "happy", f"✨ **{interaction.user.name}** beams with absolute delight!", discord.Color.yellow())

    @app_commands.command(name="laugh", description="Expressive: Burst out laughing.")
    async def laugh(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "laugh", f"😂 **{interaction.user.name}** bursts out laughing!", discord.Color.teal())

    @app_commands.command(name="lurk", description="Expressive: Lurk quietly.")
    async def lurk(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "lurk", f"👀 **{interaction.user.name}** peeks out quietly from the shadows...", discord.Color.dark_purple())

    @app_commands.command(name="nod", description="Expressive: Nod your head in firm agreement.")
    async def nod(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "nod", f"👍 **{interaction.user.name}** nods in firm agreement.", discord.Color.green())

    @app_commands.command(name="pout", description="Expressive: Pout grumpily.")
    async def pout(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "pout", f"😤 **{interaction.user.name}** pouts grumpily.", discord.Color.magenta())

    @app_commands.command(name="shrug", description="Expressive: Shrug your shoulders.")
    async def shrug(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "shrug", f"🤷 **{interaction.user.name}** shrugs their shoulders indifferently.", discord.Color.light_grey())

    @app_commands.command(name="sleep", description="Expressive: Drift off to sleep.")
    async def sleep(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "sleep", f"💤 **{interaction.user.name}** curls up and drifts off to sleep.", discord.Color.dark_blue())

    @app_commands.command(name="smile", description="Expressive: Offer a warm, comforting smile.")
    async def smile(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "smile", f"☀️ **{interaction.user.name}** offers a warm, comforting smile.", discord.Color.from_rgb(173, 216, 230))

    @app_commands.command(name="smug", description="Expressive: Wear a smug, knowing grin.")
    async def smug(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "smug", f"😏 **{interaction.user.name}** wears a smug, knowing grin.", discord.Color.dark_green())

    @app_commands.command(name="think", description="Expressive: Deep in thought.")
    async def think(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "think", f"🤔 **{interaction.user.name}** is deep in thought.", discord.Color.orange())

    @app_commands.command(name="yawn", description="Expressive: Let out a sleepy yawn.")
    async def yawn(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "yawn", f"🥱 **{interaction.user.name}** lets out a sleepy yawn.", discord.Color.light_grey())

    @app_commands.command(name="dance", description="Standalone: Break out into an energetic celebratory dance.")
    async def dance(self, interaction: discord.Interaction):
        await self._run_expressive(interaction, "dance", f"💃 **{interaction.user.name}** breaks into a celebratory dance party!", discord.Color.gold())

    # -------------------------------------------------------------
    # 🤝 INTERACTIVE TARGETED COMMANDS
    # -------------------------------------------------------------
    @app_commands.command(name="warm", description="Interactive: Offer a warm drink to another member.")
    @app_commands.describe(member="Optional: Select the target user you want to share a drink with.")
    async def warm(self, interaction: discord.Interaction, member: discord.Member = None):
        if interaction.guild and not interaction.client.is_feature_enabled(interaction.guild.id, 'social_enabled'):
            await interaction.response.send_message("❌ **Feature Disabled:** Social interaction commands are currently turned off in this server.", ephemeral=True)
            return

        if member is None or member.id == interaction.user.id:
            await interaction.response.send_message("☕ You hold a warm mug of coffee in your own hands.", ephemeral=False)
            return
        
        embed = discord.Embed(
            description=f"☕ **{interaction.user.mention}** passes a steaming mug of coffee over to **{member.mention}**!",
            color=discord.Color.from_rgb(147, 112, 219)
        )
        await interaction.response.send_message(content=member.mention, embed=embed)

    @app_commands.command(name="baka", description="Interactive: Playfully call another member an idiot!")
    @app_commands.describe(member="Select the target user.")
    async def baka(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "baka",
                                    f"💢 **{interaction.user.mention}** calls **{member.mention}** an absolute baka!",
                                    "🤡 You call yourself a baka.", discord.Color.red())

    @app_commands.command(name="hug", description="Interactive: Offer a warm hug.")
    @app_commands.describe(member="Select the target user you want to hug.")
    async def hug(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "hug", 
                                    f"🫂 **{interaction.user.mention}** gives **{member.mention}** a big, warm hug!",
                                    "❄️ You wrap your arms around yourself.", discord.Color.from_rgb(173, 216, 230))

    @app_commands.command(name="love", description="Interactive: Send affection to another member.")
    @app_commands.describe(member="Select the target user.")
    async def love(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "love",
                                    f"💖 **{interaction.user.mention}** sends some warm love over to **{member.mention}**!",
                                    "💖 You hug yourself warmly.", discord.Color.from_rgb(255, 105, 180))

    @app_commands.command(name="run", description="Interactive: Run away from another member.")
    @app_commands.describe(member="Select the target user you are running from.")
    async def run(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "run",
                                    f"🏃 **{interaction.user.mention}** runs away from **{member.mention}**!",
                                    "🏃 You run around in circles.", discord.Color.blue())

    @app_commands.command(name="slap", description="Interactive: Slap another member.")
    @app_commands.describe(member="Select the target user you want to slap.")
    async def slap(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "slap",
                                    f"💥 **{interaction.user.mention}** slaps **{member.mention}** across the face!",
                                    "👋 You manage to slap yourself.", discord.Color.red())

    @app_commands.command(name="pat", description="Interactive: Gently pat another member on the head.")
    @app_commands.describe(member="Select the target user you want to headpat.")
    async def pat(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "pat",
                                    f"👋 **{interaction.user.mention}** gently pats **{member.mention}** on the head.",
                                    "🐱 You pat your own head.", discord.Color.green())

    @app_commands.command(name="cuddle", description="Interactive: Cuddle with another member.")
    @app_commands.describe(member="Select the target user you want to cuddle.")
    async def cuddle(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "cuddle",
                                    f"🧸 **{interaction.user.mention}** cuddles with **{member.mention}**!",
                                    "🛋️ You cuddle up by yourself with a soft plushie.", discord.Color.from_rgb(255, 182, 193))

    @app_commands.command(name="bite", description="Interactive: Take a playful little bite out of another member.")
    @app_commands.describe(member="Select the target user you want to bite.")
    async def bite(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "bite",
                                    f"🦷 **{interaction.user.mention}** takes a playful little bite out of **{member.mention}**!",
                                    "🥐 You playfully bite into a snack instead.", discord.Color.red())

    @app_commands.command(name="bonk", description="Interactive: Bonk another member on the head.")
    @app_commands.describe(member="Select the target user you want to bonk.")
    async def bonk(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "bonk",
                                    f"🔨 **{interaction.user.mention}** bonks **{member.mention}** on the head!",
                                    "🤕 You accidentally bonk your own head.", discord.Color.orange())

    @app_commands.command(name="feed", description="Interactive: Feed something delicious to another member.")
    @app_commands.describe(member="Select the target user you want to feed.")
    async def feed(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "feed",
                                    f"🍰 **{interaction.user.mention}** feeds a delicious treat to **{member.mention}**! 🥧",
                                    "🍫 You happily feed yourself another snack.", discord.Color.orange())

    @app_commands.command(name="handhold", description="Interactive: Gently hold hands with another member.")
    @app_commands.describe(member="Select the target user you want to hold hands with.")
    async def handhold(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "handhold",
                                    f"🤝 **{interaction.user.mention}** gently holds hands with **{member.mention}**.",
                                    "🔥 You interlock your own hands.", discord.Color.from_rgb(255, 182, 193))

    @app_commands.command(name="handshake", description="Interactive: Firmly shake hands with another member.")
    @app_commands.describe(member="Select the target user you want to shake hands with.")
    async def handshake(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "handshake",
                                    f"🤝 **{interaction.user.mention}** firmly shakes hands with **{member.mention}**!",
                                    "🤝 You shake your own hand.", discord.Color.green())

    @app_commands.command(name="highfive", description="Interactive: Slap a celebratory high-five with another member.")
    @app_commands.describe(member="Select the target user you want to high-five.")
    async def highfive(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "highfive",
                                    f"🖐️ **{interaction.user.mention}** slaps a celebratory high-five with **{member.mention}**! ⚡",
                                    "💨 You high-five the air.", discord.Color.gold())

    @app_commands.command(name="kick", description="Interactive: Playfully kick another member.")
    @app_commands.describe(member="Select the target user you want to kick.")
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "kick",
                                    f"👟 **{interaction.user.mention}** playfully kicks **{member.mention}**!",
                                    "🪵 You kick a loose floorboard.", discord.Color.red())

    @app_commands.command(name="kiss", description="Interactive: Plant a sweet kiss on another member.")
    @app_commands.describe(member="Select the target user you want to kiss.")
    async def kiss(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "kiss",
                                    f"💋 **{interaction.user.mention}** plants an affectionate kiss on **{member.mention}**. 🌹",
                                    "🧸 You kiss your soft plushie.", discord.Color.from_rgb(255, 182, 193))

    @app_commands.command(name="peck", description="Interactive: Give another member a quick little peck.")
    @app_commands.describe(member="Select the target user you want to peck.")
    async def peck(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "peck",
                                    f"😚 **{interaction.user.mention}** gives **{member.mention}** a quick little peck!",
                                    "💪 You peck your own shoulder.", discord.Color.from_rgb(255, 182, 193))

    @app_commands.command(name="poke", description="Interactive: Persistently poke another member.")
    @app_commands.describe(member="Select the target user you want to poke.")
    async def poke(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "poke",
                                    f"👉 **{interaction.user.mention}** persistently pokes **{member.mention}**!",
                                    "🙄 You poke your own cheeks.", discord.Color.light_grey())

    @app_commands.command(name="punch", description="Interactive: Playfully punch another member's shoulder.")
    @app_commands.describe(member="Select the target user you want to punch.")
    async def punch(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "punch",
                                    f"👊 **{interaction.user.mention}** playfully punches **{member.mention}** on the shoulder!",
                                    "💥 You punch a couch pillow.", discord.Color.red())

    @app_commands.command(name="shoot", description="Interactive: Shoot a playful finger-gun gesture at another member.")
    @app_commands.describe(member="Select the target user you want to shoot finger guns at.")
    async def shoot(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "shoot",
                                    f"👉💥 **{interaction.user.mention}** shoots a finger-gun gesture over at **{member.mention}**!",
                                    "🪞 You shoot finger-guns at yourself in the mirror.", discord.Color.teal())

    @app_commands.command(name="stare", description="Interactive: Lock eyes and stare intently at another member.")
    @app_commands.describe(member="Select the target user you want to stare at.")
    async def stare(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "stare",
                                    f"👀 **{interaction.user.mention}** locks eyes and stares intently at **{member.mention}**...",
                                    "🔥 You stare blankly into space.", discord.Color.dark_purple())

    @app_commands.command(name="thumbsup", description="Interactive: Flash a supportive thumbs-up to another member.")
    @app_commands.describe(member="Select the target user you want to thumbs-up.")
    async def thumbsup(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "thumbsup",
                                    f"👍 **{interaction.user.mention}** flashes a supportive thumbs-up to **{member.mention}**!",
                                    "👍 You give yourself a thumbs-up.", discord.Color.green())

    @app_commands.command(name="tickle", description="Interactive: Tickle another member relentlessly.")
    @app_commands.describe(member="Select the target user you want to tickle.")
    async def tickle(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "tickle",
                                    f"🤣 **{interaction.user.mention}** tickles **{member.mention}** relentlessly!",
                                    "🧦 You wiggle your toes.", discord.Color.yellow())

    @app_commands.command(name="wave", description="Interactive: Wave happily to another member.")
    @app_commands.describe(member="Select the target user you want to wave to.")
    async def wave(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "wave",
                                    f"👋 **{interaction.user.mention}** waves happily to **{member.mention}**!",
                                    "👋 You wave to the empty room.", discord.Color.from_rgb(173, 216, 230))

    @app_commands.command(name="wink", description="Interactive: Flash a sly, playful wink over to another member.")
    @app_commands.describe(member="Select the target user you want to wink at.")
    async def wink(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "wink",
                                    f"😉 **{interaction.user.mention}** flashes a sly wink over to **{member.mention}**!",
                                    "😉 You wink at your own reflection.", discord.Color.teal())

    @app_commands.command(name="yeet", description="Interactive: Yeet another member ruthlessly.")
    @app_commands.describe(member="Select the target user you want to yeet.")
    async def yeet(self, interaction: discord.Interaction, member: discord.Member):
        await self._run_interactive(interaction, member, "yeet",
                                    f"🚀 **{interaction.user.mention}** ruthlessly yeets **{member.mention}** away!",
                                    "🗑️ You yeet a piece of paper into the trash.", discord.Color.red())

    @blush.error
    @bored.error
    @confused.error
    @cringe.error
    @cry.error
    @clap.error
    @facepalm.error
    @happy.error
    @laugh.error
    @lurk.error
    @nod.error
    @pout.error
    @shrug.error
    @sleep.error
    @smile.error
    @smug.error
    @think.error
    @yawn.error
    @dance.error
    @warm.error
    @baka.error
    @hug.error
    @love.error
    @run.error
    @slap.error
    @pat.error
    @cuddle.error
    @bite.error
    @bonk.error
    @feed.error
    @handhold.error
    @handshake.error
    @highfive.error
    @kick.error
    @kiss.error
    @peck.error
    @poke.error
    @punch.error
    @shoot.error
    @stare.error
    @thumbsup.error
    @tickle.error
    @wave.error
    @wink.error
    @yeet.error
    async def interaction_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            seconds = int(error.retry_after % 60)
            await interaction.response.send_message(
                f"⏳ **Rate Limit Intercept:** This action is cooling down. Please wait **{seconds}s** before interacting again.",
                ephemeral=True
            )
        else:
            cmd_name = interaction.command.name if interaction.command else "Unknown Command"
            print(f"🚨 Code Error in `/{cmd_name}`: {error}")

async def setup(bot):
    await bot.add_cog(InteractionCommands(bot))