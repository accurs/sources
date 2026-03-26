from aiohttp import web
from datetime import datetime, timezone
from collections import deque
import time


class Api:
    def __init__(self, bot, port: int = 6969):
        self.bot = bot
        self.port = port
        self.start_time = time.time()
        self.latency_history: deque = deque(maxlen=100)
        self.app = web.Application()
        self._register_routes()

    def _register_routes(self):
        self.app.router.add_get("/guilds", self.get_guilds)
        self.app.router.add_get("/commands", self.get_commands)
        self.app.router.add_get("/stats", self.get_stats)
        self.app.router.add_get("/avatar", self.get_avatar)

    async def get_guilds(self, request: web.Request) -> web.Response:
        try:
            guilds_data = []
            for guild in self.bot.guilds:
                guilds_data.append({
                    "id": str(guild.id),
                    "name": guild.name,
                    "icon_url": str(guild.icon.url) if guild.icon else None,
                    "member_count": guild.member_count,
                })

            return web.json_response({
                "success": True,
                "amount": len(guilds_data),
                "guilds": guilds_data,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def get_commands(self, request: web.Request) -> web.Response:
        try:
            prefix = getattr(self.bot, "command_prefix", ",,")
            if callable(prefix):
                prefix = ",,"

            commands_data = []
            for command in self.bot.walk_commands():
                if command.hidden:
                    continue
                cmd_data = {
                    "name": command.name,
                    "qualified_name": command.qualified_name,
                    "aliases": list(command.aliases) if command.aliases else [],
                    "description": command.help or command.short_doc or "No description available",
                    "usage": command.usage or "",
                    "signature": command.signature,
                    "category": command.cog.qualified_name if command.cog else "No Category",
                    "syntax": f"{prefix}{command.qualified_name} {command.signature}".strip(),
                }
                commands_data.append(cmd_data)

            commands_by_category: dict = {}
            for cmd in commands_data:
                commands_by_category.setdefault(cmd["category"], []).append(cmd)

            return web.json_response({
                "success": True,
                "prefix": prefix,
                "total_commands": len(commands_data),
                "commands": commands_data,
                "commands_by_category": commands_by_category,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def get_stats(self, request: web.Request) -> web.Response:
        try:
            current_latency = round(self.bot.latency * 1000) if self.bot.is_ready() else -1
            self.latency_history.append(current_latency)
            valid = [l for l in self.latency_history if l > 0]
            avg_latency = round(sum(valid) / len(valid), 1) if valid else 0

            return web.json_response({
                "success": True,
                "guilds": len(self.bot.guilds),
                "users": sum(g.member_count for g in self.bot.guilds),
                "latency": max(current_latency, 0),
                "avg_latency": avg_latency,
                "uptime": int(time.time() - self.start_time),
                "status": "online" if self.bot.is_ready() else "offline",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def get_avatar(self, request: web.Request) -> web.Response:
        try:
            avatar_url = self.bot.user.display_avatar.url if self.bot.user else None
            if not avatar_url:
                return web.Response(status=404)
            return web.Response(status=302, headers={"Location": str(avatar_url)})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        print(f"[API] Server started on http://0.0.0.0:{self.port}")

    def run(self):
        web.run_app(self.app, host="0.0.0.0", port=self.port)
