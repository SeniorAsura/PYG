import discord
from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands
import json
import os
import random
import string
import aiohttp

TOKEN = os.environ.get("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"registered": {}, "pending": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def make_code():
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PYG-{suffix}"

async def get_roblox_user(username: str):
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": False}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            results = data.get("data", [])
            if not results:
                return None
            user = results[0]
            return user["id"], user["name"]

async def get_roblox_description(user_id: int):
    url = f"https://users.roblox.com/v1/users/{user_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("description", "")

class VerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.green, emoji="✅", custom_id="verify_panel_button")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        role = discord.utils.get(interaction.guild.roles, name="Verified")
        if not role:
            await interaction.response.send_message("❌ The **Verified** role doesn't exist yet. Ask an admin to create it.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("You're already verified!", ephemeral=True)
            return
        await interaction.user.add_roles(role)
        await interaction.response.send_message("✅ You are now **Verified**!\nUse `/register` to link and verify your Roblox account.", ephemeral=True)

class RobloxConfirmView(View):
    def __init__(self, discord_id: int):
        super().__init__(timeout=300)
        self.discord_id = discord_id

    @discord.ui.button(label="✅ I added the code — Check now!", style=discord.ButtonStyle.blurple)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.discord_id:
            await interaction.response.send_message("This isn't your verification.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        user_id_str = str(interaction.user.id)
        if user_id_str not in data.get("pending", {}):
            await interaction.followup.send("❌ No pending verification found. Run `/register` again.", ephemeral=True)
            return
        entry = data["pending"][user_id_str]
        roblox_id = entry["roblox_id"]
        code = entry["code"]
        roblox_username = entry["roblox_username"]
        description = await get_roblox_description(roblox_id)
        if description is None:
            await interaction.followup.send("❌ Couldn't reach Roblox. Try again in a moment.", ephemeral=True)
            return
        if code not in description:
            await interaction.followup.send(
                f"❌ Code **`{code}`** not found in your Roblox profile description.\n\n"
                "Make sure you:\n"
                "1. Go to **roblox.com** → your profile → **Edit**\n"
                "2. Paste the code into your **About Me / Description**\n"
                "3. Save, then click the button again.", ephemeral=True)
            return
        data["registered"][user_id_str] = {"roblox_username": roblox_username, "roblox_id": roblox_id, "verified": True}
        del data["pending"][user_id_str]
        save_data(data)
        verified_role = discord.utils.get(interaction.guild.roles, name="Verified")
        member_role = discord.utils.get(interaction.guild.roles, name="Member")
        roles_to_add = [r for r in [verified_role, member_role] if r and r not in interaction.user.roles]
        if roles_to_add:
            await interaction.user.add_roles(*roles_to_add)
        await interaction.followup.send(f"✅ **Roblox account verified!**\nLinked to: **{roblox_username}** (ID: `{roblox_id}`)\nWelcome to PYG Clan! 🎮", ephemeral=True)
        embed = discord.Embed(title="🎉 New Member Verified!", description=f"{interaction.user.mention} just verified their Roblox account as **{roblox_username}**!", color=0x8A2BE2)
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.discord_id:
            await interaction.response.send_message("This isn't your verification.", ephemeral=True)
            return
        data = load_data()
        data.get("pending", {}).pop(str(interaction.user.id), None)
        save_data(data)
        await interaction.response.send_message("❌ Verification cancelled.", ephemeral=True)
        self.stop()

@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Game("PYG Clan • Rivals"))
    print(f"✅ {bot.user} is online!")

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name="welcome")
    if not channel:
        channel = member.guild.system_channel
    if not channel:
        return
    embed = discord.Embed(
        title="Welcome to PYG Clan! 🏆",
        description=f"Hey {member.mention}, welcome!\n\n**To get started:**\n1️⃣ Head to the verification channel and click **Verify Me**\n2️⃣ Use `/register <roblox_username>` to verify your Roblox account\n\nOnce verified you'll unlock full server access. Let's go! 🎮",
        color=0x8A2BE2)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Pye-Gaming Clan")
    await channel.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def verification(ctx):
    embed = discord.Embed(title="PYG Clan Verification", description="Click the button below to get verified and gain access to the server!", color=0x8A2BE2)
    embed.set_footer(text="Pye-Gaming Clan")
    await ctx.send(embed=embed, view=VerifyView())
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    if member == ctx.author:
        return await ctx.send("❌ You cannot kick yourself!")
    await member.kick(reason=reason)
    await ctx.send(f"✅ **{member}** has been kicked. Reason: {reason or 'No reason provided.'}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    if member == ctx.author:
        return await ctx.send("❌ You cannot ban yourself!")
    await member.ban(reason=reason)
    await ctx.send(f"✅ **{member}** has been banned. Reason: {reason or 'No reason provided.'}")

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("✅ Slash commands synced!")

@bot.tree.command(name="verify", description="Get verified to access the server")
async def slash_verify(interaction: discord.Interaction):
    role = discord.utils.get(interaction.guild.roles, name="Verified")
    if not role:
        return await interaction.response.send_message("❌ Verified role not found. Ask an admin to create it.", ephemeral=True)
    if role in interaction.user.roles:
        return await interaction.response.send_message("You're already verified!", ephemeral=True)
    await interaction.user.add_roles(role)
    await interaction.response.send_message("✅ You are now **Verified**!\nUse `/register` to link your Roblox account.", ephemeral=True)

@bot.tree.command(name="register", description="Verify your Roblox account ownership")
@app_commands.describe(roblox_username="Your exact Roblox username")
async def register(interaction: discord.Interaction, roblox_username: str):
    await interaction.response.defer(ephemeral=True)
    data = load_data()
    user_id_str = str(interaction.user.id)
    if user_id_str in data.get("registered", {}):
        existing = data["registered"][user_id_str]
        return await interaction.followup.send(f"✅ Already registered as **{existing['roblox_username']}**. Contact an admin to change it.", ephemeral=True)
    result = await get_roblox_user(roblox_username)
    if result is None:
        return await interaction.followup.send(f"❌ Roblox username **{roblox_username}** not found. Check the spelling and try again.", ephemeral=True)
    roblox_id, roblox_display = result
    code = make_code()
    if "pending" not in data:
        data["pending"] = {}
    data["pending"][user_id_str] = {"roblox_username": roblox_display, "roblox_id": roblox_id, "code": code}
    save_data(data)
    embed = discord.Embed(
        title="🔐 Roblox Verification",
        description=f"Found Roblox account: **{roblox_display}** (ID: `{roblox_id}`)\n\n**To verify you own this account:**\n1. Go to **[roblox.com](https://www.roblox.com)** and log in\n2. Click your profile → **Edit Profile**\n3. Paste this code into your **About Me / Description**:\n\n```{code}```\n4. Save your profile, then click the button below.\n\n*(You can remove the code after verification)*",
        color=0x8A2BE2)
    embed.set_footer(text="Code expires in 5 minutes")
    await interaction.followup.send(embed=embed, view=RobloxConfirmView(interaction.user.id), ephemeral=True)

@bot.tree.command(name="whois", description="Look up a member's registered Roblox account")
@app_commands.describe(member="The Discord member to look up")
async def whois(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    data = load_data()
    entry = data.get("registered", {}).get(str(target.id))
    if not entry:
        return await interaction.response.send_message(f"**{target.display_name}** has not registered a Roblox account.", ephemeral=True)
    embed = discord.Embed(title=f"🔍 Roblox Lookup: {target.display_name}", color=0x8A2BE2)
    embed.add_field(name="Roblox Username", value=f"[{entry['roblox_username']}](https://www.roblox.com/users/{entry['roblox_id']}/profile)", inline=False)
    embed.add_field(name="Roblox ID", value=str(entry["roblox_id"]), inline=True)
    embed.add_field(name="Verified", value="✅ Yes" if entry.get("verified") else "❌ No", inline=True)
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
@app_commands.default_permissions(kick_members=True)
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if member == interaction.user:
        return await interaction.response.send_message("❌ You cannot kick yourself!", ephemeral=True)
    await member.kick(reason=reason)
    await interaction.response.send_message(f"✅ **{member}** has been kicked. Reason: {reason or 'No reason provided.'}")

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
@app_commands.default_permissions(ban_members=True)
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if member == interaction.user:
        return await interaction.response.send_message("❌ You cannot ban yourself!", ephemeral=True)
    await member.ban(reason=reason)
    await interaction.response.send_message(f"✅ **{member}** has been banned. Reason: {reason or 'No reason provided.'}")

@bot.tree.command(name="info", description="Show PYG Clan information")
async def info(interaction: discord.Interaction):
    data = load_data()
    embed = discord.Embed(title="🏆 PYG Clan", description="The premier Roblox Rivals clan!", color=0x8A2BE2)
    embed.add_field(name="▶️ YouTube", value="Pye-Gaming", inline=False)
    embed.add_field(name="🎮 Game", value="Roblox Rivals", inline=False)
    embed.add_field(name="👥 Server Members", value=str(interaction.guild.member_count), inline=True)
    embed.add_field(name="✅ Verified Members", value=str(len(data.get("registered", {}))), inline=True)
    embed.set_footer(text="PYG Clan • Rivals")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    elif not isinstance(error, commands.CommandNotFound):
        raise error

bot.run(TOKEN)
