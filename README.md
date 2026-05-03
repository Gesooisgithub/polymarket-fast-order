# Polymarket Hotkey Trader

Sistema di trading ultra-veloce per Polymarket tramite hotkeys globali. Piazza ordini istantaneamente premendo combinazioni di tasti, con conferma fill in tempo reale via WebSocket e visualizzazione portfolio dopo ogni trade.

**Target**: < 1 secondo da keypress a ordine eseguito.

## Requisiti

- Python 3.9+
- Windows (per hotkeys globali)
- Privilegi Amministratore (per catturare hotkeys globali)
- Wallet con USDC su Polygon
- USDC approvato per il trading su Polymarket
- API Keys Builder di Polymarket

## Installazione

### 1. Clona/Scarica il progetto

```bash
cd polymarket-fast-order
```

### 2. Crea e attiva l'ambiente virtuale

**Obbligatorio**: il bot deve essere eseguito all'interno di un ambiente virtuale Python.

```bash
python -m venv .venv
.venv\Scripts\activate
```

> Ogni volta che apri un nuovo terminale per usare il bot, ricordati di attivare il venv:
> ```bash
> .venv\Scripts\activate
> ```

### 3. Installa dipendenze

```bash
pip install -r requirements.txt
```

### 4. Configura credenziali

Copia il file `.env.example` in `.env`:

```bash
copy .env.example .env
```

Modifica `.env` con le tue credenziali:

```env
POLYMARKET_PRIVATE_KEY=0x_la_tua_private_key
POLYMARKET_FUNDER_ADDRESS=0x_il_tuo_wallet_address
POLYMARKET_API_KEY=your_api_key
POLYMARKET_API_SECRET=your_api_secret
POLYMARKET_PASSPHRASE=your_passphrase
```

#### Come ottenere le API Keys:
1. Vai su [polymarket.com/settings/builder-codes](https://polymarket.com/settings/builder-codes)
2. Crea un nuovo set di API keys
3. Copia API Key, Secret e Passphrase nel file `.env`

#### Come ottenere la Private Key da MetaMask:
1. Apri MetaMask
2. Clicca sui 3 puntini accanto al nome dell'account
3. "Account details" > "Show private key"
4. Inserisci la password e copia la key (inizia con `0x`)

**IMPORTANTE**: Non condividere MAI la tua private key o le API keys!

### 5. Approva USDC (se non l'hai gia fatto)

Puoi approvare USDC in due modi:

**Opzione A** - Usa lo script incluso:
```bash
python setup_allowance.py
```

**Opzione B** - Manualmente su Polymarket:
1. Vai su [Polymarket.com](https://polymarket.com)
2. Connetti il tuo wallet
3. Piazza un ordine qualsiasi manualmente
4. Approva la transazione "Approve USDC"

## Avvio

```bash
.venv\Scripts\activate
python main.py
```

> Il programma deve essere eseguito come **Amministratore** per le hotkeys globali.

## Modalita di funzionamento

Il bot supporta due modalita, configurabili in `config.json`:

### Football Mode (default)

Pensato per le partite di calcio. Gestisce 3 mercati contemporaneamente: **Team1 win**, **Draw**, **Team2 win**.

All'avvio:
1. Viene mostrato il saldo wallet
2. Ti viene chiesto di incollare un **URL evento Polymarket** (es. `https://polymarket.com/sports/sea/sea-gen-tor-2026-02-22`)
3. Il bot auto-rileva i 3 mercati dall'evento e li configura
4. Le hotkeys diventano attive e i prezzi si aggiornano ogni 2 secondi

### Standard Mode

Per mercati singoli YES/NO. All'avvio selezioni un mercato tramite condition ID, slug o ricerca keyword.

## Hotkeys

Il bot usa un **importo unico** per tutti gli ordini, modificabile al volo con `CTRL+A`.

### Football Mode

| Hotkey | Azione |
|--------|--------|
| `CTRL+F1` | Buy Team 1 |
| `CTRL+F2` | Buy Draw |
| `CTRL+F3` | Buy Team 2 |
| `CTRL+F4` | Sell Team 1 |
| `CTRL+F5` | Sell Draw |
| `CTRL+F6` | Sell Team 2 |
| `CTRL+A` | Cambia importo |
| `CTRL+B` | Controlla saldo |
| `CTRL+M` | Cambia mercati (nuovo URL evento) |
| `CTRL+Q` | Esci |

### Standard Mode

| Hotkey | Azione |
|--------|--------|
| `CTRL+1` | Buy YES |
| `CTRL+2` | Buy NO |
| `CTRL+3` | Sell YES |
| `CTRL+4` | Sell NO |
| `CTRL+A` | Cambia importo |
| `CTRL+B` | Controlla saldo |
| `CTRL+M` | Cambia mercato |
| `CTRL+Q` | Esci |

> Le hotkeys sono personalizzabili in `config.json`.

## Come funzionano gli ordini

Gli ordini vengono inviati come **FAK (Fill-And-Kill)** con prezzo aggressivo per garantire esecuzione immediata:

- **BUY**: Limit price 0.99 - compra a qualsiasi prezzo disponibile nell'orderbook. La size viene calcolata come `importo / 0.99` per spendere circa l'importo desiderato in USDC.
- **SELL**: Limit price 0.01 - vende **tutte le shares** possedute al miglior prezzo disponibile.

L'ordine "sweeps" l'orderbook, fillando contro tutta la liquidita disponibile.

### Conferma Fill in tempo reale

Dopo ogni ordine, il bot mostra una conferma con i dati reali del fill:

- **Mercati non-sportivi**: conferma istantanea dalla risposta REST (makingAmount/takingAmount)
- **Mercati sportivi (football)**: conferma via WebSocket entro ~4 secondi (evento MATCHED dal canale utente Polymarket)

Il `FillTracker` mantiene una connessione WebSocket persistente a `wss://ws-subscriptions-clob.polymarket.com/ws/user` per ricevere eventi di trade in tempo reale.

### Portfolio dopo ogni fill

Dopo ogni conferma di fill, il `PortfolioDisplay` mostra automaticamente:
- Prezzo medio di acquisto e shares possedute
- Prezzo corrente dell'outcome
- P/L stimato rispetto all'ultimo prezzo di acquisto

### Ottimizzazioni velocita

- I prezzi sono cachati e aggiornati ogni 2 secondi in background
- Il saldo USDC e le posizioni sono tracciati localmente (nessuna chiamata HTTP nel path critico)
- Le posizioni vengono pre-caricate all'avvio (`initialize_positions`)
- Fallback automatico a HTTP se la cache e vuota
- Cooldown di 0.5s tra ordini (previene double-click accidentali)

## Configurazione

Modifica `config.json`:

```json
{
  "hotkeys": {
    "buy_team1": "ctrl+f1",
    "buy_draw": "ctrl+f2",
    "buy_team2": "ctrl+f3",
    "sell_team1": "ctrl+f4",
    "sell_draw": "ctrl+f5",
    "sell_team2": "ctrl+f6",
    "set_amount": "ctrl+a",
    "check_balance": "ctrl+b",
    "change_markets": "ctrl+m",
    "quit": "ctrl+q"
  },
  "default_amount": 1.0,
  "cooldown_seconds": 0.5,
  "clob_host": "https://clob.polymarket.com",
  "gamma_host": "https://gamma-api.polymarket.com",
  "chain_id": 137,
  "signature_type": 0
}
```

### Opzioni configurabili

- **hotkeys**: combinazioni di tasti per ogni azione
- **default_amount**: importo di default in USDC all'avvio
- **cooldown_seconds**: tempo minimo tra ordini consecutivi
- **mode**: `"football"` (default) o `"standard"`
- **clob_host**: endpoint API CLOB di Polymarket
- **gamma_host**: endpoint API Gamma di Polymarket
- **chain_id**: ID chain Polygon (137 = mainnet)
- **signature_type**: 0 per EOA/MetaMask, 1 per Magic wallet

## Struttura File

```
polymarket-fast-order/
├── main.py                # Entry point, app loop, hotkey wiring
├── trader.py              # Logica trading CLOB, position/balance tracking
├── fill_tracker.py        # Conferma fill via WebSocket in tempo reale
├── portfolio_display.py   # Visualizzazione portfolio dopo ogni fill
├── event_fetcher.py       # Fetch eventi football da URL Polymarket
├── hotkey_manager.py      # Gestione hotkeys globali
├── market_info.py         # Client API (Gamma + CLOB), MarketData
├── console_ui.py          # Interfaccia console con colorama
├── setup_allowance.py     # Script per approvare pUSD sui contratti CTF
├── wrap_usdce.py          # Script per convertire USDC.e -> pUSD (CLOB V2)
├── config.json            # Configurazione hotkeys e parametri
├── .env                   # Credenziali (NON committare!)
├── .env.example           # Template credenziali
└── requirements.txt       # Dipendenze Python
```

## Troubleshooting

### "Hotkeys non funzionano"
- Esegui il programma come **Amministratore**
- Su Windows: Click destro su cmd/PowerShell > "Esegui come amministratore"

### "USDC not approved"
- Esegui `python setup_allowance.py` oppure vai su Polymarket.com e piazza un ordine manualmente

### "Insufficient balance"
- Controlla di avere abbastanza USDC nel wallet su rete Polygon

### "Invalid signature"
- Verifica che la private key in `.env` sia corretta e inizi con `0x`

### "Could not identify Team1, Draw, and Team2 markets"
- L'URL dell'evento deve puntare a una partita con 3 outcome (Team1, Draw, Team2)
- Verifica che i mercati siano ancora attivi e non chiusi

## Sicurezza

- La private key non viene MAI stampata o loggata
- `.env` e nel `.gitignore`
- Gli ordini sono firmati localmente (la key non lascia il tuo computer)
- Le API keys vengono usate solo per autenticazione con il CLOB e il canale WebSocket (`wss://ws-subscriptions-clob.polymarket.com/ws/user`)
- Cooldown di 0.5s previene ordini accidentali

## Disclaimer

**ATTENZIONE**: Questo software esegue ordini REALI con soldi REALI.

- Gli ordini vengono eseguiti al **miglior prezzo disponibile** (non a un prezzo specifico)
- Non c'e protezione slippage - l'ordine sweeps l'orderbook
- Usa importi che puoi permetterti di perdere
- Testa prima con importi piccoli

L'autore non e responsabile per perdite finanziarie derivanti dall'uso di questo software.

## License

MIT License
