from typing import Optional
from pydantic import BaseModel


class ScreenshotResponse(BaseModel):
    url: str
    screenshot: str 
    width: str
    height: str
    format: str
    fullpage: Optional[str] = None
