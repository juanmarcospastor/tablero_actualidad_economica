import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# =========================
# Fuentes
# =========================
INFOBAE_MUNDO_URL = "https://www.infobae.com/america/"
INFOBAE_ECO_URL = "https://www.infobae.com/economia/"
TIEMPO_SJ_ECO_URL = "https://www.tiempodesanjuan.com/economia"
INFOBAE_DOLAR_URL = "https://www.infobae.com/economia/divisas/dolar-hoy/"

DOLARES_AD_BASE = "https://api.argentinadatos.com/v1/cotizaciones/dolares"
DOLARES_AD_DOCS = "https://argentinadatos.com/docs/operations/get-cotizaciones-dolares.html"
DOLARES_AD_CASAS = {
    "OFICIAL": {"label": "Oficial", "casa": "oficial"},
    "BLUE": {"label": "Blue", "casa": "blue"},
    "BOLSA": {"label": "Bolsa (MEP)", "casa": "bolsa"},
    "CCL": {"label": "Contado con Liqui", "casa": "contadoconliqui"},
    "MAYORISTA": {"label": "Mayorista", "casa": "mayorista"},
    "CRIPTO": {"label": "Cripto", "casa": "cripto"},
    "TARJETA": {"label": "Tarjeta", "casa": "turista"},
}

INFLACION_MENSUAL_URL = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
INFLACION_INTERANUAL_URL = "https://api.argentinadatos.com/v1/finanzas/indices/inflacionInteranual"
RIESGO_PAIS_URL = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"
RIESGO_PAIS_DOCS = "https://argentinadatos.com/docs/operations/get-finanzas-indices-riesgo-pais.html"

BCRA_BASE = "https://api.bcra.gob.ar/estadisticas/v4.0"
BCRA_LIST_URL = f"{BCRA_BASE}/Monetarias"
BCRA_SERIE_URL = f"{BCRA_BASE}/Monetarias/{{id}}"
BCRA_VARIABLES = {
    "RESERVAS": {
        "label": "Reservas Internacionales",
        "tokens": ["reservas internacionales"],
        "y_title": "millones de USD",
    },
    "TC_MINORISTA": {
        "label": "Tipo de Cambio Minorista",
        "tokens": ["tipo de cambio minorista", "tc minorista"],
        "y_title": "ARS/USD",
    },
    "TAMAR_PRIVADOS": {
        "label": "TAMAR de bancos privados",
        "tokens": ["tamar", "bancos privados"],
        "y_title": "% TNA",
    },
    "BASE_MONETARIA": {
        "label": "Base monetaria",
        "tokens": ["base monetaria"],
        "y_title": "millones de ARS",
    },
}
_BCRA_IDS_CACHE = {}

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_RANGE_MAP = {
    "1D": {"range": "1d", "interval": "5m"},
    "1W": {"range": "5d", "interval": "30m"},
    "1M": {"range": "1mo", "interval": "1d"},
    "3M": {"range": "3mo", "interval": "1d"},
    "6M": {"range": "6mo", "interval": "1d"},
    "1A": {"range": "1y", "interval": "1wk"},
    "5A": {"range": "5y", "interval": "1mo"},
    "TODO": {"range": "max", "interval": "1mo"},
}
ASSETS = {
    "wti": {"label": "WTI", "symbol": "CL=F"},
    "brent": {"label": "Brent", "symbol": "BZ=F"},
}


def _headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
        "Accept-Language": "es-AR,es;q=0.9",
    }


def _fmt_fecha(fecha):
    if not fecha:
        return "-"
    return str(fecha)[:10]


def _as_float(value):
    try:
        return float(value)
    except Exception:
        return None


# =========================
# Noticias
# =========================
def obtener_primera_noticia_infobae(url_fuente):
    r = requests.get(url_fuente, headers=_headers(), timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    a = soup.select_one("a.story-card-ctn[href]") or soup.select_one("article a[href]")
    if not a:
        return {"titulo": "No se pudo detectar la primera noticia.", "epigrafe": "", "url": url_fuente}

    h2 = a.select_one("h2.story-card-hl") or a.select_one("h2")
    h3 = a.select_one("h3.story-card-deck") or a.select_one("h3, p")
    titulo = h2.get_text(" ", strip=True) if h2 else a.get_text(" ", strip=True)
    epigrafe = h3.get_text(" ", strip=True) if h3 else ""
    href = a.get("href", "")
    return {"titulo": titulo, "epigrafe": epigrafe, "url": urljoin("https://www.infobae.com", href)}


def obtener_primera_noticia_tiempo_sj():
    r = requests.get(TIEMPO_SJ_ECO_URL, headers=_headers(), timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    a = soup.select_one("a.news-article.news-article--highlighted-news[href]") or soup.select_one("a[href*='/economia/'][href]")
    if not a:
        return {"titulo": "No se pudo detectar la primera noticia.", "epigrafe": "", "url": TIEMPO_SJ_ECO_URL}
    h2 = a.select_one("h2.news-article__title") or a.select_one("h2")
    p = a.select_one("p") or a.select_one("div.news-article__preview")
    titulo = h2.get_text(" ", strip=True) if h2 else a.get_text(" ", strip=True)
    epigrafe = p.get_text(" ", strip=True) if p else ""
    return {"titulo": titulo, "epigrafe": epigrafe, "url": urljoin("https://www.tiempodesanjuan.com", a.get("href", ""))}


# =========================
# Series y APIs
# =========================
def obtener_serie_api(url):
    r = requests.get(url, headers=_headers(), timeout=20)
    r.raise_for_status()
    data = r.json()
    rows = []
    for it in data if isinstance(data, list) else []:
        f = it.get("fecha")
        v = _as_float(it.get("valor"))
        if f and v is not None:
            rows.append((f, v))
    rows.sort(key=lambda x: x[0])
    x = [f for f, _ in rows]
    y = [v for _, v in rows]
    return {"x": x, "y": y, "ultimo": y[-1] if y else None, "fecha_ultimo": x[-1] if x else None}


def obtener_dolares_ad(casa_key):
    casa_key = (casa_key or "OFICIAL").upper()
    if casa_key not in DOLARES_AD_CASAS:
        casa_key = "OFICIAL"
    casa = DOLARES_AD_CASAS[casa_key]["casa"]
    r = requests.get(f"{DOLARES_AD_BASE}/{casa}", headers=_headers(), timeout=20)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = data.get("results", [])
    rows = []
    for it in data if isinstance(data, list) else []:
        f = it.get("fecha")
        v = _as_float(it.get("venta"))
        if f and v is not None:
            rows.append((f, v))
    rows.sort(key=lambda x: x[0])
    x = [f for f, _ in rows]
    y = [v for _, v in rows]
    return {"x": x, "y": y, "ultimo": y[-1] if y else None, "fecha_ultimo": x[-1] if x else None}


def obtener_cotizaciones_infobae():
    # Versión liviana sin Playwright. Si Infobae cambia el HTML, se muestra mensaje pero no rompe el tablero.
    try:
        r = requests.get(INFOBAE_DOLAR_URL, headers=_headers(), timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        out = {}
        for card in soup.select("a.foreign-item-ctn, div.foreign-item-ctn"):
            title_el = card.select_one("span.box-info-title")
            if not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
            compra = venta = variacion = "-"
            for sub in card.select("div.box-info-sub-content"):
                label = sub.select_one("span.box-info-value")
                val = sub.select_one("span.fc-val")
                if not label or not val:
                    continue
                txt_label = label.get_text(" ", strip=True).lower()
                if "compra" in txt_label:
                    compra = val.get_text(" ", strip=True)
                elif "venta" in txt_label:
                    venta = val.get_text(" ", strip=True)
            pct = card.select_one("div.box-info-content-percent")
            if pct:
                variacion = re.sub(r"\s+", "", pct.get_text(" ", strip=True)) or "-"
            out[title] = {"compra": compra, "venta": venta, "variacion": variacion}
        if out:
            return out
    except Exception:
        pass
    return {"No disponible": {"compra": "-", "venta": "-", "variacion": "No se pudo leer con requests"}}


def _normalizar_texto(s):
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def obtener_bcra_ids():
    global _BCRA_IDS_CACHE
    if _BCRA_IDS_CACHE:
        return _BCRA_IDS_CACHE
    r = requests.get(BCRA_LIST_URL, headers=_headers(), timeout=25, verify=False)
    r.raise_for_status()
    data = r.json()
    items = data.get("results") or data.get("data") or data
    ids = {}
    for item in items if isinstance(items, list) else []:
        nombre = _normalizar_texto(item.get("descripcion") or item.get("nombre") or item.get("name"))
        ident = item.get("idVariable") or item.get("id") or item.get("codigo")
        if not nombre or ident is None:
            continue
        for key, cfg in BCRA_VARIABLES.items():
            if all(tok in nombre for tok in cfg["tokens"]):
                ids[key] = ident
    _BCRA_IDS_CACHE = ids
    return ids


def obtener_bcra_serie(var_key):
    ids = obtener_bcra_ids()
    if var_key not in ids:
        raise RuntimeError(f"No encontré el ID de la variable {var_key} en BCRA.")
    r = requests.get(BCRA_SERIE_URL.format(id=ids[var_key]), headers=_headers(), timeout=25, verify=False)
    r.raise_for_status()
    data = r.json()
    items = data.get("results") or data.get("data") or data
    rows = []
    for it in items if isinstance(items, list) else []:
        f = it.get("fecha") or it.get("date")
        v = _as_float(it.get("valor") or it.get("value"))
        if f and v is not None:
            rows.append((f, v))
    rows.sort(key=lambda x: x[0])
    x = [f for f, _ in rows]
    y = [v for _, v in rows]
    return {"x": x, "y": y, "ultimo": y[-1] if y else None, "fecha_ultimo": x[-1] if x else None}


def get_yahoo_data(symbol, range_key):
    range_key = (range_key or "1M").upper()
    cfg = YAHOO_RANGE_MAP.get(range_key, YAHOO_RANGE_MAP["1M"])
    url = YAHOO_URL.format(symbol=symbol)
    r = requests.get(url, params={"range": cfg["range"], "interval": cfg["interval"]}, headers=_headers(), timeout=20)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close", [])
    x, y = [], []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        x.append(datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"))
        y.append(float(close))
    latest = y[-1] if y else None
    first = y[0] if y else None
    variation = ((latest / first) - 1) * 100 if latest is not None and first not in (None, 0) else None
    return {"x": x, "y": y, "latest": latest, "variation": variation}


# =========================
# Rutas
# =========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/widget/infobae_mundo")
def widget_infobae_mundo():
    item = obtener_primera_noticia_infobae(INFOBAE_MUNDO_URL)
    return render_template("_news_card.html", titulo="Infobae Mundo (1ra noticia)", fuente=INFOBAE_MUNDO_URL, item=item)


@app.route("/widget/infobae")
def widget_infobae():
    item = obtener_primera_noticia_infobae(INFOBAE_ECO_URL)
    return render_template("_news_card.html", titulo="Infobae - Economía (1ra noticia)", fuente=INFOBAE_ECO_URL, item=item)


@app.route("/widget/tiempo_sj")
def widget_tiempo_sj():
    item = obtener_primera_noticia_tiempo_sj()
    return render_template("_news_card.html", titulo="Tiempo de San Juan - Economía (1ra noticia)", fuente=TIEMPO_SJ_ECO_URL, item=item)


@app.route("/widget/dolares_infobae")
def widget_dolares_infobae():
    datos = obtener_cotizaciones_infobae()
    return render_template("_dolares_cotizaciones_card.html", datos=datos, fuente=INFOBAE_DOLAR_URL)


@app.route("/widget/dolares_ad")
def widget_dolares_ad():
    casa_key = (request.args.get("casa") or "OFICIAL").upper()
    if casa_key not in DOLARES_AD_CASAS:
        casa_key = "OFICIAL"
    error = ""
    serie = {"x": [], "y": [], "ultimo": None, "fecha_ultimo": None}
    try:
        serie = obtener_dolares_ad(casa_key)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    return render_template("_dolares_ad_card.html", serie=serie, casa_key=casa_key, casas=DOLARES_AD_CASAS, fuente=f"{DOLARES_AD_BASE}/{DOLARES_AD_CASAS[casa_key]['casa']}", docs_casa=DOLARES_AD_DOCS, error=error)


@app.route("/widget/inflacion")
def widget_inflacion():
    error = ""
    mensual = {"x": [], "y": [], "ultimo": None, "fecha_ultimo": None}
    interanual = {"x": [], "y": [], "ultimo": None, "fecha_ultimo": None}
    try:
        mensual = obtener_serie_api(INFLACION_MENSUAL_URL)
        interanual = obtener_serie_api(INFLACION_INTERANUAL_URL)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    return render_template("_inflacion_card.html", mensual=mensual, interanual=interanual, fuente_mensual=INFLACION_MENSUAL_URL, fuente_interanual=INFLACION_INTERANUAL_URL, error=error)


@app.route("/widget/riesgo_pais")
def widget_riesgo_pais():
    error = ""
    serie = {"x": [], "y": [], "ultimo": None, "fecha_ultimo": None}
    try:
        serie = obtener_serie_api(RIESGO_PAIS_URL)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    return render_template("_serie_card.html", titulo="Riesgo País", badge="Riesgo", serie=serie, fuente=RIESGO_PAIS_URL, docs=RIESGO_PAIS_DOCS, y_title="puntos básicos", decimals=0, error=error)


@app.route("/widget/bcra_monetarias")
def widget_bcra_monetarias():
    var_key = (request.args.get("var") or "TAMAR_PRIVADOS").upper()
    if var_key not in BCRA_VARIABLES:
        var_key = "TAMAR_PRIVADOS"
    error = ""
    serie = {"x": [], "y": [], "ultimo": None, "fecha_ultimo": None}
    try:
        serie = obtener_bcra_serie(var_key)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    return render_template("_bcra_monetarias_card.html", serie=serie, var_key=var_key, variables=BCRA_VARIABLES, y_title=BCRA_VARIABLES[var_key]["y_title"], fuente=BCRA_LIST_URL, error=error)


@app.route("/widget/wti_card")
def widget_wti_card():
    return render_template("_wti_card.html")


@app.route("/api/asset-data")
def api_asset_data():
    compare = (request.args.get("compare") or "both").lower()
    range_key = (request.args.get("range") or "1D").upper()
    keys = ["wti", "brent"] if compare == "both" else [compare if compare in ASSETS else "wti"]
    series_map, latest_map, variation_map, labels_map = {}, {}, {}, {}
    for key in keys:
        data = get_yahoo_data(ASSETS[key]["symbol"], range_key)
        series_map[key] = {"x": data["x"], "y": data["y"]}
        latest_map[key] = data["latest"]
        variation_map[key] = data["variation"]
        labels_map[key] = ASSETS[key]["label"]
    return jsonify({"range": range_key, "currency": "USD", "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "series_map": series_map, "latest_map": latest_map, "variation_map": variation_map, "labels_map": labels_map})


if __name__ == "__main__":
    app.run(debug=True)
