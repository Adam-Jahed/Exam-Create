"""Inline theme CSS for Exam Create."""

LIGHT = {
    "bg": "#e9ecef",
    "panel": "#f5f6f8",
    "text": "#2b2f33",
    "muted": "#5a6168",
    "border": "#cfd4da",
    "input_bg": "#ffffff",
    "accent": "#1e293b",
    "accent_text": "#ffffff",
    "brand_grad_a": "#0b1220",
    "brand_grad_b": "#334155",
    "brand_mark_text": "#ffffff",
    "tab_bg": "#dde2e7",
    "tab_active_bg": "#ffffff",
}

DARK = {
    "bg": "#2b2b2b",
    "panel": "#363636",
    "text": "#ffffff",
    "muted": "#c5c8cc",
    "border": "#4a4a4a",
    "input_bg": "#3a3a3a",
    "accent": "#475569",
    "accent_text": "#ffffff",
    "brand_grad_a": "#0b1220",
    "brand_grad_b": "#1e293b",
    "brand_mark_text": "#ffffff",
    "tab_bg": "#3a3a3a",
    "tab_active_bg": "#4a4a4a",
}


def palette(theme: str) -> dict:
    return DARK if theme == "dark" else LIGHT


def theme_css(theme: str) -> str:
    p = palette(theme)
    return f"""
    <style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
        background-color: {p['bg']} !important;
        color: {p['text']} !important;
    }}
    [data-testid="stHeader"] {{
        background: transparent !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {p['panel']} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {p['text']} !important;
    }}
    .stApp p, .stApp span, .stApp label, .stApp li,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    .stApp div[data-testid="stMarkdownContainer"],
    .stApp div[data-testid="stMarkdownContainer"] * {{
        color: {p['text']} !important;
    }}
    .stApp small, .stApp .st-emotion-cache-1mw54nq, .stApp [data-testid="stCaptionContainer"] {{
        color: {p['muted']} !important;
    }}
    .stTextArea textarea, .stTextInput input, .stNumberInput input,
    [data-baseweb="select"] > div, [data-baseweb="input"] > div {{
        background-color: {p['input_bg']} !important;
        color: {p['text']} !important;
        border-color: {p['border']} !important;
    }}
    .stTextArea textarea::placeholder, .stTextInput input::placeholder {{
        color: {p['muted']} !important;
        opacity: 0.8;
    }}
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        background-color: {p['panel']} !important;
        color: {p['text']} !important;
        border: 1px solid {p['border']} !important;
    }}
    .stButton > button:hover, .stFormSubmitButton > button:hover {{
        border-color: {p['accent']} !important;
        color: {p['accent']} !important;
    }}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
        background-color: {p['accent']} !important;
        color: {p['accent_text']} !important;
        border: 1px solid {p['accent']} !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        filter: brightness(1.05);
        color: {p['accent_text']} !important;
    }}
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"],
    [data-testid="stMetricDelta"] {{
        color: {p['text']} !important;
    }}
    [data-testid="stExpander"], [data-testid="stExpander"] summary,
    [data-testid="stExpander"] details {{
        background-color: {p['panel']} !important;
        color: {p['text']} !important;
        border-color: {p['border']} !important;
    }}
    [data-testid="stExpander"] * {{
        color: {p['text']} !important;
    }}
    div[data-testid="stProgress"] > div > div > div {{
        background-color: {p['accent']} !important;
    }}
    .stTabs [data-baseweb="tab-list"] {{
        background-color: {p['tab_bg']} !important;
        border-radius: 8px;
        padding: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        color: {p['text']} !important;
        background-color: transparent !important;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {p['tab_active_bg']} !important;
        border-radius: 6px !important;
    }}
    .stRadio > div {{
        background-color: {p['panel']} !important;
        border: 1px solid {p['border']} !important;
        border-radius: 8px;
        padding: 6px;
    }}
    .stRadio label {{ color: {p['text']} !important; }}
    [data-testid="stAlert"] {{
        background-color: {p['panel']} !important;
        color: {p['text']} !important;
        border: 1px solid {p['border']} !important;
    }}
    [data-testid="stAlert"] * {{ color: {p['text']} !important; }}
    [data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {p['panel']} !important;
        border: 1px solid {p['border']} !important;
        border-radius: 10px;
    }}
    hr {{ border-color: {p['border']} !important; }}

    .ec-brand-wrap {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 1.4rem 1.6rem;
        margin: 0.2rem 0 1.6rem 0;
        background: linear-gradient(135deg, {p['panel']} 0%, {p['bg']} 100%);
        border: 1px solid {p['border']};
        border-radius: 14px;
        box-shadow: 0 2px 14px rgba(0,0,0,0.06);
    }}
    .ec-brand-left {{
        display: flex;
        align-items: center;
        gap: 1rem;
    }}
    .ec-brand-mark {{
        width: 64px;
        height: 64px;
        border-radius: 16px;
        background: linear-gradient(135deg, {p['brand_grad_a']}, {p['brand_grad_b']});
        display: flex;
        align-items: center;
        justify-content: center;
        color: {p['brand_mark_text']} !important;
        font-family: ui-serif, Georgia, "Times New Roman", serif;
        font-weight: 700;
        font-size: 1.7rem;
        letter-spacing: -0.04em;
        box-shadow: 0 6px 18px rgba(0,0,0,0.28),
                    inset 0 1px 0 rgba(255,255,255,0.08);
        border: 1px solid rgba(0,0,0,0.4);
    }}
    .ec-brand-text {{ display: flex; flex-direction: column; line-height: 1.05; }}
    .ec-brand-title {{
        font-family: ui-serif, Georgia, "Times New Roman", serif;
        font-weight: 700;
        font-size: 2.6rem;
        letter-spacing: -0.02em;
        color: {p['text']} !important;
        margin: 0;
    }}
    .ec-brand-tagline {{
        font-size: 0.9rem;
        color: {p['muted']} !important;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        margin-top: 0.3rem;
    }}

    .ec-stat-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.75rem;
        margin: 0.5rem 0 1.4rem 0;
    }}
    @media (max-width: 720px) {{
        .ec-stat-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    .ec-stat {{
        background-color: {p['panel']};
        border: 1px solid {p['border']};
        border-radius: 12px;
        padding: 0.9rem 1rem;
    }}
    .ec-stat-label {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: {p['muted']} !important;
        margin-bottom: 0.3rem;
    }}
    .ec-stat-value {{
        font-size: 1.6rem;
        font-weight: 700;
        color: {p['text']} !important;
        line-height: 1.1;
    }}
    .ec-stat-sub {{
        font-size: 0.78rem;
        color: {p['muted']} !important;
        margin-top: 0.15rem;
    }}
    </style>
    """
