# Polymarket Hotkey Trader

Ultra-fast trading system for Polymarket via global hotkeys. Place orders instantly by pressing key combinations, with real-time fill confirmation via WebSocket and portfolio display after each trade.

**Target**: < 1 second from keypress to executed order.

## Requirements

- Python 3.9+
- Windows (for global hotkeys)
- Administrator privileges (to capture global hotkeys)
- Wallet with USDC on Polygon
- USDC approved for trading on Polymarket
- MetaMask wallet with private key

## Installation

### 1. Clone the project

```bash
git clone https://github.com/YOUR_USERNAME/polymarket-fast-order.git
cd polymarket-fast-order
```

### 2. Create and activate a virtual environment

**Required**: the bot must be run inside a Python virtual environment.

```bash
python -m venv .venv
.venv\Scripts\activate
```

> Every time you open a new terminal to use the bot, remember to activate the venv:
> ```bash
> .venv\Scripts\activate
> ```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure credentials

Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

Edit `.env` with your credentials:

```env
POLYMARKET_PRIVATE_KEY=0x_your_private_key
POLYMARKET_FUNDER_ADDRESS=0x_your_wallet_address
```

#### How to get your Private Key from MetaMask:
1. Open MetaMask
2. Click the 3 dots next to the account name
3. "Account details" > "Show private key"
4. Enter your password and copy the key (starts with `0x`)

**IMPORTANT**: Never share your private key!

### 5. Approve USDC (if not done already)

You can approve USDC in two ways:

**Option A** - Use the included script:
```bash
python setup_allowance.py
```

**Option B** - Manually on Polymarket:
1. Go to [Polymarket.com](https://polymarket.com)
2. Connect your wallet
3. Place any order manually
4. Approve the "Approve USDC" transaction

## Usage

```bash
.venv\Scripts\activate
python main.py
```

> The program must be run as **Administrator** for global hotkeys to work.

## Operating Modes

The bot supports two modes, configurable in `config.json`:

### Football Mode (default)

Designed for football (soccer) matches. Manages 3 markets simultaneously: **Team1 win**, **Draw**, **Team2 win**.

On startup:
1. Your wallet balance is displayed
2. You are asked to paste a **Polymarket event URL** (e.g. `https://polymarket.com/sports/sea/sea-gen-tor-2026-02-22`)
3. The bot auto-detects the 3 markets from the event and configures them
4. Hotkeys become active and prices refresh every 2 seconds

### Standard Mode

For single YES/NO markets. On startup you select a market via condition ID, slug, or keyword search.

## Hotkeys

The bot uses a **single amount** for all orders, adjustable on the fly with `CTRL+A`.

### Football Mode

| Hotkey | Action |
|--------|--------|
| `CTRL+F1` | Buy Team 1 |
| `CTRL+F2` | Buy Draw |
| `CTRL+F3` | Buy Team 2 |
| `CTRL+F4` | Sell Team 1 |
| `CTRL+F5` | Sell Draw |
| `CTRL+F6` | Sell Team 2 |
| `CTRL+A` | Change amount |
| `CTRL+B` | Check balance |
| `CTRL+M` | Change markets (new event URL) |
| `CTRL+Q` | Quit |

### Standard Mode

| Hotkey | Action |
|--------|--------|
| `CTRL+1` | Buy YES |
| `CTRL+2` | Buy NO |
| `CTRL+3` | Sell YES |
| `CTRL+4` | Sell NO |
| `CTRL+A` | Change amount |
| `CTRL+B` | Check balance |
| `CTRL+M` | Change market |
| `CTRL+Q` | Quit |

> Hotkeys are customizable in `config.json`.

## How Orders Work

Orders are sent as **FAK (Fill-And-Kill)** with aggressive pricing to guarantee immediate execution:

- **BUY**: Limit price 0.99 - buys at any available price in the orderbook. Size is calculated as `amount / 0.99` to spend approximately the desired USDC amount.
- **SELL**: Limit price 0.01 - sells **all shares** held at the best available price.

The order "sweeps" the orderbook, filling against all available liquidity.

### Real-time Fill Confirmation

After each order, the bot shows a confirmation with actual fill data:

- **Non-sports markets**: instant confirmation from the REST response (makingAmount/takingAmount)
- **Sports markets (football)**: confirmation via WebSocket within ~4 seconds (MATCHED event from the Polymarket user channel)

The `FillTracker` maintains a persistent WebSocket connection to `wss://ws-subscriptions-clob.polymarket.com/ws/user` for real-time trade events.

### Portfolio After Each Fill

After each fill confirmation, the `PortfolioDisplay` automatically shows:
- Average purchase price and shares held
- Current outcome price
- Estimated P/L relative to the last purchase price

### Speed Optimizations

- Prices are cached and refreshed every 2 seconds in the background
- USDC balance and positions are tracked locally (no HTTP calls in the critical path)
- Positions are pre-loaded at startup (`initialize_positions`)
- Automatic fallback to HTTP if cache is empty
- 0.5s cooldown between orders (prevents accidental double-clicks)

## Configuration

Edit `config.json`:

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

### Configurable Options

- **hotkeys**: key combinations for each action
- **default_amount**: default USDC amount at startup
- **cooldown_seconds**: minimum time between consecutive orders
- **mode**: `"football"` (default) or `"standard"`
- **clob_host**: Polymarket CLOB API endpoint
- **gamma_host**: Polymarket Gamma API endpoint
- **chain_id**: Polygon chain ID (137 = mainnet)
- **signature_type**: 0 for EOA/MetaMask, 1 for Magic wallet

## File Structure

```
polymarket-fast-order/
├── main.py                # Entry point, app loop, hotkey wiring
├── trader.py              # CLOB trading logic, position/balance tracking
├── fill_tracker.py        # Real-time fill confirmation via WebSocket
├── portfolio_display.py   # Portfolio display after each fill
├── event_fetcher.py       # Fetch football events from Polymarket URL
├── hotkey_manager.py      # Global hotkey management
├── market_info.py         # API client (Gamma + CLOB), MarketData
├── console_ui.py          # Console interface with colorama
├── setup_allowance.py     # Script to approve USDC on Polymarket
├── config.json            # Hotkey and parameter configuration
├── .env                   # Credentials (DO NOT commit!)
├── .env.example           # Credentials template
└── requirements.txt       # Python dependencies
```

## Troubleshooting

### "Hotkeys not working"
- Run the program as **Administrator**
- On Windows: Right-click cmd/PowerShell > "Run as administrator"

### "USDC not approved"
- Run `python setup_allowance.py` or go to Polymarket.com and place an order manually

### "Insufficient balance"
- Make sure you have enough USDC in your wallet on the Polygon network

### "Invalid signature"
- Verify that the private key in `.env` is correct and starts with `0x`

### "Could not identify Team1, Draw, and Team2 markets"
- The event URL must point to a match with 3 outcomes (Team1, Draw, Team2)
- Verify that the markets are still active and not closed

## Security

- The private key is NEVER printed or logged
- `.env` is in `.gitignore`
- Orders are signed locally (the key never leaves your computer)
- API credentials are derived automatically from your private key
- 0.5s cooldown prevents accidental orders

## Disclaimer

**WARNING**: This software executes REAL orders with REAL money.

- Orders are executed at the **best available price** (not at a specific price)
- There is no slippage protection - the order sweeps the orderbook
- Only use amounts you can afford to lose
- Test with small amounts first

The author is not responsible for financial losses resulting from the use of this software.

## License

MIT License
