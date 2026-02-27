import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import io
import math
from PIL import Image, ImageDraw
from dotenv import load_dotenv
import os
load_dotenv()

# ---- CONFIG ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
FRAME_COUNT = 80
FILL_FRAMES = 40
FRAME_DURATION = 50  # ms per frame

JAR_URL = "https://purepng.com/public/uploads/large/purepng.com-glass-jarobjectsglass-jarbottle-glass-object-pot-jar-631522325591pohq0.png"

SIZE = 128
BG_COLOR = (40, 40, 40)

LIQUID_X = 18
LIQUID_Y = 28
LIQUID_W = 90
LIQUID_H = 90
LIQUID_COLOR = (255, 250, 240)

WOBBLE_AMP = 3
WOBBLE_SPEED = 0.1

# ---- BOT SETUP ----
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---- BURST PROGRESSION ----
def burst_levels(fill_frames: int) -> list:
    bursts = [
        (1/5,             fill_frames * 0.25),
        (1/2,             fill_frames * 0.5),
        (1/3+1/4+1/6,     fill_frames * 0.75),
        (1.0,             fill_frames - 1),
    ]
    levels = []
    for i in range(fill_frames):
        prev_target, prev_frame = 0.0, 0
        for target, frame in bursts:
            if i <= frame:
                t = (i - prev_frame) / max(frame - prev_frame, 1)
                t = t * t * (3 - 2 * t)
                level = prev_target + (target - prev_target) * t
                levels.append(min(level, 1.0))
                break
            prev_target, prev_frame = target, frame
        else:
            levels.append(1.0)
    return levels

# ---- GIF GENERATION ----
async def generate_gif(avatar_bytes: bytes, jar_bytes: bytes) -> io.BytesIO:
    # Prepare avatar
    avatar_rgba = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((LIQUID_W, LIQUID_H))
    mask = Image.new("L", (LIQUID_W, LIQUID_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, LIQUID_W, LIQUID_H], radius=10, fill=255)
    avatar_rgba.putalpha(mask)
    avatar_rgb = Image.new("RGB", (LIQUID_W, LIQUID_H), BG_COLOR)
    avatar_rgb.paste(avatar_rgba, (0, 0), avatar_rgba)

    # Prepare jar
    jar_rgba = Image.open(io.BytesIO(jar_bytes)).convert("RGBA").resize((SIZE, SIZE))
    jar_rgb = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    jar_rgb.paste(jar_rgba, (0, 0), jar_rgba)
    jar_mask = jar_rgba.split()[3]

    # Precompute rounded rect mask (same every frame)
    rounded_mask = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(rounded_mask).rounded_rectangle(
        [LIQUID_X, LIQUID_Y, LIQUID_X + LIQUID_W, LIQUID_Y + LIQUID_H],
        radius=10, fill=(255, 255, 255, 255)
    )
    rounded_mask_alpha = rounded_mask.split()[3]

    levels = burst_levels(FILL_FRAMES)
    empty_rgba = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    frames = []

    for i in range(FRAME_COUNT):
        frame = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        frame.paste(avatar_rgb, (LIQUID_X, LIQUID_Y))

        progress = levels[i] if i < FILL_FRAMES else 1.0
        liquid_height = int(LIQUID_H * progress)
        liquid_top = LIQUID_Y + LIQUID_H - liquid_height

        if liquid_height > 0:
            # Build wobbled surface polygon
            points = []
            for x in range(LIQUID_X, LIQUID_X + LIQUID_W + 1):
                wobble = int(WOBBLE_AMP * math.sin(
                    (x / LIQUID_W) * math.pi * 2 + i * WOBBLE_SPEED
                ))
                top = max(liquid_top + wobble, LIQUID_Y)
                points.append((x, top))
            points.append((LIQUID_X + LIQUID_W, LIQUID_Y + LIQUID_H))
            points.append((LIQUID_X, LIQUID_Y + LIQUID_H))

            # Draw liquid on transparent RGBA layer
            liquid_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
            ImageDraw.Draw(liquid_layer).polygon(points, fill=(*LIQUID_COLOR, 245))

            # Clip to rounded rect
            liquid_layer = Image.composite(liquid_layer, empty_rgba, rounded_mask_alpha)

            # Composite onto frame
            frame_rgba = frame.convert("RGBA")
            frame_rgba = Image.alpha_composite(frame_rgba, liquid_layer)
            frame = frame_rgba.convert("RGB")

        # Paste jar on top
        frame.paste(jar_rgb, (0, 0), jar_mask)
        frames.append(frame)

    output = io.BytesIO()
    frames[0].save(
        output, format="GIF", save_all=True,
        append_images=frames[1:], loop=0, duration=FRAME_DURATION,
    )
    output.seek(0)
    return output

# ---- SLASH COMMAND ----
@tree.command(name="cumjar", description="Put someone in a jar and cum on them!")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def jar(interaction: discord.Interaction, victim: discord.User):
    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        avatar_url = victim.display_avatar.with_format("png").with_size(128).url
        async with session.get(avatar_url) as resp:
            avatar_bytes = await resp.read()

        async with session.get(JAR_URL) as resp:
            jar_bytes = await resp.read()

    gif = await generate_gif(avatar_bytes, jar_bytes)

    await interaction.followup.send(
        content=f"*{interaction.user.mention} cums on {victim.mention}*",
        file=discord.File(gif, filename="jar.gif"),
    )

# ---- STARTUP ----
@bot.event
async def on_ready():
    synced = await tree.sync()
    print(f"Synced {len(synced)} commands")
    print(f"Logged in as {bot.user}")


bot.run(BOT_TOKEN)

