# generated by datamodel-codegen:
#   filename:  e.json
#   timestamp: 2024-06-19T20:47:50+00:00

from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class AvatarThumb(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class AvatarMedium(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class ShareQrcodeUrl(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class ShareInfo(BaseModel):
    share_url: Optional[str] = None
    share_desc: Optional[str] = None
    share_title: Optional[str] = None
    share_qrcode_url: Optional[ShareQrcodeUrl] = None
    share_title_myself: Optional[str] = None
    share_title_other: Optional[str] = None
    share_desc_info: Optional[str] = None
    now_invitation_card_image_urls: Optional[Any] = None


class VideoIcon(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class Avatar168x168(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class Avatar300x300(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class MatchedFriend(BaseModel):
    video_items: Optional[Any] = None


class Author(BaseModel):
    uid: Optional[str] = None
    short_id: Optional[str] = None
    nickname: Optional[str] = None
    signature: Optional[str] = None
    avatar_thumb: Optional[AvatarThumb] = None
    avatar_medium: Optional[AvatarMedium] = None
    follow_status: Optional[int] = None
    is_block: Optional[bool] = None
    custom_verify: Optional[str] = None
    unique_id: Optional[str] = None
    room_id: Optional[int] = None
    authority_status: Optional[int] = None
    verify_info: Optional[str] = None
    share_info: Optional[ShareInfo] = None
    with_commerce_entry: Optional[bool] = None
    verification_type: Optional[int] = None
    enterprise_verify_reason: Optional[str] = None
    is_ad_fake: Optional[bool] = None
    followers_detail: Optional[Any] = None
    region: Optional[str] = None
    commerce_user_level: Optional[int] = None
    platform_sync_info: Optional[Any] = None
    is_discipline_member: Optional[bool] = None
    secret: Optional[int] = None
    prevent_download: Optional[bool] = None
    geofencing: Optional[Any] = None
    video_icon: Optional[VideoIcon] = None
    follower_status: Optional[int] = None
    comment_setting: Optional[int] = None
    duet_setting: Optional[int] = None
    download_setting: Optional[int] = None
    cover_url: Optional[List] = None
    language: Optional[str] = None
    item_list: Optional[Any] = None
    is_star: Optional[bool] = None
    type_label: Optional[List] = None
    ad_cover_url: Optional[Any] = None
    comment_filter_status: Optional[int] = None
    avatar_168x168: Optional[Avatar168x168] = None
    avatar_300x300: Optional[Avatar300x300] = None
    relative_users: Optional[Any] = None
    cha_list: Optional[Any] = None
    sec_uid: Optional[str] = None
    need_points: Optional[Any] = None
    homepage_bottom_toast: Optional[Any] = None
    can_set_geofencing: Optional[Any] = None
    white_cover_url: Optional[Any] = None
    user_tags: Optional[Any] = None
    bold_fields: Optional[Any] = None
    search_highlight: Optional[Any] = None
    mutual_relation_avatars: Optional[Any] = None
    events: Optional[Any] = None
    matched_friend: Optional[MatchedFriend] = None
    advance_feature_item_order: Optional[Any] = None
    advanced_feature_info: Optional[Any] = None
    user_profile_guide: Optional[Any] = None
    shield_edit_field_info: Optional[Any] = None
    can_message_follow_status_list: Optional[Any] = None
    account_labels: Optional[Any] = None
    social_info: Optional[str] = None


class CoverLarge(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class CoverMedium(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class CoverThumb(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class PlayUrl(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class StrongBeatUrl(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class Music(BaseModel):
    id: Optional[int] = None
    id_str: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    album: Optional[str] = None
    cover_large: Optional[CoverLarge] = None
    cover_medium: Optional[CoverMedium] = None
    cover_thumb: Optional[CoverThumb] = None
    play_url: Optional[PlayUrl] = None
    source_platform: Optional[int] = None
    duration: Optional[int] = None
    extra: Optional[str] = None
    user_count: Optional[int] = None
    position: Optional[Any] = None
    collect_stat: Optional[int] = None
    status: Optional[int] = None
    offline_desc: Optional[str] = None
    owner_id: Optional[str] = None
    owner_nickname: Optional[str] = None
    is_original: Optional[bool] = None
    mid: Optional[str] = None
    binded_challenge_id: Optional[int] = None
    author_deleted: Optional[bool] = None
    owner_handle: Optional[str] = None
    author_position: Optional[Any] = None
    prevent_download: Optional[bool] = None
    external_song_info: Optional[List] = None
    sec_uid: Optional[str] = None
    avatar_thumb: Optional[AvatarThumb] = None
    avatar_medium: Optional[AvatarMedium] = None
    preview_start_time: Optional[int] = None
    preview_end_time: Optional[int] = None
    is_commerce_music: Optional[bool] = None
    is_original_sound: Optional[bool] = None
    artists: Optional[Any] = None
    lyric_short_position: Optional[Any] = None
    mute_share: Optional[bool] = None
    tag_list: Optional[Any] = None
    is_author_artist: Optional[bool] = None
    is_pgc: Optional[bool] = None
    search_highlight: Optional[Any] = None
    multi_bit_rate_play_info: Optional[Any] = None
    tt_to_dsp_song_infos: Optional[Any] = None
    recommend_status: Optional[int] = None
    uncert_artists: Optional[Any] = None
    strong_beat_url: Optional[StrongBeatUrl] = None


class Author1(BaseModel):
    followers_detail: Optional[Any] = None
    platform_sync_info: Optional[Any] = None
    geofencing: Optional[Any] = None
    cover_url: Optional[Any] = None
    item_list: Optional[Any] = None
    type_label: Optional[Any] = None
    ad_cover_url: Optional[Any] = None
    relative_users: Optional[Any] = None
    cha_list: Optional[Any] = None
    need_points: Optional[Any] = None
    homepage_bottom_toast: Optional[Any] = None
    can_set_geofencing: Optional[Any] = None
    white_cover_url: Optional[Any] = None
    user_tags: Optional[Any] = None
    bold_fields: Optional[Any] = None
    search_highlight: Optional[Any] = None
    mutual_relation_avatars: Optional[Any] = None
    events: Optional[Any] = None
    advance_feature_item_order: Optional[Any] = None
    advanced_feature_info: Optional[Any] = None
    user_profile_guide: Optional[Any] = None
    shield_edit_field_info: Optional[Any] = None
    can_message_follow_status_list: Optional[Any] = None
    account_labels: Optional[Any] = None


class ShareInfo1(BaseModel):
    share_url: Optional[str] = None
    share_desc: Optional[str] = None
    share_title: Optional[str] = None
    bool_persist: Optional[int] = None
    share_title_myself: Optional[str] = None
    share_title_other: Optional[str] = None
    share_signature_url: Optional[str] = None
    share_signature_desc: Optional[str] = None
    share_quote: Optional[str] = None
    share_desc_info: Optional[str] = None
    now_invitation_card_image_urls: Optional[Any] = None


class ChaListItem(BaseModel):
    cid: Optional[str] = None
    cha_name: Optional[str] = None
    desc: Optional[str] = None
    schema_: Optional[str] = Field(None, alias="schema")
    author: Optional[Author1] = None
    user_count: Optional[int] = None
    share_info: Optional[ShareInfo1] = None
    connect_music: Optional[List] = None
    type: Optional[int] = None
    sub_type: Optional[int] = None
    is_pgcshow: Optional[bool] = None
    collect_stat: Optional[int] = None
    is_challenge: Optional[int] = None
    view_count: Optional[int] = None
    is_commerce: Optional[bool] = None
    hashtag_profile: Optional[str] = None
    cha_attrs: Optional[Any] = None
    banner_list: Optional[Any] = None
    show_items: Optional[Any] = None
    search_highlight: Optional[Any] = None


class PlayAddr(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_key: Optional[str] = None
    data_size: Optional[int] = None
    file_hash: Optional[str] = None
    url_prefix: Optional[Any] = None


class Cover(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class DynamicCover(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class OriginCover(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class DownloadAddr(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    data_size: Optional[int] = None
    url_prefix: Optional[Any] = None


class BitRateItem(BaseModel):
    gear_name: Optional[str] = None
    quality_type: Optional[int] = None
    bit_rate: Optional[int] = None
    play_addr: Optional[PlayAddr] = None
    is_bytevc1: Optional[int] = None
    dub_infos: Optional[Any] = None
    HDR_type: Optional[str] = None
    HDR_bit: Optional[str] = None


class PlayAddrH264(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_key: Optional[str] = None
    data_size: Optional[int] = None
    file_hash: Optional[str] = None
    url_prefix: Optional[Any] = None


class PlayAddrBytevc1(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_key: Optional[str] = None
    data_size: Optional[int] = None
    file_hash: Optional[str] = None
    url_prefix: Optional[Any] = None


class Video1(BaseModel):
    play_addr: Optional[PlayAddr] = None
    cover: Optional[Cover] = None
    height: Optional[int] = None
    width: Optional[int] = None
    dynamic_cover: Optional[DynamicCover] = None
    origin_cover: Optional[OriginCover] = None
    ratio: Optional[str] = None
    download_addr: Optional[DownloadAddr] = None
    has_watermark: Optional[bool] = None
    bit_rate: Optional[List[BitRateItem]] = None
    duration: Optional[int] = None
    play_addr_h264: Optional[PlayAddrH264] = None
    cdn_url_expired: Optional[int] = None
    need_set_token: Optional[bool] = None
    CoverTsp: Optional[Any] = None
    misc_download_addrs: Optional[str] = None
    tags: Optional[Any] = None
    big_thumbs: Optional[Any] = None
    play_addr_bytevc1: Optional[PlayAddrBytevc1] = None
    is_bytevc1: Optional[int] = None
    meta: Optional[str] = None
    source_HDR_type: Optional[int] = None
    bit_rate_audio: Optional[List] = None


class Statistics(BaseModel):
    aweme_id: Optional[str] = None
    comment_count: Optional[int] = None
    digg_count: Optional[int] = None
    download_count: Optional[int] = None
    play_count: Optional[int] = None
    share_count: Optional[int] = None
    forward_count: Optional[int] = None
    lose_count: Optional[int] = None
    lose_comment_count: Optional[int] = None
    whatsapp_share_count: Optional[int] = None
    collect_count: Optional[int] = None
    repost_count: Optional[int] = None


class Status(BaseModel):
    aweme_id: Optional[str] = None
    is_delete: Optional[bool] = None
    allow_share: Optional[bool] = None
    allow_comment: Optional[bool] = None
    is_private: Optional[bool] = None
    with_goods: Optional[bool] = None
    private_status: Optional[int] = None
    in_reviewing: Optional[bool] = None
    reviewed: Optional[int] = None
    self_see: Optional[bool] = None
    is_prohibited: Optional[bool] = None
    download_status: Optional[int] = None


class TextExtraItem(BaseModel):
    start: Optional[int] = None
    end: Optional[int] = None
    user_id: Optional[str] = None
    type: Optional[int] = None
    hashtag_name: Optional[str] = None
    hashtag_id: Optional[str] = None
    is_commerce: Optional[bool] = None
    sec_uid: Optional[str] = None


class LabelTop(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class ShareInfo2(BaseModel):
    share_url: Optional[str] = None
    share_desc: Optional[str] = None
    share_title: Optional[str] = None
    bool_persist: Optional[int] = None
    share_title_myself: Optional[str] = None
    share_title_other: Optional[str] = None
    share_link_desc: Optional[str] = None
    share_signature_url: Optional[str] = None
    share_signature_desc: Optional[str] = None
    share_quote: Optional[str] = None
    share_desc_info: Optional[str] = None
    now_invitation_card_image_urls: Optional[Any] = None
    share_button_display_mode: Optional[int] = None
    button_display_stratege_source: Optional[str] = None


class RiskInfos(BaseModel):
    vote: Optional[bool] = None
    warn: Optional[bool] = None
    risk_sink: Optional[bool] = None
    type: Optional[int] = None
    content: Optional[str] = None


class TextStickerInfo(BaseModel):
    text_size: Optional[int] = None
    text_color: Optional[str] = None
    bg_color: Optional[str] = None
    text_language: Optional[str] = None
    alignment: Optional[int] = None
    source_width: Optional[float] = None
    source_height: Optional[float] = None


class InteractionSticker(BaseModel):
    type: Optional[int] = None
    index: Optional[int] = None
    track_info: Optional[str] = None
    attr: Optional[str] = None
    text_info: Optional[str] = None
    text_sticker_info: Optional[TextStickerInfo] = None


class VideoControl(BaseModel):
    allow_download: Optional[bool] = None
    share_type: Optional[int] = None
    show_progress_bar: Optional[int] = None
    draft_progress_bar: Optional[int] = None
    allow_duet: Optional[bool] = None
    allow_react: Optional[bool] = None
    prevent_download_type: Optional[int] = None
    allow_dynamic_wallpaper: Optional[bool] = None
    timer_status: Optional[int] = None
    allow_music: Optional[bool] = None
    allow_stitch: Optional[bool] = None


class CommerceInfo(BaseModel):
    adv_promotable: Optional[bool] = None
    branded_content_type: Optional[int] = None


class Icon(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class Thumbnail(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class Action(BaseModel):
    icon: Optional[Icon] = None
    schema_: Optional[str] = Field(None, alias="schema")
    action_type: Optional[int] = None


class Anchor(BaseModel):
    keyword: Optional[str] = None
    id: Optional[str] = None
    type: Optional[int] = None
    icon: Optional[Icon] = None
    extra: Optional[str] = None
    log_extra: Optional[str] = None
    description: Optional[str] = None
    thumbnail: Optional[Thumbnail] = None
    actions: Optional[List[Action]] = None
    component_key: Optional[str] = None
    anchor_strong: Optional[Any] = None


class DownloadGeneral(BaseModel):
    code: Optional[int] = None
    show_type: Optional[int] = None
    transcode: Optional[int] = None
    mute: Optional[bool] = None
    extra: Optional[str] = None


class DownloadMaskPanel(BaseModel):
    code: Optional[int] = None
    show_type: Optional[int] = None
    transcode: Optional[int] = None
    mute: Optional[bool] = None
    extra: Optional[str] = None


class ShareGeneral(BaseModel):
    code: Optional[int] = None
    show_type: Optional[int] = None
    transcode: Optional[int] = None
    mute: Optional[bool] = None
    extra: Optional[str] = None


class AwemeAcl(BaseModel):
    download_general: Optional[DownloadGeneral] = None
    download_mask_panel: Optional[DownloadMaskPanel] = None
    share_list_status: Optional[int] = None
    share_general: Optional[ShareGeneral] = None
    platform_list: Optional[Any] = None
    share_action_list: Optional[Any] = None
    press_action_list: Optional[Any] = None


class AllowCreateSticker(BaseModel):
    status: Optional[int] = None


class InteractPermission(BaseModel):
    duet: Optional[int] = None
    stitch: Optional[int] = None
    duet_privacy_setting: Optional[int] = None
    stitch_privacy_setting: Optional[int] = None
    upvote: Optional[int] = None
    allow_adding_to_story: Optional[int] = None
    allow_create_sticker: Optional[AllowCreateSticker] = None


class ContentDescExtraItem(BaseModel):
    start: Optional[int] = None
    end: Optional[int] = None
    type: Optional[int] = None
    hashtag_name: Optional[str] = None
    hashtag_id: Optional[str] = None
    is_commerce: Optional[bool] = None
    line_idx: Optional[int] = None


class TextExtraItem1(BaseModel):
    type: Optional[int] = None
    hashtag_name: Optional[str] = None
    sub_type: Optional[int] = None
    tag_id: Optional[str] = None
    user_id: Optional[str] = None
    is_commerce: Optional[bool] = None
    sec_uid: Optional[str] = None


class OriginalClientText(BaseModel):
    markup_text: Optional[str] = None
    text_extra: Optional[List[TextExtraItem1]] = None


class CommentConfig(BaseModel):
    emoji_recommend_list: Optional[Any] = None


class AddedSoundMusicInfo(BaseModel):
    id: Optional[int] = None
    id_str: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    album: Optional[str] = None
    cover_large: Optional[CoverLarge] = None
    cover_medium: Optional[CoverMedium] = None
    cover_thumb: Optional[CoverThumb] = None
    play_url: Optional[PlayUrl] = None
    source_platform: Optional[int] = None
    duration: Optional[int] = None
    extra: Optional[str] = None
    user_count: Optional[int] = None
    position: Optional[Any] = None
    collect_stat: Optional[int] = None
    status: Optional[int] = None
    offline_desc: Optional[str] = None
    owner_id: Optional[str] = None
    owner_nickname: Optional[str] = None
    is_original: Optional[bool] = None
    mid: Optional[str] = None
    binded_challenge_id: Optional[int] = None
    author_deleted: Optional[bool] = None
    owner_handle: Optional[str] = None
    author_position: Optional[Any] = None
    prevent_download: Optional[bool] = None
    external_song_info: Optional[List] = None
    sec_uid: Optional[str] = None
    avatar_thumb: Optional[AvatarThumb] = None
    avatar_medium: Optional[AvatarMedium] = None
    preview_start_time: Optional[int] = None
    preview_end_time: Optional[int] = None
    is_commerce_music: Optional[bool] = None
    is_original_sound: Optional[bool] = None
    artists: Optional[Any] = None
    lyric_short_position: Optional[Any] = None
    mute_share: Optional[bool] = None
    tag_list: Optional[Any] = None
    is_author_artist: Optional[bool] = None
    is_pgc: Optional[bool] = None
    search_highlight: Optional[Any] = None
    multi_bit_rate_play_info: Optional[Any] = None
    tt_to_dsp_song_infos: Optional[Any] = None
    recommend_status: Optional[int] = None
    uncert_artists: Optional[Any] = None
    strong_beat_url: Optional[StrongBeatUrl] = None


class LogInfo(BaseModel):
    order: Optional[str] = None


class AigcInfo(BaseModel):
    aigc_label_type: Optional[int] = None


class StickerDetail(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    children: Optional[Any] = None
    owner_id: Optional[str] = None
    tags: Optional[Any] = None
    sec_uid: Optional[str] = None
    linked_anchors: Optional[Any] = None
    attributions: Optional[Any] = None


class DisplayImage(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class OwnerWatermarkImage(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class UserWatermarkImage(BaseModel):
    uri: Optional[str] = None
    url_list: Optional[List[str]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url_prefix: Optional[Any] = None


class Image(BaseModel):
    display_image: Optional[DisplayImage] = None
    owner_watermark_image: Optional[OwnerWatermarkImage] = None
    user_watermark_image: Optional[UserWatermarkImage] = None
    thumbnail: Optional[Thumbnail] = None
    bitrate_images: Optional[Any] = None


class ImagePostCover(BaseModel):
    display_image: Optional[DisplayImage] = None
    owner_watermark_image: Optional[OwnerWatermarkImage] = None
    user_watermark_image: Optional[UserWatermarkImage] = None
    thumbnail: Optional[Thumbnail] = None
    bitrate_images: Optional[Any] = None


class ImagePostInfo(BaseModel):
    images: Optional[List[Image]] = None
    image_post_cover: Optional[ImagePostCover] = None
    post_extra: Optional[str] = None


class AwemeListItem(BaseModel):
    aweme_id: Optional[str] = None
    desc: Optional[str] = None
    create_time: Optional[int] = None
    author: Optional[Author] = None
    music: Optional[Music] = None
    cha_list: Optional[List[ChaListItem]] = None
    video: Optional[Video1] = None
    share_url: Optional[str] = None
    user_digged: Optional[int] = None
    statistics: Optional[Statistics] = None
    status: Optional[Status] = None
    rate: Optional[int] = None
    text_extra: Optional[List[TextExtraItem]] = None
    is_top: Optional[int] = None
    label_top: Optional[LabelTop] = None
    share_info: Optional[ShareInfo2] = None
    distance: Optional[str] = None
    video_labels: Optional[List] = None
    is_vr: Optional[bool] = None
    is_ads: Optional[bool] = None
    aweme_type: Optional[int] = None
    cmt_swt: Optional[bool] = None
    image_infos: Optional[Any] = None
    risk_infos: Optional[RiskInfos] = None
    is_relieve: Optional[bool] = None
    sort_label: Optional[str] = None
    position: Optional[Any] = None
    uniqid_position: Optional[Any] = None
    author_user_id: Optional[int] = None
    bodydance_score: Optional[int] = None
    geofencing: Optional[Any] = None
    is_hash_tag: Optional[int] = None
    is_pgcshow: Optional[bool] = None
    region: Optional[str] = None
    video_text: Optional[List] = None
    collect_stat: Optional[int] = None
    label_top_text: Optional[Any] = None
    group_id: Optional[str] = None
    prevent_download: Optional[bool] = None
    nickname_position: Optional[Any] = None
    challenge_position: Optional[Any] = None
    item_comment_settings: Optional[int] = None
    with_promotional_music: Optional[bool] = None
    long_video: Optional[Any] = None
    item_duet: Optional[int] = None
    item_react: Optional[int] = None
    desc_language: Optional[str] = None
    interaction_stickers: Optional[List[InteractionSticker]] = None
    misc_info: Optional[str] = None
    origin_comment_ids: Optional[Any] = None
    commerce_config_data: Optional[Any] = None
    distribute_type: Optional[int] = None
    video_control: Optional[VideoControl] = None
    has_vs_entry: Optional[bool] = None
    commerce_info: Optional[CommerceInfo] = None
    need_vs_entry: Optional[bool] = None
    anchors: Optional[List[Anchor]] = None
    hybrid_label: Optional[Any] = None
    with_survey: Optional[bool] = None
    geofencing_regions: Optional[Any] = None
    aweme_acl: Optional[AwemeAcl] = None
    cover_labels: Optional[Any] = None
    mask_infos: Optional[List] = None
    search_highlight: Optional[Any] = None
    playlist_blocked: Optional[bool] = None
    green_screen_materials: Optional[Any] = None
    interact_permission: Optional[InteractPermission] = None
    question_list: Optional[Any] = None
    content_desc: Optional[str] = None
    content_desc_extra: Optional[List[ContentDescExtraItem]] = None
    products_info: Optional[Any] = None
    follow_up_publish_from_id: Optional[int] = None
    disable_search_trending_bar: Optional[bool] = None
    music_begin_time_in_ms: Optional[int] = None
    music_end_time_in_ms: Optional[int] = None
    item_distribute_source: Optional[str] = None
    item_source_category: Optional[int] = None
    branded_content_accounts: Optional[Any] = None
    is_description_translatable: Optional[bool] = None
    follow_up_item_id_groups: Optional[str] = None
    is_text_sticker_translatable: Optional[bool] = None
    text_sticker_major_lang: Optional[str] = None
    original_client_text: Optional[OriginalClientText] = None
    music_selected_from: Optional[str] = None
    tts_voice_ids: Optional[Any] = None
    reference_tts_voice_ids: Optional[Union[Any, str]] = None
    voice_filter_ids: Optional[Any] = None
    reference_voice_filter_ids: Optional[Any] = None
    music_title_style: Optional[int] = None
    comment_config: Optional[CommentConfig] = None
    added_sound_music_info: Optional[AddedSoundMusicInfo] = None
    origin_volume: Optional[str] = None
    music_volume: Optional[str] = None
    support_danmaku: Optional[bool] = None
    has_danmaku: Optional[bool] = None
    muf_comment_info_v2: Optional[Any] = None
    behind_the_song_music_ids: Optional[Any] = None
    behind_the_song_video_music_ids: Optional[Any] = None
    content_original_type: Optional[int] = None
    shoot_tab_name: Optional[str] = None
    content_type: Optional[str] = None
    content_size_type: Optional[int] = None
    operator_boost_info: Optional[Any] = None
    log_info: Optional[LogInfo] = None
    main_arch_common: Optional[str] = None
    aigc_info: Optional[AigcInfo] = None
    banners: Optional[Any] = None
    picked_users: Optional[Any] = None
    comment_topbar_info: Optional[Any] = None
    follow_up_first_item_id: Optional[str] = None
    stickers: Optional[str] = None
    sticker_detail: Optional[StickerDetail] = None
    image_post_info: Optional[ImagePostInfo] = None


class Extra(BaseModel):
    now: Optional[int] = None
    fatal_item_ids: Optional[Any] = None
    api_debug_info: Optional[Any] = None


class LogPb(BaseModel):
    impr_id: Optional[str] = None


class LogInfo1(BaseModel):
    impr_id: Optional[str] = None
    pull_type: Optional[str] = None


class Video(BaseModel):
    status_code: Optional[int] = None
    min_cursor: Optional[int] = None
    max_cursor: Optional[int] = None
    has_more: Optional[int] = None
    aweme_list: Optional[List[AwemeListItem]] = None
    home_model: Optional[int] = None
    refresh_clear: Optional[int] = None
    extra: Optional[Extra] = None
    log_pb: Optional[LogPb] = None
    preload_ads: Optional[List] = None
    preload_awemes: Optional[Any] = None
    log_info: Optional[LogInfo1] = None
