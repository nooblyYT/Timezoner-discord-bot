import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import json
import os

# --- CONFIG ---
# Hide your token using environment variables
# In your terminal: export DISCORD_TOKEN="your_token_here"
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("Please set the DISCORD_TOKEN environment variable!")

GUILD_ID = 1188742345768837261  # your server ID
UPDATE_INTERVAL = 60  # seconds
DATA_FILE = "user_timezones.json"

# --- Load persistent user timezones ---
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        USER_TIMEZONES = json.load(f)
        USER_TIMEZONES = {int(k): v for k, v in USER_TIMEZONES.items()}
else:
    USER_TIMEZONES = {}

original_nicknames = {}

# --- Bot setup ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Helper functions ---
def get_time_string(tz_name):
    try:
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)
        return now.strftime("%I:%M %p")
    except:
        return None

def save_timezones():
    with open(DATA_FILE, "w") as f:
        json.dump(USER_TIMEZONES, f)

# --- Nickname update loop ---
@tasks.loop(seconds=UPDATE_INTERVAL)
async def update_nicknames():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("[Timezoner] Guild not found!")
        return

    for member in guild.members:
        user_id = member.id
        original = original_nicknames.get(user_id, member.nick or member.name)
        tz = USER_TIMEZONES.get(user_id)

        if tz:
            time_now = get_time_string(tz)
            if not time_now:
                continue
            new_nick = f"{original} | {time_now}"
        else:
            # Remove time if user deleted their timezone
            new_nick = original

        try:
            if member.nick != new_nick:
                await member.edit(nick=new_nick)
                print(f"[Timezoner] Updated {member} → {new_nick}")
        except discord.Forbidden:
            print(f"[Timezoner] Cannot edit {member} — missing permissions")
        except Exception as e:
            print(f"[Timezoner] Error updating {member}: {e}")

# --- /timezone command ---
@bot.tree.command(name="timezone", description="Set your timezone for nickname updates")
@app_commands.describe(tz="Timezone name, e.g. America/Chicago")
async def timezone(interaction: discord.Interaction, tz: str):
    if tz.lower() in ["remove", "delete", "none"]:
        # Remove timezone
        USER_TIMEZONES.pop(interaction.user.id, None)
        save_timezones()
        await interaction.response.send_message(
            "Your timezone has been removed. Time will no longer appear in your nickname.",
            ephemeral=True
        )
        print(f"[Timezoner] {interaction.user} removed their timezone")
        return

    # Validate timezone
    try:
        pytz.timezone(tz)
    except:
        await interaction.response.send_message(
            "Invalid timezone. Example: `America/Chicago`", ephemeral=True
        )
        return

    USER_TIMEZONES[interaction.user.id] = tz
    save_timezones()

    # Save original nickname
    member = interaction.guild.get_member(interaction.user.id)
    if member:
        original_nicknames[interaction.user.id] = member.nick or member.name

    # Update nickname immediately
    time_now = get_time_string(tz)
    if member and time_now:
        try:
            await member.edit(nick=f"{original_nicknames[interaction.user.id]} | {time_now}")
        except discord.Forbidden:
            print(f"[Timezoner] Cannot edit {member} — missing permissions")
        except Exception as e:
            print(f"[Timezoner] Error updating {member}: {e}")

    await interaction.response.send_message(
        f"Timezone set to `{tz}`. Your nickname will update automatically.", ephemeral=True
    )
    print(f"[Timezoner] {interaction.user} set timezone to {tz}")

# --- /timezones command ---
@bot.tree.command(name="timezones", description="List all available timezones")
async def timezones(interaction: discord.Interaction):
    zones = pytz.all_timezones
    chunk_size = 50
    messages = []
    for i in range(0, len(zones), chunk_size):
        chunk = zones[i:i+chunk_size]
        messages.append("```\n" + "\n".join(chunk) + "\n```")

    await interaction.response.send_message(
        f"There are {len(zones)} available timezones. Use `/timezone <timezone>` to set your timezone.\n\n" +
        messages[0], ephemeral=True
    )

    for msg in messages[1:]:
        await interaction.followup.send(msg, ephemeral=True)

# --- On ready ---
@bot.event
async def on_ready():
    # Sync guild commands immediately
    guild = discord.Object(id=GUILD_ID)
    try:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"[Timezoner] Slash commands synced to guild {GUILD_ID}")
    except Exception as e:
        print(f"[Timezoner] Failed to sync guild commands: {e}")

    # Attempt global sync (may take up to 1 hour)
    try:
        await bot.tree.sync()
        print("[Timezoner] Slash commands synced globally")
    except Exception as e:
        print(f"[Timezoner] Global sync failed: {e}")

    print(f"[Timezoner] Logged in as {bot.user}")
    update_nicknames.start()

# --- Run bot ---
bot.run(TOKEN)
