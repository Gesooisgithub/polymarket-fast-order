"""
Script to wrap USDC.e into pUSD on Polygon (CLOB V2 collateral).

Run this when you have USDC.e in your wallet and need pUSD to trade on
Polymarket V2. Wrapping is enforced onchain by the CollateralOnramp contract.

Two-step flow:
    1. Approve the Onramp contract to spend your USDC.e
    2. Call onramp.wrap(USDC.e, you, amount) -> pUSD is minted to your wallet

Requires:
    - POLYMARKET_PRIVATE_KEY in .env
    - USDC.e on the wallet (Polygon)
    - ~0.01 POL/MATIC for gas (2 transactions)

For EOA wallets (signature_type=0), the recipient is your own wallet address.
For Proxy/Safe wallets, change RECIPIENT to your proxy address.

Usage:
    python wrap_usdce.py
"""

import os
import sys
import time

from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

# Polygon Mainnet RPC - try multiple options
POLYGON_RPCS = [
    "https://polygon.llamarpc.com",
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon",
]

# Contract addresses (Polygon Mainnet) — CLOB V2
USDCE_ADDRESS  = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e (bridged)
PUSD_ADDRESS   = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"  # pUSD (V2 collateral)
ONRAMP_ADDRESS = "0x93070a847efEf7F70739046A929D47a521F5B8ee"  # CollateralOnramp

# ERC20 ABI (approve / allowance / balanceOf)
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount",  "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "owner",   "type": "address"},
            {"name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

# CollateralOnramp ABI (only wrap needed)
ONRAMP_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_asset",  "type": "address"},
            {"name": "_to",     "type": "address"},
            {"name": "_amount", "type": "uint256"}
        ],
        "name": "wrap",
        "outputs": [],
        "type": "function"
    }
]

MAX_UINT256 = 2**256 - 1


def connect_polygon():
    """Try several public RPCs and return the first connected Web3 instance."""
    for rpc in POLYGON_RPCS:
        try:
            print(f"  Trying {rpc}...")
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 10}))
            if w3.is_connected():
                print(f"  Connected!")
                return w3
        except Exception as e:
            print(f"  Failed: {e}")
            continue
    return None


def prompt_amount(max_amount: float) -> float:
    """Ask the user how many USDC.e to wrap. Returns 0 to cancel."""
    print()
    print(f"Available USDC.e: ${max_amount:.2f}")
    print("How many USDC.e do you want to wrap into pUSD?")
    print("  - Type a number (e.g. 50)")
    print("  - Type 'all' to wrap the full balance")
    print("  - Press Enter to cancel")

    try:
        raw = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 0.0

    if not raw:
        return 0.0

    if raw == "all":
        return max_amount

    try:
        amount = float(raw)
    except ValueError:
        print("ERROR: invalid number.")
        return 0.0

    if amount <= 0:
        print("ERROR: amount must be positive.")
        return 0.0

    if amount > max_amount:
        print(f"ERROR: not enough USDC.e (have ${max_amount:.2f}).")
        return 0.0

    return amount


def main():
    print("=" * 60)
    print("USDC.e -> pUSD Wrap (Polymarket CLOB V2)")
    print("=" * 60)
    print()

    # Load credentials
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    if not private_key:
        print("ERROR: POLYMARKET_PRIVATE_KEY not found in .env")
        return

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    # Connect
    print("Connecting to Polygon...")
    w3 = connect_polygon()
    if not w3 or not w3.is_connected():
        print("ERROR: Could not connect to any Polygon RPC")
        return

    print(f"Chain ID: {w3.eth.chain_id}")
    print()

    # Account
    account = w3.eth.account.from_key(private_key)
    wallet_address = account.address
    print(f"Wallet Address: {wallet_address}")

    # MATIC balance
    matic_balance = w3.eth.get_balance(wallet_address)
    matic_balance_eth = w3.from_wei(matic_balance, 'ether')
    print(f"MATIC Balance: {matic_balance_eth:.4f} MATIC")

    if matic_balance_eth < 0.01:
        print("WARNING: Low MATIC balance. Need at least 0.01 MATIC for gas.")
        return

    # Token contracts
    usdce_addr  = Web3.to_checksum_address(USDCE_ADDRESS)
    pusd_addr   = Web3.to_checksum_address(PUSD_ADDRESS)
    onramp_addr = Web3.to_checksum_address(ONRAMP_ADDRESS)

    usdce  = w3.eth.contract(address=usdce_addr,  abi=ERC20_ABI)
    pusd   = w3.eth.contract(address=pusd_addr,   abi=ERC20_ABI)
    onramp = w3.eth.contract(address=onramp_addr, abi=ONRAMP_ABI)

    # Balances
    usdce_balance_raw = usdce.functions.balanceOf(wallet_address).call()
    pusd_balance_raw  = pusd.functions.balanceOf(wallet_address).call()
    usdce_balance = usdce_balance_raw / 1e6
    pusd_balance  = pusd_balance_raw  / 1e6

    print(f"USDC.e Balance: ${usdce_balance:.2f}")
    print(f"pUSD Balance:   ${pusd_balance:.2f}")
    print()

    if usdce_balance <= 0:
        print("Nothing to wrap (USDC.e balance is zero).")
        return

    # Ask amount
    amount_human = prompt_amount(usdce_balance)
    if amount_human <= 0:
        print("Cancelled.")
        return

    amount_raw = int(round(amount_human * 1e6))  # 6 decimals
    print()
    print(f"Wrapping ${amount_human:.2f} USDC.e -> pUSD")
    print(f"Recipient: {wallet_address} (EOA)")
    print()

    # ---- Step 1: approve onramp to spend USDC.e ----
    current_allowance = usdce.functions.allowance(wallet_address, onramp_addr).call()

    if current_allowance >= amount_raw:
        print(f"Step 1/2: USDC.e already approved for Onramp (allowance OK).")
    else:
        print(f"Step 1/2: Approving USDC.e for Onramp...")
        try:
            nonce = w3.eth.get_transaction_count(wallet_address)
            gas_price = w3.eth.gas_price

            # Approve unlimited so future wraps don't need re-approval
            tx = usdce.functions.approve(onramp_addr, MAX_UINT256).build_transaction({
                'from': wallet_address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': int(gas_price * 1.1),
                'chainId': 137,
            })

            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"  TX Hash: {tx_hash.hex()}")
            print(f"  Waiting for confirmation...")

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt['status'] != 1:
                print("  X Approve transaction failed.")
                return
            print("  Approved successfully!")
        except Exception as e:
            print(f"  X Error approving: {e}")
            return

        # Small delay before next tx
        print()
        print("  Waiting 5 seconds before wrapping...")
        time.sleep(5)

    print()

    # ---- Step 2: wrap ----
    print(f"Step 2/2: Wrapping {amount_human:.2f} USDC.e -> pUSD...")
    try:
        nonce = w3.eth.get_transaction_count(wallet_address)
        gas_price = w3.eth.gas_price

        tx = onramp.functions.wrap(
            usdce_addr,
            wallet_address,
            amount_raw,
        ).build_transaction({
            'from': wallet_address,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': int(gas_price * 1.1),
            'chainId': 137,
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"  TX Hash: {tx_hash.hex()}")
        print(f"  Waiting for confirmation...")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt['status'] != 1:
            print("  X Wrap transaction failed.")
            return
        print("  Wrapped successfully!")
    except Exception as e:
        print(f"  X Error wrapping: {e}")
        return

    print()
    print("-" * 60)

    # Final balances
    new_usdce_balance = usdce.functions.balanceOf(wallet_address).call() / 1e6
    new_pusd_balance  = pusd.functions.balanceOf(wallet_address).call()  / 1e6
    print(f"New USDC.e Balance: ${new_usdce_balance:.2f}")
    print(f"New pUSD Balance:   ${new_pusd_balance:.2f}")
    print()
    print("Done. Now you can run:")
    print("  python setup_allowance.py")
    print("to approve pUSD on the V2 CTF Exchange contracts (if not done already).")
    print()


if __name__ == "__main__":
    main()
