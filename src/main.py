import discord
import toml
import logging
import subprocess
import discord.ext.commands as commands
import discord.ext.tasks as tasks
import re
import asyncio
import json
import argparse
import traceback
import random
import rolldice
#import aiopubsub

import tio
import db
import util
import achievement

config = util.config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(asctime)s %(message)s", datefmt="%H:%M:%S %d/%m/%Y")

bot = commands.Bot(command_prefix=config["prefix"], description="AutoBotRobot, the most useless bot in the known universe.", case_insensitive=True)
bot._skip_check = lambda x, y: False


cleaner = discord.ext.commands.clean_content()
def clean(ctx, text):
    return cleaner.convert(ctx, text)

@bot.event
async def on_message(message):
    words = message.content.split(" ")
    if len(words) == 10 and message.author.id == 435756251205468160:
        await message.channel.send(util.unlyric(message.content))
    else:
        if message.author == bot.user or message.author.discriminator == "0000": return
        ctx = await bot.get_context(message)
        if not ctx.valid: return
        await bot.invoke(ctx)

@bot.event
async def on_command_error(ctx, err):
    #print(ctx, err)
    if isinstance(err, (commands.CommandNotFound, commands.CheckFailure)): return
    if isinstance(err, commands.MissingRequiredArgument): return await ctx.send(embed=util.error_embed(str(err)))
    try:
        trace = re.sub("\n\n+", "\n", "\n".join(traceback.format_exception(err, err, err.__traceback__)))
        logging.error("command error occured (in %s)", ctx.invoked_with, exc_info=err)
        await ctx.send(embed=util.error_embed(util.gen_codeblock(trace), title="Internal error"))
        await achievement.achieve(ctx.bot, ctx.message, "error")
    except Exception as e: print("meta-error:", e)

@bot.command(help="Gives you a random fortune as generated by `fortune`.")
async def fortune(ctx):
    await ctx.send(subprocess.run(["fortune"], stdout=subprocess.PIPE, encoding="UTF-8").stdout)

@bot.command(help="Generates an apioform type.")
async def apioform(ctx):
    await ctx.send(util.apioform())

@bot.command(help="Says Pong.")
async def ping(ctx):
    await ctx.send("Pong.")

@bot.command(help="Deletes the specified target.", rest_is_raw=True)
async def delete(ctx, *, raw_target):
    target = await clean(ctx, raw_target.strip().replace("\n", " "))
    if len(target) > 256:
        await ctx.send(embed=util.error_embed("Deletion target must be max 256 chars"))
        return
    async with ctx.typing():
        await ctx.send(f"Deleting {target}...")
        await asyncio.sleep(1)
        await bot.database.execute("INSERT INTO deleted_items (timestamp, item) VALUES (?, ?)", (util.timestamp(), target))
        await bot.database.commit()
        await ctx.send(f"Deleted {target} successfully.")

@bot.command(help="View recently deleted things, optionally matching a filter.")
async def list_deleted(ctx, search=None):
    acc = "Recently deleted:\n"
    if search: acc = f"Recently deleted (matching {search}):\n"
    csr = None
    if search:
        csr = bot.database.execute("SELECT * FROM deleted_items WHERE item LIKE ? ORDER BY timestamp DESC LIMIT 100", (f"%{search}%",))
    else:
        csr = bot.database.execute("SELECT * FROM deleted_items ORDER BY timestamp DESC LIMIT 100")
    async with csr as cursor:
        async for row in cursor:
            to_add = "- " + row[2].replace("```", "[REDACTED]") + "\n"
            if len(acc + to_add) > 2000:
                break
            acc += to_add
    await ctx.send(acc)

# Python, for some *very intelligent reason*, makes the default ArgumentParser exit the program on error.
# This is obviously undesirable behavior in a Discord bot, so we override this.
class NonExitingArgumentParser(argparse.ArgumentParser):
    def exit(self, status=0, message=None):
        if status:
            raise Exception(f'Flag parse error: {message}')
        exit(status)

EXEC_REGEX = "^(.*)```([a-zA-Z0-9_\\-+]+)?\n(.*)```$"

exec_flag_parser = NonExitingArgumentParser(add_help=False)
exec_flag_parser.add_argument("--verbose", "-v", action="store_true")
exec_flag_parser.add_argument("--language", "-L")

@bot.command(rest_is_raw=True, help="Execute provided code (in a codeblock) using TIO.run.")
async def exec(ctx, *, arg):
    match = re.match(EXEC_REGEX, arg, flags=re.DOTALL)
    if match == None:
        await ctx.send(embed=util.error_embed("Invalid format. Expected a codeblock."))
        return
    flags_raw = match.group(1)
    flags = exec_flag_parser.parse_args(flags_raw.split())
    lang = flags.language or match.group(2)
    if not lang:
        await ctx.send(embed=util.error_embed("No language specified. Use the -L flag or add a language to your codeblock."))
        return
    lang = lang.strip()
    code = match.group(3)

    async with ctx.typing():
        ok, real_lang, result, debug = await tio.run(lang, code)
        if not ok:
            await ctx.send(embed=util.error_embed(util.gen_codeblock(result), "Execution failed"))
        else:
            out = result
            if flags.verbose: 
                debug_block = "\n" + util.gen_codeblock(f"""{debug}\nLanguage:  {real_lang}""")
                out = out[:2000 - len(debug_block)] + debug_block
            else:
                out = out[:2000]
            await ctx.send(out)

@bot.command(help="List supported languages, optionally matching a filter.")
async def supported_langs(ctx, search=None):
    langs = sorted(tio.languages())
    acc = ""
    for lang in langs:
        if len(acc + lang) > 2000:
            await ctx.send(acc)
            acc = ""
        if search == None or search in lang: acc += lang + " "
    if acc == "": acc = "No results."
    await ctx.send(acc)

@bot.command(help="Get some information about the bot.", aliases=["invite"])
async def about(ctx):
    await ctx.send("""**AutoBotRobot: The least useful Discord bot ever designed.**
AutoBotRobot has many features, but not necessarily any practical ones.
It can execute code via TIO.run, do reminders, print fortunes, and not any more!
AutoBotRobot is open source - the code is available at <https://github.com/osmarks/autobotrobot> - and you could run your own instance if you wanted to and could get around the complete lack of user guide or documentation.
You can also invite it to your server: <https://discordapp.com/oauth2/authorize?&client_id=509849474647064576&scope=bot&permissions=68608>
""")

@bot.command(help="Randomly generate an integer using dice syntax.", name="random", rest_is_raw=True)
async def random_int(ctx, *, dice):
    await ctx.send(rolldice.roll_dice(dice)[0])

bad_things = ["lyric", "endos", "solarflame", "lyric", "319753218592866315", "andrew", "6", "c++"]
good_things = ["potato", "heav", "gollark", "helloboi", "bees", "hellboy", "rust", "ferris", "crab", "transistor"]
negations = ["not", "bad", "un", "kill", "n't"]
def weight(thing):
    lthing = thing.lower()
    weight = 1.0
    if lthing == "c": weight *= 0.3
    for bad_thing in bad_things:
        if bad_thing in lthing: weight *= 0.5
    for good_thing in good_things:
        if good_thing in lthing: weight *= 2.0
    for negation in negations:
        for _ in range(lthing.count(negation)): weight = 1 / weight
    return weight

@bot.command(help="'Randomly' choose between the specified options.", name="choice", aliases=["choose"])
async def random_choice(ctx, *choices):
    choicelist = list(choices)
    samples = 1
    try:
        samples = int(choices[0])
        choicelist.pop(0)
    except: pass

    if samples > 1e4:
        await ctx.send("No.")
        return

    choices = random.choices(choicelist, weights=map(weight, choicelist), k=samples)

    if len(choices) == 1:
        await ctx.send(choices[0])
    else:
        counts = {}
        for choice in choices:
            counts[choice] = counts.get(choice, 0) + 1
        await ctx.send("\n".join(map(lambda x: f"{x[0]} x{x[1]}", counts.items())))
@bot.check
async def andrew_bad(ctx):
    return ctx.message.author.id != 543131534685765673

@bot.event
async def on_ready():
    logging.info("Connected as " + bot.user.name)
    await bot.change_presence(status=discord.Status.online, 
        activity=discord.Activity(name=f"{bot.command_prefix}help", type=discord.ActivityType.listening))

async def run_bot():
    bot.database = await db.init(config["database"])
    for ext in (
        "reminders",
        "debug",
        "telephone",
        "achievement"
    ):
        bot.load_extension(ext)
    await bot.start(config["token"])

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.logout())
    finally:
        loop.close()
