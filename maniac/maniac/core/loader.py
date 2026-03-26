import os
from pathlib import Path

async def load_cogs(bot):
    plugins_dir = Path("maniac/plugins")
    
    for folder in plugins_dir.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        
        for file in folder.iterdir():
            if file.suffix == ".py" and not file.name.startswith("_"):
                extension = f"maniac.plugins.{folder.name}.{file.stem}"
                try:
                    await bot.load_extension(extension)
                    print(f"Loaded: {extension}")
                except Exception as e:
                    print(f"Failed to load {extension}: {e}")
