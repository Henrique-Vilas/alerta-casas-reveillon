# Alerta de casas – Réveillon no Litoral Norte (BA)

A cada 30 minutos, busca no Airbnb casas inteiras em **Praia do Forte, Itacimirim e Guarajuba**
para **29/12 a 02/01** com **5+ quartos** e **até R$ 16.000 no total**, e manda no seu WhatsApp:

- 🏠 cada casa nova que aparecer (uma mensagem por casa, da mais barata para a mais cara)
- ⚠️ **SEM PISCINA** em destaque quando a casa não tiver piscina
- 📉 aviso quando uma casa que você já recebeu baixar de preço (R$ 300 ou mais)

Ele para sozinho no dia 29/12. Tudo que dá para ajustar está em `config.py`.

## Configuração (uns 10 minutos)

### 1. Suba para o GitHub
Crie um repositório **público** e envie esta pasta. Em repositório público o GitHub Actions é
ilimitado e grátis. Rodando a cada 30 min até 29/12, um repositório privado passaria dos
2.000 minutos grátis por mês. Suas chaves ficam em *Secrets*, que nunca aparecem publicamente.

### 2. Cadastre as chaves
No repositório: **Settings → Secrets and variables → Actions**.

Aba **Variables** → `New repository variable`:

| Nome | Valor |
|---|---|
| `WHATSAPP_PROVEDOR` | `zapi` ou `evolution` |

Aba **Secrets** → `New repository secret`:

| Nome | O que é |
|---|---|
| `WHATSAPP_NUMERO` | Seu número com DDI e DDD, só dígitos. Ex.: `5571999998888` |
| **Se usar Z-API** | |
| `ZAPI_INSTANCIA` | ID da instância (painel Z-API) |
| `ZAPI_TOKEN` | Token da instância |
| `ZAPI_CLIENT_TOKEN` | Token de segurança da conta (aba *Segurança*), se você tiver ativado |
| **Se usar Evolution API** | |
| `EVOLUTION_URL` | Endereço do seu servidor, ex.: `https://evolution.seudominio.com` |
| `EVOLUTION_INSTANCIA` | Nome da instância |
| `EVOLUTION_APIKEY` | API key |

> A instância do WhatsApp precisa estar conectada. Mande do número da instância para o seu
> número (pode ser o mesmo chip, se for um segundo aparelho).

### 3. Teste
Aba **Actions → Alerta casas Réveillon → Run workflow**. Em ~2 minutos as primeiras casas chegam.
Depois disso roda sozinho a cada 30 min (o GitHub às vezes atrasa alguns minutos).

## Como funciona
- `alerta.py` faz duas buscas por praia na API do Airbnb (via `pyairbnb`): uma normal e outra
  com o filtro "Piscina". A casa que só aparece na primeira é marcada como **sem piscina**.
  Anúncios com "piscina" no título também contam como tendo piscina.
- O preço considerado é o **total do período** que o Airbnb mostra para essas datas.
  Se a busca trouxer preço por noite, ele multiplica pelas 4 noites.
- `visto.json` guarda o que já foi enviado, para não repetir. Apague o conteúdo
  (deixe `{}`) se quiser receber tudo de novo.
- `HOSPEDES` em `config.py`: coloque quantos adultos vão. Algumas casas cobram por hóspede,
  e o preço fica mais próximo do real.

## Teste local (sem enviar nada)
```bash
python tests/teste_offline.py
```
