"""Busca casas no Airbnb (Praia do Forte, Itacimirim, Guarajuba) para o Réveillon
e manda alerta no WhatsApp (Z-API ou Evolution API) quando aparece casa nova
ou quando uma casa já avisada baixa de preço."""

import json
import math
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

import config

ARQUIVO_VISTOS = Path(__file__).with_name("visto.json")
AMENIDADE_PISCINA = 7  # id de "Piscina" nos filtros do Airbnb
PALAVRAS_PISCINA = re.compile(r"piscina|pool|swimming", re.I)
NOITES = (date.fromisoformat(config.CHECK_OUT) - date.fromisoformat(config.CHECK_IN)).days


# ---------------------------------------------------------------- Airbnb

def _buscar(local, com_piscina, hash_busca=""):
    import pyairbnb

    sw, ne = local["sw"], local["ne"]
    return pyairbnb.search_all(
        check_in=config.CHECK_IN,
        check_out=config.CHECK_OUT,
        sw_lat=sw[0], sw_long=sw[1], ne_lat=ne[0], ne_long=ne[1],
        zoom_value=14,
        price_min=0,
        price_max=0,  # o teto é aplicado aqui no script, sobre o total do período
        place_type="Entire home/apt",
        amenities=[AMENIDADE_PISCINA] if com_piscina else [],
        adults=config.HOSPEDES,
        min_bedrooms=config.MIN_QUARTOS,
        currency="BRL",
        language="en",  # o parser da lib entende "R$15,000"; em pt viraria 15.000 -> 15.0
        hash=hash_busca,
    )


def buscar_airbnb(local):
    """Retorna (todos, ids_com_piscina). Faz duas buscas: sem filtro e com filtro de piscina."""
    import pyairbnb

    hash_busca = ""
    for tentativa in range(2):
        try:
            todos = _buscar(local, False, hash_busca)
            com_piscina = _buscar(local, True, hash_busca)
            return todos, {str(r["room_id"]) for r in com_piscina}
        except Exception as erro:  # o hash fixo da lib às vezes expira: pega um novo
            if tentativa == 1:
                raise
            print(f"  busca falhou ({erro}); tentando com hash atualizado", file=sys.stderr)
            hash_busca = pyairbnb.search.fetch_stays_search_hash()


def preco_total(r):
    unit = r.get("price", {}).get("unit", {})
    total = r.get("price", {}).get("total", {}).get("amount") or 0
    if total:
        return float(total)
    valor = unit.get("discount") or unit.get("amount") or 0
    qualif = (unit.get("qualifier") or "").lower()
    if re.search(r"\bnight\b|noite\b", qualif) and not re.search(r"\d", qualif):
        valor *= NOITES  # preço veio por noite
    return float(valor)


def quartos(r):
    texto = json.dumps(r.get("structuredContent", {}), ensure_ascii=False) + " " + r.get("title", "") + " " + r.get("name", "")
    m = re.search(r"(\d+)\s*(?:bedrooms?|quartos?|su[ií]tes?)", texto, re.I)
    return int(m.group(1)) if m else None


def praia_mais_proxima(r):
    lat = r.get("coordinates", {}).get("latitude") or 0
    lng = r.get("coordinates", {}).get("longitud") or 0
    return min(config.LOCAIS, key=lambda n: math.dist((lat, lng), config.LOCAIS[n]["centro"]))


falhas = []


def coletar():
    casas = {}
    for nome, local in config.LOCAIS.items():
        print(f"Buscando {nome}...")
        try:
            todos, ids_piscina = buscar_airbnb(local)
        except Exception as erro:
            print(f"  ERRO em {nome}: {erro}", file=sys.stderr)
            falhas.append(nome)
            continue
        print(f"  {len(todos)} anúncios com {config.MIN_QUARTOS}+ quartos, {len(ids_piscina)} com piscina")
        for r in todos:
            rid = str(r["room_id"])
            if rid in casas:
                casas[rid]["piscina"] |= rid in ids_piscina
                continue
            nome_anuncio = r.get("name") or r.get("title") or "Casa"
            n_quartos = quartos(r)
            casas[rid] = {
                "id": rid,
                "nome": nome_anuncio,
                "praia": praia_mais_proxima(r),
                "preco": preco_total(r),
                "quartos": n_quartos,
                "piscina": rid in ids_piscina or bool(PALAVRAS_PISCINA.search(nome_anuncio)),
                "nota": r.get("rating", {}).get("value") or None,
                "avaliacoes": r.get("rating", {}).get("reviewCount") or 0,
                "link": f"https://www.airbnb.com.br/rooms/{rid}?check_in={config.CHECK_IN}&check_out={config.CHECK_OUT}",
            }
        time.sleep(2)
    return casas


def filtrar(casas):
    ok = []
    for c in casas.values():
        if not c["preco"] or c["preco"] > config.PRECO_MAXIMO_TOTAL:
            continue
        if c["quartos"] is not None and c["quartos"] < config.MIN_QUARTOS:
            continue
        ok.append(c)
    return sorted(ok, key=lambda c: c["preco"])


# ---------------------------------------------------------------- WhatsApp

def brl(v):
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def montar_mensagem(c, queda_de=None):
    di = datetime.strptime(config.CHECK_IN, "%Y-%m-%d").strftime("%d/%m")
    df = datetime.strptime(config.CHECK_OUT, "%Y-%m-%d").strftime("%d/%m")
    cabecalho = "📉 *BAIXOU O PREÇO*" if queda_de else "🏠 *CASA NOVA ENCONTRADA*"
    linhas = [
        cabecalho,
        f"📍 {c['praia']}",
        f"*{c['nome']}*",
        f"🛏️ {c['quartos'] or str(config.MIN_QUARTOS) + '+'} quartos",
    ]
    preco = f"💰 {brl(c['preco'])} total ({di} a {df}, {NOITES} noites)"
    if queda_de:
        preco += f"\n   antes: {brl(queda_de)}"
    linhas.append(preco)
    linhas.append("🏊 Tem piscina" if c["piscina"] else "⚠️ *ATENÇÃO: SEM PISCINA*")
    if c["nota"]:
        linhas.append(f"⭐ {c['nota']} ({c['avaliacoes']} avaliações)")
    linhas.append(c["link"])
    return "\n".join(linhas)


def enviar_whatsapp(texto):
    provedor = os.environ.get("WHATSAPP_PROVEDOR", "zapi").lower()
    numero = os.environ["WHATSAPP_NUMERO"]  # ex.: 5571999998888

    if provedor == "zapi":
        url = (f"https://api.z-api.io/instances/{os.environ['ZAPI_INSTANCIA']}"
               f"/token/{os.environ['ZAPI_TOKEN']}/send-text")
        headers = {"Client-Token": os.environ.get("ZAPI_CLIENT_TOKEN", "")}
        corpo = {"phone": numero, "message": texto}
    elif provedor == "evolution":
        base = os.environ["EVOLUTION_URL"].rstrip("/")
        url = f"{base}/message/sendText/{os.environ['EVOLUTION_INSTANCIA']}"
        headers = {"apikey": os.environ["EVOLUTION_APIKEY"]}
        corpo = {"number": numero, "text": texto}
    else:
        raise SystemExit(f"WHATSAPP_PROVEDOR inválido: {provedor} (use zapi ou evolution)")

    if os.environ.get("MODO_TESTE") == "1":
        print("---- (teste, não enviado) ----\n" + texto)
        return
    resp = requests.post(url, json=corpo, headers=headers, timeout=30)
    if resp.status_code >= 300:
        raise RuntimeError(f"WhatsApp respondeu {resp.status_code}: {resp.text[:300]}")
    time.sleep(1.5)


# ---------------------------------------------------------------- principal

def carregar_vistos():
    try:
        return json.loads(ARQUIVO_VISTOS.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    if date.today() > date.fromisoformat(config.PARAR_EM):
        print("Período encerrado, nada a fazer.")
        return

    vistos = carregar_vistos()
    casas = filtrar(coletar())
    print(f"{len(casas)} casas dentro do orçamento de {brl(config.PRECO_MAXIMO_TOTAL)}")

    alertas = []
    for c in casas:
        antigo = vistos.get(c["id"])
        if antigo is None:
            alertas.append((c, None))
        elif antigo["preco"] - c["preco"] >= config.AVISAR_QUEDA_DE_PRECO_MINIMA:
            alertas.append((c, antigo["preco"]))

    enviados = alertas[: config.MAX_ALERTAS_POR_RODADA]
    restantes = alertas[config.MAX_ALERTAS_POR_RODADA:]
    for c, queda in enviados:
        enviar_whatsapp(montar_mensagem(c, queda))
        vistos[c["id"]] = {"preco": c["preco"], "nome": c["nome"], "visto_em": date.today().isoformat()}

    if restantes:
        resumo = [f"➕ Mais {len(restantes)} casas encontradas (do mais barato para o mais caro):"]
        for c, _ in restantes[:30]:
            sem = " ⚠️ SEM PISCINA" if not c["piscina"] else ""
            resumo.append(f"• {c['praia']} · {brl(c['preco'])}{sem}\n  {c['link']}")
        enviar_whatsapp("\n".join(resumo))
        for c, _ in restantes:
            vistos[c["id"]] = {"preco": c["preco"], "nome": c["nome"], "visto_em": date.today().isoformat()}

    # guarda também o preço atual dos já vistos para detectar quedas futuras
    for c in casas:
        if c["id"] in vistos:
            vistos[c["id"]]["preco"] = min(vistos[c["id"]]["preco"], c["preco"])

    ARQUIVO_VISTOS.write_text(json.dumps(vistos, ensure_ascii=False, indent=1, sort_keys=True))
    print(f"{len(alertas)} alertas enviados.")
    if len(falhas) == len(config.LOCAIS):
        raise SystemExit("Todas as buscas falharam (Airbnb pode ter mudado a API ou bloqueado).")


if __name__ == "__main__":
    main()
