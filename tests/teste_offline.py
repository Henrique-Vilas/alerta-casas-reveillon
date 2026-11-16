"""Roda o fluxo inteiro com respostas falsas do Airbnb, sem internet e sem enviar nada."""
import os, sys, json, types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MODO_TESTE="1", WHATSAPP_PROVEDOR="zapi", WHATSAPP_NUMERO="5571900000000",
                  ZAPI_INSTANCIA="x", ZAPI_TOKEN="y")

def anuncio(i, preco, qualif, lat, lng, quartos=5, nome="Casa"):
    return {"room_id": i, "name": nome, "title": "Home in Mata de São João",
            "structuredContent": {"primaryLine": [{"body": f"{quartos} bedrooms"}, {"body": "8 beds"}]},
            "price": {"unit": {"qualifier": qualif, "amount": preco}, "total": {}},
            "rating": {"value": 4.9, "reviewCount": "37"},
            "coordinates": {"latitude": lat, "longitud": lng}}

base = [
    anuncio(1, 15000, "for 4 nights", -12.578, -38.00, nome="Casa pé na areia"),
    anuncio(2, 3500, "night", -12.656, -38.07, nome="Casa grande condomínio"),   # 14.000 total
    anuncio(3, 18000, "total", -12.625, -38.05),                                 # caro demais
    anuncio(4, 9000, "total", -12.625, -38.05, quartos=4),                       # poucos quartos
    anuncio(5, 12000, "total", -12.625, -38.045, nome="Casa com piscina privativa"),
]
fake = types.ModuleType("pyairbnb")
fake.search_all = lambda **kw: [a for a in base if not kw["amenities"] or a["room_id"] == 1]
sys.modules["pyairbnb"] = fake

import alerta, config
alerta.ARQUIVO_VISTOS = Path(os.environ.get("TMPDIR", "/tmp")) / "visto_teste.json"
alerta.ARQUIVO_VISTOS.unlink(missing_ok=True)
alerta.time.sleep = lambda s: None
config.PARAR_EM = "2099-01-01"

print("=== 1ª rodada ==="); alerta.main()
vistos = json.loads(alerta.ARQUIVO_VISTOS.read_text())
assert set(vistos) == {"1", "2", "5"}, vistos
print("\n=== 2ª rodada (nada novo) ==="); alerta.main()
base[0]["price"]["unit"]["amount"] = 13500
print("\n=== 3ª rodada (casa 1 baixou) ==="); alerta.main()
print("\nOK")
