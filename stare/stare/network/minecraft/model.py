from pydantic import BaseModel, Field
from typing import Optional, List


class PlayerUUIDResponse(BaseModel):
    """Response model for UUID lookup"""
    name: str = Field(..., description="Player username")
    id: str = Field(..., description="Player UUID (without dashes)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Notch",
                "id": "069a79f444e94726a5befca90e38aaf5"
            }
        }


class TextureProperty(BaseModel):
    """Texture property from player profile"""
    name: str
    value: str # This is Base64.
    signature: Optional[str] = None


class PlayerProfileResponse(BaseModel):
    """Response model for player profile"""
    id: str = Field(..., description="Player UUID (without dashes)")
    name: str = Field(..., description="Player username")
    properties: List[TextureProperty] = Field(default_factory=list, description="Texture properties")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "069a79f444e94726a5befca90e38aaf5",
                "name": "Notch",
                "properties": [
                    {
                        "name": "textures",
                        "value": "eyJ0aW1lc3RhbXAiOjE..."
                    }
                ]
            }
        }


class PlayerAvatarResponse(BaseModel):
    """Response model for player avatar"""
    uuid: str = Field(..., description="Player UUID")
    avatar_url: str = Field(..., description="2D avatar URL")
    size: int = Field(128, description="Avatar size")
    overlay: bool = Field(True, description="Include second skin layer")
    
    class Config:
        json_schema_extra = {
            "example": {
                "uuid": "069a79f444e94726a5befca90e38aaf5",
                "avatar_url": "https://crafatar.com/avatars/069a79f444e94726a5befca90e38aaf5?size=128&overlay=true",
                "size": 128,
                "overlay": True
            }
        }


class PlayerRenderResponse(BaseModel):
    """Response model for player 3D render"""
    uuid: str = Field(..., description="Player UUID")
    render_url: str = Field(..., description="3D render URL")
    skin_url: str = Field(..., description="Full skin PNG URL")
    render_type: str = Field("head", description="Render type (head or body)")
    scale: int = Field(4, description="Render scale")
    overlay: bool = Field(True, description="Include second skin layer")
    
    class Config:
        json_schema_extra = {
            "example": {
                "uuid": "069a79f444e94726a5befca90e38aaf5",
                "render_url": "https://crafatar.com/renders/head/069a79f444e94726a5befca90e38aaf5?scale=4&overlay=true",
                "skin_url": "https://crafatar.com/skins/069a79f444e94726a5befca90e38aaf5",
                "render_type": "head",
                "scale": 4,
                "overlay": True
            }
        }


__all__ = [
    'PlayerUUIDResponse',
    'PlayerProfileResponse',
    'PlayerAvatarResponse',
    'PlayerRenderResponse',
    'TextureProperty'
]
