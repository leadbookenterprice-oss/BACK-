TEMPLATE_IDS = (
    'costa_serena',
    'oliva_natural',
    'terracota_suave',
    'brisa_calida',
    'arena_clara',
    'dubai_night',
    'beverly_hills',
    'manhattan',
    'mediterraneo',
    'tech_modern',
)

BASE_LAYOUT_BY_TEMPLATE = {
    'costa_serena': 'mediterraneo',
    'oliva_natural': 'beverly_hills',
    'terracota_suave': 'dubai_night',
    'brisa_calida': 'manhattan',
    'arena_clara': 'tech_modern',
    'dubai_night': 'dubai_night',
    'beverly_hills': 'beverly_hills',
    'manhattan': 'manhattan',
    'mediterraneo': 'mediterraneo',
    'tech_modern': 'tech_modern',
}

TEMPLATE_CONTRACTS = {
    'costa_serena': {
        'name': 'Costa Serena',
        'description': 'Mediterraneo luminoso con azules costeros y arena suave.',
        'base_layout': 'mediterraneo',
        'style': 'mediterranean_light',
        'colors': {
            'primary': '#2f5d73',
            'secondary': '#4d7f96',
            'accent': '#d3a45f',
            'background': '#f5f1ea',
            'text': '#23333b',
        },
        'fonts': {'display': 'Libre Baskerville', 'body': 'Lato', 'mono': 'Lato'},
    },
    'oliva_natural': {
        'name': 'Oliva Natural',
        'description': 'Residencial calido con tonos olivo y acento piedra.',
        'base_layout': 'beverly_hills',
        'style': 'organic_editorial',
        'colors': {
            'primary': '#5c6d4a',
            'secondary': '#7f8f66',
            'accent': '#c89a58',
            'background': '#f7f3ea',
            'text': '#2f3426',
        },
        'fonts': {'display': 'Cormorant Garamond', 'body': 'Lato', 'mono': 'Lato'},
    },
    'terracota_suave': {
        'name': 'Terracota Suave',
        'description': 'Tonos tierra elegantes para una comunicacion acogedora.',
        'base_layout': 'dubai_night',
        'style': 'warm_luxury',
        'colors': {
            'primary': '#7a4a36',
            'secondary': '#9a654e',
            'accent': '#d79a63',
            'background': '#f6eee7',
            'text': '#3a281f',
        },
        'fonts': {'display': 'Libre Baskerville', 'body': 'DM Sans', 'mono': 'DM Sans'},
    },
    'brisa_calida': {
        'name': 'Brisa Calida',
        'description': 'Estilo mediterraneo comercial con clima claro y amable.',
        'base_layout': 'manhattan',
        'style': 'coastal_commercial',
        'colors': {
            'primary': '#46606b',
            'secondary': '#6f8892',
            'accent': '#e0ad67',
            'background': '#fbf7f0',
            'text': '#24343a',
        },
        'fonts': {'display': 'Playfair Display', 'body': 'Lato', 'mono': 'DM Sans'},
    },
    'arena_clara': {
        'name': 'Arena Clara',
        'description': 'Minimal calido con acentos dorados suaves.',
        'base_layout': 'tech_modern',
        'style': 'warm_minimal',
        'colors': {
            'primary': '#6b5b49',
            'secondary': '#8a785f',
            'accent': '#cda66d',
            'background': '#f9f5ee',
            'text': '#332a20',
        },
        'fonts': {'display': 'Cormorant Garamond', 'body': 'DM Sans', 'mono': 'DM Sans'},
    },
    'dubai_night': {
        'name': 'Dubai Night',
        'description': 'Lujo nocturno con contraste alto y acento dorado.',
        'base_layout': 'dubai_night',
        'style': 'dark_luxury',
        'colors': {
            'primary': '#1a0a2e',
            'secondary': '#2d1b4e',
            'accent': '#c9a84c',
            'background': '#080808',
            'text': '#f5f3ee',
        },
        'fonts': {'display': 'Playfair Display', 'body': 'Inter', 'mono': 'Space Mono'},
    },
    'beverly_hills': {
        'name': 'Beverly Hills',
        'description': 'Editorial elegante, limpio y sofisticado.',
        'base_layout': 'beverly_hills',
        'style': 'editorial',
        'colors': {
            'primary': '#2c3e50',
            'secondary': '#34495e',
            'accent': '#e8c547',
            'background': '#fafaf8',
            'text': '#20242a',
        },
        'fonts': {'display': 'Cormorant Garamond', 'body': 'DM Sans', 'mono': 'DM Sans'},
    },
    'manhattan': {
        'name': 'Manhattan',
        'description': 'Urbano industrial, fuerte y de alto impacto.',
        'base_layout': 'manhattan',
        'style': 'urban_strong',
        'colors': {
            'primary': '#111111',
            'secondary': '#1a1a1a',
            'accent': '#e63946',
            'background': '#101010',
            'text': '#f3f3f3',
        },
        'fonts': {'display': 'Oswald', 'body': 'Source Sans 3', 'mono': 'Oswald'},
    },
    'mediterraneo': {
        'name': 'Mediterraneo',
        'description': 'Calido, residencial y organico con tonos tierra.',
        'base_layout': 'mediterraneo',
        'style': 'mediterranean_warm',
        'colors': {
            'primary': '#6b4423',
            'secondary': '#8b5e3c',
            'accent': '#c17f3a',
            'background': '#f8f4ef',
            'text': '#2c2416',
        },
        'fonts': {'display': 'Libre Baskerville', 'body': 'Lato', 'mono': 'Lato'},
    },
    'tech_modern': {
        'name': 'Tech Modern',
        'description': 'Estetica digital premium con acento neon.',
        'base_layout': 'tech_modern',
        'style': 'tech_modern',
        'colors': {
            'primary': '#0d47a1',
            'secondary': '#1565c0',
            'accent': '#00e5ff',
            'background': '#081421',
            'text': '#e8f3ff',
        },
        'fonts': {'display': 'Space Grotesk', 'body': 'Space Grotesk', 'mono': 'Space Mono'},
    },
}

REQUIRED_PDF_SECTIONS = (
    'hero',
    'price',
    'stats',
    'description',
    'amenities',
    'gallery',
    'contact',
)


def normalize_template_id(value):
    if not value:
        return None
    template_id = str(value).strip().lower()
    template_id = (
        template_id
        .replace('template_', '')
        .replace('post_', '')
        .replace('story_', '')
        .replace('carousel_', '')
        .replace('carrusel_', '')
        .replace('email_', '')
        .replace('.html', '')
    )
    return template_id if template_id in TEMPLATE_CONTRACTS else None


def get_template_contract(template_id):
    normalized = normalize_template_id(template_id)
    if not normalized:
        return None
    contract = dict(TEMPLATE_CONTRACTS[normalized])
    contract['id'] = normalized
    contract['required_pdf_sections'] = REQUIRED_PDF_SECTIONS
    contract['base_layout'] = BASE_LAYOUT_BY_TEMPLATE.get(normalized, contract.get('base_layout', normalized))
    return contract


def template_catalog_from_contracts():
    catalog = {}
    for template_id in TEMPLATE_IDS:
        contract = get_template_contract(template_id)
        catalog[template_id] = {
            'name': contract['name'],
            'description': contract['description'],
            'colors': contract['colors'],
            'fonts': contract['fonts'],
            'base_layout': contract['base_layout'],
            'style': contract['style'],
            'contract_valid': True,
        }
    return catalog


def build_pdf_contract_text(template_id):
    contract = get_template_contract(template_id)
    if not contract:
        return ''
    colors = contract['colors']
    fonts = contract['fonts']
    sections = ', '.join(REQUIRED_PDF_SECTIONS)
    return (
        f"template_id={contract['id']}; name={contract['name']}; base_layout={contract['base_layout']}; "
        f"style={contract['style']}; colors primary={colors['primary']}, secondary={colors['secondary']}, "
        f"accent={colors['accent']}, background={colors['background']}, text={colors['text']}; "
        f"fonts display={fonts['display']}, body={fonts['body']}, mono={fonts['mono']}; "
        f"required_sections={sections}."
    )
