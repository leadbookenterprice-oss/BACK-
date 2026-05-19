from decouple import config


def get_video_profile(tipo_video: str, is_land: bool = False) -> dict:
    tv = (tipo_video or "reel").lower()

    if tv == "tour":
        return {
            "min_duration": float(config("VIDEO_MIN_DURATION_TOUR", default=55)),
            "scene_min": 6.5,
            "first_overlap": 1.15,
            "music_volume": 0.09,
            "sfx_volume": 0.12,
            "caption_chunk_size": 7,
            "caption_min_duration": 1.35,
            "zoom_scale": 1.018,
            "cut_flash_opacity": 0.18,
            "cut_flash_duration": 0.22,
            "cut_fade_duration": 0.55,
            "camera_sfx_volume": 0.0,
            "caption_anim": "tour",
        }

    # reel default
    if is_land:
        return {
            "min_duration": float(config("VIDEO_MIN_DURATION_REEL", default=20)),
            "scene_min": 3.1,
            "first_overlap": 0.45,
            "music_volume": 0.11,
            "sfx_volume": 0.30,
            "caption_chunk_size": 4,
            "caption_min_duration": 0.90,
            "zoom_scale": 1.028,
            "cut_flash_opacity": 0.42,
            "cut_flash_duration": 0.08,
            "cut_fade_duration": 0.18,
            "camera_sfx_volume": 0.28,
            "caption_anim": "reel",
        }

    return {
        "min_duration": float(config("VIDEO_MIN_DURATION_REEL", default=20)),
        "scene_min": 2.8,
        "first_overlap": 0.45,
        "music_volume": 0.13,
        "sfx_volume": 0.34,
        "caption_chunk_size": 4,
        "caption_min_duration": 0.80,
        "zoom_scale": 1.035,
        "cut_flash_opacity": 0.62,
        "cut_flash_duration": 0.06,
        "cut_fade_duration": 0.14,
        "camera_sfx_volume": 0.65,
        "caption_anim": "reel",
    }


def get_visual_theme(is_land: bool, tone: str = "profesional") -> dict:
    t = (tone or "profesional").lower()

    if is_land:
        return {
            "caption_bg": "rgba(8, 22, 12, 0.76)",
            "caption_primary": "#E8F5E9",
            "caption_accent": "#C8E6C9",
            "caption_stroke": "rgba(0, 0, 0, 0.60)",
            "cta_border": "#81C784",
            "cta_accent": "#A5D6A7",
            "caption_top": "1228px",
            "caption_size": "70px",
            "cta_top": "1435px",
        }

    if t == "lujo":
        return {
            "caption_bg": "rgba(24, 16, 6, 0.78)",
            "caption_primary": "#F9F3E8",
            "caption_accent": "#E7C97A",
            "caption_stroke": "rgba(0, 0, 0, 0.58)",
            "cta_border": "#E7C97A",
            "cta_accent": "#F3DFA6",
            "caption_top": "1238px",
            "caption_size": "72px",
            "cta_top": "1444px",
        }

    if t == "energetico":
        return {
            "caption_bg": "rgba(6, 10, 24, 0.74)",
            "caption_primary": "#F4F8FF",
            "caption_accent": "#76D1FF",
            "caption_stroke": "rgba(0, 0, 0, 0.62)",
            "cta_border": "#3CCBFF",
            "cta_accent": "#8EE7FF",
            "caption_top": "1218px",
            "caption_size": "76px",
            "cta_top": "1432px",
        }

    return {
        "caption_bg": "rgba(0, 0, 0, 0.72)",
        "caption_primary": "#FFFFFF",
        "caption_accent": "#FFD700",
        "caption_stroke": "rgba(0, 0, 0, 0.55)",
        "cta_border": "#FFD700",
        "cta_accent": "#00E5FF",
        "caption_top": "1249px",
        "caption_size": "74px",
        "cta_top": "1450px",
    }
