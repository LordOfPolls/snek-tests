import asyncio
import os
from contextlib import suppress
from datetime import datetime

import dis_snek
from dis_snek import (
    InteractionContext,
    MessageableMixin,
    ThreadableMixin,
    BrandColors,
    Embed,
    Status,
    process_emoji_req_format,
    EmbedFooter,
    SelectOption,
    Modal,
    ParagraphText,
    PartialEmoji,
    Scale,
    Permissions,
    Message,
    EmbedField,
    EmbedAuthor,
    EmbedAttachment,
    GuildNews,
    GuildChannel,
)
from dis_snek.api.gateway.gateway import WebsocketClient
from dis_snek.api.http.route import Route
from dis_snek.api.voice.audio import AudioVolume
from dis_snek.client.errors import NotFound


async def append_edit(message: dis_snek.Message, content):
    return await message.edit(message.content + content)


class Tests(Scale):
    @staticmethod
    def ensure_attributes(target_object):
        for attr in dir(target_object):
            # ensure all props and attributes load correctly
            getattr(target_object, attr)

    async def test_channels(self, ctx: InteractionContext, msg):
        channels = [
            guild_category := await ctx.guild.create_category("_test_category"),
            guild_text := await ctx.guild.create_text_channel("_test_text"),
            guild_news := await ctx.guild.create_news_channel("_test_news"),
            guild_stage := await ctx.guild.create_stage_channel("_test_stage"),
            guild_voice := await ctx.guild.create_voice_channel("_test_voice"),
        ]
        assert all(c in ctx.guild.channels for c in channels)

        channels.append(dm := await self.bot.owner.fetch_dm())

        try:
            for channel in channels:
                self.ensure_attributes(channel)

                if isinstance(channel, GuildChannel) and channel != guild_category:
                    await channel.edit(parent_id=guild_category.id)
                    assert channel.category == guild_category

                if isinstance(channel, MessageableMixin):
                    _m = await channel.send("test")
                    assert _m.channel == channel

                    if isinstance(channel, GuildNews):
                        await _m.publish()

                    await _m.delete()

                if isinstance(channel, ThreadableMixin):
                    if isinstance(channel, GuildNews):
                        _tm = await channel.send("dummy message")
                        thread = await _tm.create_thread("new thread")
                    else:
                        thread = await channel.create_thread("new thread")
                    assert thread.parent_channel == channel
                    _m = await thread.send("test")
                    assert _m.channel == thread

                    _m = await channel.send("start thread here")
                    m_thread = await channel.create_thread(
                        "new message thread", message=_m
                    )
                    assert _m.id == m_thread.id

                    assert m_thread in ctx.guild.threads
                    assert thread in ctx.guild.threads
                    await thread.delete()
                    # We suppress bcu sometimes event fires too fast, before wait_for is called
                    with suppress(asyncio.exceptions.TimeoutError):
                        await self.bot.wait_for("thread_delete", timeout=2)
                    assert thread not in ctx.guild.threads
        finally:
            for channel in channels:
                with suppress(NotFound):
                    await channel.delete()

    async def test_messages(self, ctx: InteractionContext, msg):
        thread = await msg.create_thread("Test Thread")

        try:

            _m = await thread.send("Test")
            self.ensure_attributes(_m)

            await _m.edit("Test Edit")
            assert _m.content == "Test Edit"
            await _m.add_reaction("❌")
            with suppress(asyncio.exceptions.TimeoutError):
                await self.bot.wait_for("message_reaction_add", timeout=2)

            assert len(_m.reactions) == 1

            assert len(await _m.fetch_reaction("❌")) != 0
            await _m.remove_reaction("❌")
            with suppress(asyncio.exceptions.TimeoutError):
                await self.bot.wait_for("message_reaction_remove", timeout=2)

            await _m.add_reaction("❌")
            await _m.clear_all_reactions()
            with suppress(asyncio.exceptions.TimeoutError):
                await self.bot.wait_for("message_reaction_remove_all", timeout=2)

            assert len(_m.reactions) == 0

            await _m.pin()
            assert _m.pinned is True
            await _m.suppress_embeds()
            await _m.unpin()

            _r = await _m.reply(
                f"test-reply {self.bot.owner.mention} {ctx.channel.mention}"
            )
            assert _r._referenced_message_id == _m.id

            mem_mentions = []
            async for member in _r.mention_users:
                mem_mentions.append(member)
            assert len(mem_mentions) == 2

            assert len(_r.mention_channels) == 1

            await thread.send(file=r"tests/LordOfPolls.png")

            assert _m.jump_url is not None
            assert _m.proto_url is not None

            await thread.send(embeds=Embed("Test"))

            await thread.delete()

            _m = await self.bot.owner.send("Test Message from TestSuite")
            await _m.delete()

        finally:
            try:
                await thread.delete()
            except dis_snek.errors.NotFound:
                pass

    async def test_roles(self, ctx: InteractionContext, msg):
        roles: list[dis_snek.Role] = []

        try:
            try:
                roles.append(await ctx.guild.create_role("_test_role3"))
                roles.append(await ctx.guild.create_role("_test_role1", icon="💥"))
                roles.append(
                    await ctx.guild.create_role(
                        "_test_role2", icon=r"tests/LordOfPolls.png"
                    )
                )

                assert roles[0].icon is None
                assert isinstance(roles[1].icon, PartialEmoji)
                assert isinstance(roles[2].icon, dis_snek.Asset)
            except dis_snek.errors.Forbidden:
                # this was run in a server without boosts
                pass

            await ctx.guild.me.add_role(roles[0])
            await ctx.guild.me.remove_role(roles[0])

            await roles[0].edit("_test_renamed", color=BrandColors.RED)

            for role in roles:
                await role.delete()

        finally:
            for role in ctx.guild.roles:
                if role.name.startswith("_test"):
                    await role.delete()

    async def test_members(self, ctx: InteractionContext, msg):
        for member in [ctx.guild.me, ctx.guild.get_member(os.environ.get("MEMBER"))]:
            self.ensure_attributes(member)

            await member.edit_nickname("Test Nickname")
            assert member.display_name == "Test Nickname"
            await member.edit_nickname(None)
            assert member.display_name == (self.bot.get_user(member.id)).username

            assert len(member.roles) != 0
            assert member.display_avatar is not None
            assert member.display_name is not None

            assert member.has_permission(Permissions.SEND_MESSAGES)
            assert member.channel_permissions(ctx.channel)

            assert member.guild_permissions is not None

    async def test_gateway(self, ctx: InteractionContext, msg):
        gateway: WebsocketClient = self.bot._connection_state.gateway

        assert gateway._entered
        assert gateway._keep_alive is not None

        await self.bot.change_presence(Status.DO_NOT_DISTURB, activity="Testing")
        await self.bot.change_presence()

        await gateway.send_heartbeat()
        await gateway._acknowledged.wait()

    async def test_ratelimit(self, ctx: InteractionContext, msg):
        await append_edit(msg, "- Abusing the api... please wait")
        await msg.add_reaction("🤔")
        await msg.remove_reaction("🤔")

        limit = self.bot.http.get_ratelimit(
            Route(
                "DELETE",
                "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
                channel_id=msg.channel.id,
                message_id=msg.id,
                emoji=process_emoji_req_format("🤔"),
            )
        )
        await msg.add_reaction("🤔")
        await msg.remove_reaction("🤔")
        assert limit.locked
        await msg.add_reaction("🤔")
        await msg.remove_reaction("🤔")
        assert limit.locked

    async def test_embeds(self, ctx: InteractionContext, msg):
        thread = await msg.create_thread("Test Thread")

        try:
            e = Embed("Test")
            await thread.send(embeds=e)

            e = Embed(
                "Test",
                "Test",
                BrandColors.RED,
                "https://github.com/",
                datetime.now(),
                [
                    EmbedField("name", "value"),
                    EmbedField("name2", "value2"),
                    EmbedField("name3", "value3"),
                ],
                EmbedAuthor(self.bot.user.display_name, self.bot.user.avatar.url),
                EmbedAttachment(self.bot.user.avatar.url),
                EmbedAttachment(self.bot.owner.avatar.url),
                footer=EmbedFooter("Test", icon_url=self.bot.user.avatar.url),
            )
            await thread.send(embeds=e)

            e = Embed("Test")
            e.color = BrandColors.RED
            e.url = "https://github.com/"
            e.timestamp = datetime.now()
            e.set_image(self.bot.user.avatar.url)
            e.set_thumbnail(self.bot.user.avatar.url)
            e.set_author("Test", self.bot.owner.avatar.url)
            e.set_footer("Test")
            e.add_field("test", "test")
            e.add_field("test2", "test2")
            await thread.send(embeds=e)

            await thread.delete()
        finally:
            try:
                await thread.delete()
            except dis_snek.errors.NotFound:
                pass

    async def test_components(self, ctx: InteractionContext, msg):
        thread = await msg.create_thread("Test Thread")

        try:
            await thread.send("Test - single", components=dis_snek.Button(1, "test"))
            await thread.send(
                "Test - list",
                components=[dis_snek.Button(1, "test"), dis_snek.Button(1, "test")],
            )
            await thread.send(
                "Test - ActionRow",
                components=dis_snek.ActionRow(
                    *[dis_snek.Button(1, "test"), dis_snek.Button(1, "test")]
                ),
            )
            await thread.send(
                "Test - Select",
                components=dis_snek.Select([SelectOption("test", "test")]),
            )

            modal = Modal(
                "Test Modal", [ParagraphText("test", value="test value, press send")]
            )
            _m = await thread.send(
                f"Test - Modal- {ctx.author.mention} look here!",
                components=dis_snek.Button(1, "Modal", custom_id="modal"),
            )
            await append_edit(msg, "- Waiting for user action...")
            b_ctx = await self.bot.wait_for_component(_m)
            await b_ctx.context.send_modal(modal)
            modal_ctx = await self.bot.wait_for_modal(modal)
            await modal_ctx.send("Thanks!", ephemeral=True)

        finally:
            try:
                await thread.delete()
            except dis_snek.errors.NotFound:
                pass

    async def test_webhooks(self, ctx: InteractionContext, msg):
        test_channel = await ctx.guild.create_text_channel("_test_webhooks")
        test_thread = await test_channel.create_thread("Test Thread")

        try:
            hook = await test_channel.create_webhook("Test")
            await hook.send("Test 123")
            await hook.delete()

            hook = await test_channel.create_webhook(
                "Test-Avatar", r"tests/LordOfPolls.png"
            )

            _m = await hook.send("Test", wait=True)
            assert isinstance(_m, Message)
            assert _m.webhook_id == hook.id
            await hook.send("Test", username="Different Name", wait=True)
            await hook.send("Test", avatar_url=self.bot.user.avatar.url, wait=True)
            _m = await hook.send("Test", thread=test_thread, wait=True)
            assert _m.channel == test_thread

            await hook.delete()
        finally:
            await test_channel.delete()

    async def test_voice(self, ctx: InteractionContext, msg):
        test_channel = await ctx.guild.create_voice_channel("_test_voice")
        test_channel_two = await ctx.guild.create_voice_channel("_test_voice_two")

        try:
            vc = await test_channel.connect(deafened=True)
            assert vc == self.bot.get_bot_voice_state(ctx.guild_id)

            audio = AudioVolume("test_audio.mp3")

            vc.play_no_wait(audio)
            await asyncio.sleep(2)

            assert len(vc.current_audio.buffer) != 0
            assert vc.player._sent_payloads != 0

            await vc.move(test_channel_two)
            await asyncio.sleep(2)

            _before = vc.player._sent_payloads

            await test_channel_two.connect(deafened=True)

            await asyncio.sleep(2)

            assert vc.player._sent_payloads != _before

            vc.volume = 1
            await asyncio.sleep(1)
            vc.volume = 0.5

            vc.pause()
            await asyncio.sleep(0.1)
            assert vc.player.paused
            vc.resume()
            await asyncio.sleep(0.1)
            assert not vc.player.paused

            await vc.disconnect()

        finally:
            await test_channel.delete()
            await test_channel_two.delete()


def setup(bot):
    Tests(bot)
