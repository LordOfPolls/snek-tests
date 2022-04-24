import asyncio
import inspect
import logging
import os
import traceback
from contextlib import suppress
from time import perf_counter
from typing import Callable

import dis_snek
from dis_snek import (
    MessageContext,
    Intents,
    listen,
    AutocompleteContext,
)
from dis_snek.client.errors import NotFound
from dotenv import load_dotenv
from thefuzz import fuzz, process

load_dotenv()

logging.basicConfig(
    format="[%(filename)s:%(lineno)d] %(levelname)s - %(message)s",
    datefmt="%m-%d %H:%M:%S",
)
cls_log = logging.getLogger(dis_snek.const.logger_name)
cls_log.setLevel(logging.DEBUG)


class Bot(dis_snek.Snake):
    def __init__(self):
        super().__init__(
            default_prefix="<",
            intents=Intents.ALL,
            asyncio_debug=True,
            sync_interactions=True,
            delete_unused_application_cmds=True,
        )
        self.load_extension("dis_snek.ext.debug_scale")
        self.load_extension("tests.tests")

        self.available: asyncio.Event = asyncio.Event()
        self.available.set()

    @listen()
    async def on_ready(self):
        print(f"Logged in as {self.app.name}")

    async def run_test(self, name: str, method: Callable, ctx: MessageContext):
        test_title = f"{method.__name__.removeprefix('test_')} Tests".title()

        msg = await ctx.channel.send(
            f"<a:loading:950666903540625418> {test_title}: Running!"
        )
        try:
            await method(ctx, msg)
        except Exception as e:
            trace = "\n".join(traceback.format_exception(e))
            await msg.edit(f"❌ {test_title}: Failed \n```{trace}```")
        else:
            await msg.edit(f"✅ {test_title}: Completed")

    @dis_snek.slash_command("begin")
    @dis_snek.slash_option(
        "test", description="Run a specific test", opt_type=3, required=False
    )
    async def begin(self, ctx: MessageContext, test: str | None = None):
        if not self.available.is_set():
            await ctx.send("Waiting for current tests to complete...")
            await self.available.wait()

        if ctx.guild.id == 870046872864165888:
            if ctx.author.id != self.owner.id:
                return await ctx.send(
                    f"Only {self.owner.mention} can use the test suite"
                )

        self.available.clear()

        source = await ctx.send(
            "<a:loading:950666903540625418> Running dis_snek test suite..."
        )

        tasks = []
        s = perf_counter()

        methods = inspect.getmembers(self.scales["Tests"], self.filter)

        for name, method in methods:
            if test:
                if test.lower() not in name:
                    continue
            tasks.append(asyncio.create_task(self.run_test(name, method, ctx)))

        await asyncio.gather(*tasks)

        dur = perf_counter() - s

        await source.edit("✅ Dis_snek Test Suite: Completed")

        await ctx.channel.send(f"Tests completed in {round(dur, 2)} seconds")

        for channel in ctx.guild.channels:
            if channel.name.startswith("_test"):
                with suppress(NotFound):
                    await channel.delete()

        self.available.set()

    def filter(self, obj) -> bool:
        if inspect.ismethod(obj):
            if getattr(obj, "__name__").startswith("test_"):
                return True
        return False

    @begin.autocomplete("test")
    async def test_autocomplete(self, ctx: AutocompleteContext, **_):
        methods = [i[0] for i in inspect.getmembers(self.scales["Tests"], self.filter)]
        output = []

        if methods:
            if ctx.input_text:
                result = process.extract(
                    ctx.input_text, methods, scorer=fuzz.partial_token_sort_ratio
                )
                output = [t[0] for t in result if t[1] > 50]
            else:
                output = list(methods)[:25]
        await ctx.send(output)


Bot().start(os.environ.get("TOKEN"))
