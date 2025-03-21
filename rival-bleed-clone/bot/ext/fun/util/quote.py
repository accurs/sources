from PILL import Image, ImageDraw, ImageFont
from discord.ext.commands import Context, CommandError
from discord import Message, File
from asyncio import Lock
from collections import defaultdict
from typing import Optional
import textwrap
from io import BytesIO
from lib.worker import offloaded


class Quote:
    def __init__(self, bot):
        self.bot = bot
        self.locks = defaultdict(Lock)

    async def get_caption(self, ctx: Context, message: Optional[Message] = None):
        if message is None:
            msg = ctx.message.reference
            if msg is None:
                raise CommandError("no **message** or **reference** provided")
            id = msg.message_id
            message = await ctx.fetch_message(id)
        image = await message.author.display_avatar.read()
        file_name = "icon.jpeg"
        if message.content.replace("\n", "").isascii():
            para = textwrap.wrap(message.clean_content, width=26)
        else:
            para = textwrap.wrap(message.clean_content, width=13)

        @offloaded
        def do_caption(para, image, content, author):
            from PILL import Image, ImageDraw, ImageFont
            from io import BytesIO

            icon = Image.open(BytesIO(image))
            haikei = Image.open("var/grad.jpeg")
            black = Image.open("var/black.jpeg")
            w, h = (680, 370)
            w1, h1 = icon.size
            haikei = haikei.resize((w, h))
            black = black.resize((w, h))
            icon = icon.resize((h, h))
            new = Image.new(mode="RGBA", size=(w, h))
            icon = icon.convert("RGBA")
            black = black.convert("RGBA")
            haikei = haikei.convert("L")
            new = Image.new(mode="L", size=(w, h))
            icon = icon.convert("L")
            black = black.convert("L")
            icon = icon.crop((40, 0, 680, 370))
            new.paste(icon)
            sa = Image.composite(new, black, haikei)
            draw = ImageDraw.Draw(sa)
            fnt = ImageFont.truetype("var/Arial.ttf", 28)
            w2, h2 = draw.textsize("a", font=fnt)
            i = (int(len(para) / 2) * w2) + len(para) * 5
            current_h, pad = 120 - i, 0
            for line in para:
                if content.replace("\n", "").isascii():
                    w3, h3 = draw.textsize(
                        line.ljust(int(len(line) / 2 + 11), " "), font=fnt
                    )
                    draw.text(
                        (11 * (w - w3) / 13 + 10, current_h + h2),
                        line.ljust(int(len(line) / 2 + 11), " "),
                        font=fnt,
                        fill="#FFF",
                    )
                else:
                    w3, h3 = draw.textsize(
                        line.ljust(int(len(line) / 2 + 5), "　"), font=fnt
                    )
                    draw.text(
                        (11 * (w - w3) / 13 + 10, current_h + h2),
                        line.ljust(int(len(line) / 2 + 5), "　"),
                        font=fnt,
                        fill="#FFF",
                    )
                current_h += h3 + pad
            dr = ImageDraw.Draw(sa)
            font = ImageFont.truetype("var/Arial.ttf", 15)
            authorw, authorh = dr.textsize(f"-{str(author)}", font=font)
            output = BytesIO()
            dr.text(
                (480 - int(authorw / 2), current_h + h2 + 10),
                f"-{str(author)}",
                font=font,
                fill="#FFF",
            )
            sa.save(output, format="JPEG")
            output.seek(0)
            return output.read()

        output = await do_caption(para, image, message.content, str(message.author))
        file = File(fp=BytesIO(output), filename="quote.png")
        return await ctx.send(file=file)
