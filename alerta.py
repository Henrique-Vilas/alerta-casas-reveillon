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
from urllib.parse import quote

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


_hash = {"valor": ""}


def buscar_airbnb(local):
    """Retorna os anúncios da área. Se o hash fixo da lib tiver expirado, pega um novo uma vez só."""
    import pyairbnb

    try:
        return _buscar(local, False, _hash["valor"])
    except Exception as erro:
        if _hash["valor"]:
            raise
        print(f"  hash padrão expirou ({str(erro)[:80]}); buscando hash atualizado", file=sys.stderr)
        _hash["valor"] = pyairbnb.search.fetch_stays_search_hash()
        return _buscar(local, False, _hash["valor"])


def tem_piscina(rid):
    """Abre o anúncio e confere a lista de comodidades. True, False ou None (não deu para ver)."""
    import pyairbnb.details as details

    try:
        dados, _, _ = details.get(f"https://www.airbnb.com/rooms/{rid}", "en", "")
    except Exception as erro:
        print(f"  não consegui abrir {rid}: {erro}", file=sys.stderr)
        return None
    grupos = dados.get("amenities") or []
    if not grupos:
        return None
    for grupo in grupos:
        indisponivel = "not included" in (grupo.get("title") or "").lower()
        for a in grupo.get("values", []):
            texto = f"{a.get('title', '')} {a.get('icon', '')}"
            if PALAVRAS_PISCINA.search(texto) and a.get("available", True) is not False and not indisponivel:
                return True
    return False


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
            todos = buscar_airbnb(local)
        except Exception as erro:
            print(f"  ERRO em {nome}: {str(erro)[:300]}", file=sys.stderr)
            falhas.append(nome)
            continue
        print(f"  {len(todos)} anúncios com {config.MIN_QUARTOS}+ quartos")
        for r in todos:
            rid = str(r["room_id"])
            if rid in casas:
                continue
            nome_anuncio = r.get("name") or r.get("title") or "Casa"
            n_quartos = quartos(r)
            casas[rid] = {
                "id": rid,
                "nome": nome_anuncio,
                "praia": praia_mais_proxima(r),
                "preco": preco_total(r),
                "quartos": n_quartos,
                "piscina": None,  # conferido depois, só para as casas que passarem no filtro
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


def texto_piscina(piscina):
    if piscina is True:
        return "🏊 Tem piscina"
    if piscina is False:
        return "⚠️ *ATENÇÃO: SEM PISCINA*"
    return "❓ Não consegui confirmar se tem piscina, veja no anúncio"


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
    linhas.append(texto_piscina(c["piscina"]))
    if c["nota"]:
        linhas.append(f"⭐ {c['nota']} ({c['avaliacoes']} avaliações)")
    linhas.append(c["link"])
    return "\n".join(linhas)


def enviar_whatsapp(texto):
    # um ou mais números separados por vírgula, ex.: 557191066900,557187200701
    for numero in re.split(r"[,\s;]+", os.environ["WHATSAPP_NUMERO"].strip()):
        if numero:
            _enviar_para(re.sub(r"\D", "", numero), texto)


def _enviar_para(numero, texto):
    provedor = (os.environ.get("WHATSAPP_PROVEDOR") or "evolution").lower()

    if provedor == "zapi":
        url = (f"https://api.z-api.io/instances/{os.environ['ZAPI_INSTANCIA']}"
               f"/token/{os.environ['ZAPI_TOKEN']}/send-text")
        headers = {"Client-Token": os.environ.get("ZAPI_CLIENT_TOKEN", "")}
        corpo = {"phone": numero, "message": texto}
    elif provedor == "evolution":
        base = re.sub(r"/manager/?$", "", os.environ["EVOLUTION_URL"].rstrip("/"))
        url = f"{base}/message/sendText/{quote(os.environ['EVOLUTION_INSTANCIA'], safe='')}"
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

    # Piscina: confere no anúncio uma vez por casa e guarda o resultado em visto.json
    correcoes = []
    for c in casas:
        antigo = vistos.get(c["id"])
        if antigo and antigo.get("piscina") is not None:
            c["piscina"] = antigo["piscina"]
            continue
        c["piscina"] = tem_piscina(c["id"])
        if c["piscina"] is None and PALAVRAS_PISCINA.search(c["nome"]):
            c["piscina"] = True
        # casas avisadas antes desta verificação existir: corrige se não tiver piscina
        if antigo and "piscina" not in antigo and c["piscina"] is False:
            correcoes.append(c)
        if antigo and c["piscina"] is not None:
            antigo["piscina"] = c["piscina"]
        time.sleep(1)

    for c in correcoes:
        enviar_whatsapp(f"⚠️ *CORREÇÃO: esta casa NÃO tem piscina*\n📍 {c['praia']} · {brl(c['preco'])}\n*{c['nome']}*\n{c['link']}")

    alertas = []
    for c in casas:
        antigo = vistos.get(c["id"])
        if antigo is None:
            alertas.append((c, None))
        elif antigo["preco"] - c["preco"] >= config.AVISAR_QUEDA_DE_PRECO_MINIMA:
            alertas.append((c, antigo["preco"]))

    def registrar(c):
        vistos.setdefault(c["id"], {"visto_em": date.today().isoformat()})
        vistos[c["id"]].update(preco=c["preco"], nome=c["nome"], piscina=c["piscina"])

    enviados = alertas[: config.MAX_ALERTAS_POR_RODADA]
    restantes = alertas[config.MAX_ALERTAS_POR_RODADA:]
    for c, queda in enviados:
        enviar_whatsapp(montar_mensagem(c, queda))
        registrar(c)

    if restantes:
        resumo = [f"➕ Mais {len(restantes)} casas encontradas (do mais barato para o mais caro):"]
        for c, _ in restantes[:30]:
            sem = " ⚠️ SEM PISCINA" if c["piscina"] is False else ""
            resumo.append(f"• {c['praia']} · {brl(c['preco'])}{sem}\n  {c['link']}")
        enviar_whatsapp("\n".join(resumo))
        for c, _ in restantes:
            registrar(c)

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
