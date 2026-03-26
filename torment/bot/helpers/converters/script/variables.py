import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, cast

from discord import (
    Asset,
    Color,
    Guild,
    Member,
    Role,
    Status,
    TextChannel,
    Thread,
    User,
    VoiceChannel,
)
from pydantic import BaseModel

Block = Union[Member, User, Role, Guild, VoiceChannel, TextChannel, Thread, BaseModel, str]

pattern = re.compile(r"(?<!\\)\{([a-zA-Z0-9_.]+)\}")


def to_dict(
    block: Block,
    _key: Optional[str] = None,
) -> Dict[str, str]:
    origin = block.__class__.__name__.lower()
    key = _key or getattr(block, "variable", origin)
    key = "user" if key == "member" else "channel" if "channel" in key else key

    data: Dict[str, str] = {key: str(block)}

    for name in dir(block):
        if name.startswith("_"):
            continue

        try:
            value = getattr(block, name)
        except (ValueError, AttributeError):
            continue

        if callable(value):
            continue

        if value is None:
            data[f"{key}.{name}"] = "None"
            continue

        if isinstance(value, datetime):
            data[f"{key}.{name}"] = str(int(value.timestamp()))
        elif isinstance(value, timedelta):
            total_seconds = int(value.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                data[f"{key}.{name}"] = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                data[f"{key}.{name}"] = f"{minutes}m {seconds}s"
            else:
                data[f"{key}.{name}"] = f"{seconds}s"
        elif isinstance(value, int):
            data[f"{key}.{name}"] = (
                format(value, ",")
                if not name.endswith(("id", "duration"))
                else str(value)
            )
        elif isinstance(value, (str, bool, Status, Asset, Color)):
            data[f"{key}.{name}"] = str(value)
        elif isinstance(value, (Member, User, Role)):
            data[f"{key}.{name}"] = str(value)
        elif isinstance(value, (list, tuple)):
            if hasattr(value, "__iter__") and not isinstance(value, str):
                try:
                    if all(hasattr(item, "mention") for item in value):
                        data[f"{key}.{name}"] = ", ".join(
                            item.mention for item in value
                        )
                    elif all(hasattr(item, "name") for item in value):
                        data[f"{key}.{name}"] = ", ".join(item.name for item in value)
                    else:
                        data[f"{key}.{name}"] = ", ".join(str(item) for item in value)
                except (AttributeError, TypeError):
                    data[f"{key}.{name}"] = str(value)
        elif isinstance(value, BaseModel):
            base_model_data = to_dict(value)
            for __key, val in base_model_data.items():
                data[f"{key}.{__key}"] = val

    if "user.display_avatar" in data:
        data["user.avatar"] = data["user.display_avatar"]

    if isinstance(block, Guild):
        if block.owner:
            data[f"{key}.owner_mention"] = block.owner.mention
            data[f"{key}.owner_id"] = str(block.owner.id)

        if hasattr(block, "roles") and block.roles:
            data[f"{key}.roles"] = ", ".join(
                role.mention for role in reversed(block.roles)
            )

        data[f"{key}.emoji_count"] = format(len(block.emojis), ",")
        data[f"{key}.role_count"] = format(len(block.roles), ",")
        data[f"{key}.role_ids"] = ", ".join(
            str(role.id) for role in reversed(block.roles)
        )
        data[f"{key}.text_channel_count"] = format(len(block.text_channels), ",")
        data[f"{key}.voice_channel_count"] = format(len(block.voice_channels), ",")
        data[f"{key}.category_channel_count"] = format(len(block.categories), ",")
        data[f"{key}.boost_count"] = format(block.premium_subscription_count, ",")
        data[f"{key}.boost_level"] = str(block.premium_tier)

    elif isinstance(block, Member):
        data[f"{key}.booster"] = str(bool(block.premium_since))
        if block.premium_since:
            data[f"{key}.booster_since"] = str(block.premium_since)
            data[f"{key}.booster_since_timestamp"] = str(
                int(block.premium_since.timestamp())
            )
        else:
            data[f"{key}.booster_since"] = "0"
            data[f"{key}.booster_since_timestamp"] = "0"

        if block.joined_at:
            data[f"{key}.joined_at_timestamp"] = str(int(block.joined_at.timestamp()))

        data[f"{key}.role_ids"] = ", ".join(
            str(role.id) for role in reversed(block.roles[1:])
        )

    elif isinstance(block, (TextChannel, Thread)):
        if hasattr(block, "slowmode_delay"):
            data[f"{key}.slowmode"] = str(block.slowmode_delay)

    return data


def parse(string: str, blocks: List[Block | Tuple[str, Block]] = [], **kwargs) -> str:
    blocks.extend(kwargs.items())
    string = string.replace("{embed}", "{embed:0}")

    variables: Dict[str, str] = {}
    for block in blocks:
        if isinstance(block, tuple):
            variables.update(to_dict(block[1], block[0]))
            continue

        variables.update(to_dict(block))

    def replace(match: re.Match) -> str:
        name = cast(str, match[1])

        if name == "author":
            name = "user"
        elif name == "member":
            name = "user"
        elif name.startswith("author."):
            name = name.replace("author.", "user.", 1)
        elif name.startswith("member."):
            name = name.replace("member.", "user.", 1)

        value = variables.get(name)
        return value or name

    return pattern.sub(replace, string)
