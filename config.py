"""Tudo que você pode querer ajustar fica aqui."""

CHECK_IN = "2026-12-29"
CHECK_OUT = "2027-01-02"

MIN_QUARTOS = 5
PRECO_MAXIMO_TOTAL = 16_000  # R$ pelo período inteiro (29/12 a 02/01)
HOSPEDES = 0  # 0 = não informar. Coloque o nº de adultos para o preço refletir o grupo.

# Para de checar depois desta data (não faz sentido alertar depois do check-in)
PARAR_EM = "2026-12-29"

# Máximo de mensagens individuais por rodada (o resto vai num resumo)
MAX_ALERTAS_POR_RODADA = 15

# Avisa de novo quando um anúncio já enviado baixar de preço pelo menos isso (R$)
AVISAR_QUEDA_DE_PRECO_MINIMA = 300

# Caixas de busca no mapa (sul-oeste / norte-leste) e centro de cada praia
LOCAIS = {
    "Praia do Forte": {
        "sw": (-12.605, -38.040), "ne": (-12.545, -37.965), "centro": (-12.578, -38.002),
    },
    "Itacimirim": {
        "sw": (-12.645, -38.075), "ne": (-12.600, -38.025), "centro": (-12.625, -38.047),
    },
    "Guarajuba": {
        "sw": (-12.680, -38.100), "ne": (-12.635, -38.045), "centro": (-12.656, -38.068),
    },
}
