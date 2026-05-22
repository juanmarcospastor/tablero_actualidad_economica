# Tablero Actualidad Económica

Mini tablero económico en Flask listo para subir a GitHub y desplegar en Vercel.

## Cards incluidas

- Infobae Mundo: primera noticia
- Infobae Economía: primera noticia
- Tiempo de San Juan Economía: primera noticia
- Cotizaciones dólar Infobae
- Dólar ArgentinaDatos
- Inflación Argentina
- BCRA Monetarias
- Riesgo País
- Petróleo crudo WTI / Brent

## Ejecutar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Luego abrir:

```text
http://127.0.0.1:5000
```

## Subir a GitHub

```bash
git init
git add .
git commit -m "Primer tablero actualidad economica"
git branch -M main
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
git push -u origin main
```

## Desplegar en Vercel

1. Entrar a Vercel.
2. Importar el repositorio desde GitHub.
3. Framework preset: Other.
4. Deploy.

No requiere claves de inteligencia artificial ni servicios de análisis automático.
