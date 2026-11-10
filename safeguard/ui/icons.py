"""Small original line icons, decorative and independent of network fonts."""

PATHS = {
    "helmet": '<path d="M3 17v-3a9 9 0 0 1 18 0v3M9 4v9m6-9v9M2 17c5 4 15 4 20 0v3c-6 3-14 3-20 0z"/>',
    "scan": '<path d="M8 3H4a1 1 0 0 0-1 1v4m13-5h4a1 1 0 0 1 1 1v4M3 16v4a1 1 0 0 0 1 1h4m8 0h4a1 1 0 0 0 1-1v-4"/><circle cx="12" cy="12" r="4"/>',
    "people": '<circle cx="9" cy="7" r="4"/><path d="M2 22v-3a7 7 0 0 1 14 0v3zm15-18a4 4 0 0 1 0 8m2 3a6 6 0 0 1 3 5"/>',
    "layers": '<path d="m12 2 10 5-10 5L2 7zm-10 10 10 5 10-5M2 17l10 5 10-5"/>',
    "chart": '<path d="M3 21V13h4v8zm7 0V8h4v13zm7 0V3h4v18z"/>',
    "image": '<rect x="2" y="3" width="20" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 18 5-5 4 3 4-6 5 8"/>',
    "alert": '<path d="m12 2 10 19H2zM12 8v6m0 3v1"/>',
    "shield": '<path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6zM7 12l3 3 7-7"/>',
    "video": '<rect x="2" y="5" width="14" height="14" rx="2"/><path d="m16 9 6-4v14l-6-4"/>',
    "rocket": '<path d="M8 16C6 8 12 2 22 2c0 10-6 16-14 14zm0-8H3l-2 6h6m9 2v5l-6 2v-6M5 19l-3 3"/><circle cx="16" cy="8" r="2"/>',
    "upload": '<path d="M12 17V2m-5 5 5-5 5 5M3 14v7h18v-7"/>',
    "book": '<path d="M12 5C8 2 4 2 2 4v16c3-2 7-2 10 0 3-2 7-2 10 0V4c-2-2-6-2-10 1zM12 5v15"/>',
    "home": '<path d="m2 11 10-9 10 9M5 9v13h5v-8h4v8h5V9"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 5v7l4 3"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9 8a3 3 0 1 1 4 3c-1 1-1 2-1 3m0 3v1"/>',
    "settings": '<circle cx="12" cy="12" r="4"/><path d="m10 2 4 0 1 4 4-1 2 4-3 3 3 3-2 4-4-1-1 4h-4l-1-4-4 1-2-4 3-3-3-3 2-4 4 1z"/>',
}


def icon(name, size=28):
    return f'<svg xmlns="http://www.w3.org/2000/svg" class="sb-icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{PATHS[name]}</svg>'


CRANE = """<svg class="sb-crane" viewBox="0 0 300 190" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="crane-face" x2="1" y2="1"><stop stop-color="#157E7C"/><stop offset="1" stop-color="#073A43"/></linearGradient></defs><path d="M0 170 48 151 102 165 185 139 300 172V190H0Z" fill="#063137"/><path d="m57 164 91-34 93 32-91 28Z" fill="#0B4D50"/><g stroke="#0A444B" stroke-width="3"><path d="M18 170V130m12 36v-54m11 51v-30m222 33V116m13 54v-38m12 43v-65"/></g><g fill="url(#crane-face)" stroke="#12585F" stroke-width="1"><path d="M67 157V99l6-3v63zm34 13V78l7-3v98zm38 15V91l7-3v99zm48-16V107l7-3v68z"/><path d="m68 111 72 25v9l-72-25zm0 27 72 25v9l-72-25zm34-48 87 30v9l-87-30zm0 29 87 30v9l-87-30z"/><path d="m73 105 32-13v8l-32 13zm73 34 44-17v9l-44 17zm0 28 44-17v9l-44 17z"/></g><g fill="none" stroke="#168A89" stroke-width="1.3"><path d="M211 164V36h12v128l-12 5zm0-116 12 12-12 12 12 12-12 12 12 12-12 12 12 12-12 12 12 12M211 48h12m-12 24h12m-12 24h12m-12 24h12m-12 24h12"/><path d="m125 55 91-31 61 15v9l-152 17zm0 0 152-16m-139 21 9-12 10 8 11-15 10 9 12-16 10 9 16-19 14 22 12-15 11 13 12-10 12 5M216 24V14l-32 32m32-32 43 28M137 63v31m-4 0q4 7 8 0"/></g><path d="m265 37 17 4v11l-17-3z" fill="#13807E"/><path d="m208 40 18-4v13l-18 5z" fill="#0C6267"/><path d="m214 41 9-2v7l-9 3z" fill="#031F2A"/></svg>"""
