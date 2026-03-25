"""
Setup script to approve USDC.e spending on Polymarket contracts.

Run this ONCE before using the trading bot.
Requires MATIC/POL in your wallet for gas fees (~0.01 MATIC per approval).

Usage:
    python setup_allowance.py
"""

import os
import time
from dotenv import load_dotenv
from web3 import Web3

# Load environment variables
load_dotenv()

# Polygon Mainnet RPC - try multiple options
POLYGON_RPCS = [
    "https://polygon.llamarpc.com",
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon",
]

# Contract addresses (Polygon Mainnet)
USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e (Bridged)
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # Conditional Token Framework (ERC1155)

# Polymarket contracts that need USDC approval
POLYMARKET_CONTRACTS = {
    "CTF Exchange": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
    "Neg Risk CTF Exchange": "0xC5d563A36AE78145C45a50134d48A1215220f80a",
    "Neg Risk Adapter": "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
}

# Contracts that need CTF token approval (for selling shares)
CTF_OPERATORS = {
    "CTF Exchange": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
    "Neg Risk CTF Exchange": "0xC5d563A36AE78145C45a50134d48A1215220f80a",
    "Neg Risk Adapter": "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
}

# ERC20 ABI (only approve function)
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
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

# ERC1155 ABI (for CTF token approval)
ERC1155_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"}
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "operator", "type": "address"}
        ],
        "name": "isApprovedForAll",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

# Maximum uint256 for unlimited approval
MAX_UINT256 = 2**256 - 1


def main():
    print("=" * 60)
    print("Polymarket Allowance Setup")
    print("=" * 60)
    print()

    # Load credentials
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    if not private_key:
        print("ERROR: POLYMARKET_PRIVATE_KEY not found in .env")
        return

    # Ensure 0x prefix
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    # Connect to Polygon - try multiple RPCs
    print("Connecting to Polygon...")
    w3 = None
    for rpc in POLYGON_RPCS:
        try:
            print(f"  Trying {rpc}...")
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 10}))
            if w3.is_connected():
                print(f"  Connected!")
                break
        except Exception as e:
            print(f"  Failed: {e}")
            continue

    if not w3 or not w3.is_connected():
        print("ERROR: Could not connect to any Polygon RPC")
        return

    print(f"Chain ID: {w3.eth.chain_id}")
    print()

    # Get account from private key
    account = w3.eth.account.from_key(private_key)
    wallet_address = account.address
    print(f"Wallet Address: {wallet_address}")

    # Check MATIC balance
    matic_balance = w3.eth.get_balance(wallet_address)
    matic_balance_eth = w3.from_wei(matic_balance, 'ether')
    print(f"MATIC Balance: {matic_balance_eth:.4f} MATIC")

    if matic_balance_eth < 0.01:
        print("WARNING: Low MATIC balance. You need at least 0.01 MATIC for gas.")
        return

    # Check USDC.e balance
    usdc_contract = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_E_ADDRESS),
        abi=ERC20_ABI
    )
    usdc_balance = usdc_contract.functions.balanceOf(wallet_address).call()
    usdc_balance_formatted = usdc_balance / 1e6  # USDC has 6 decimals
    print(f"USDC.e Balance: ${usdc_balance_formatted:.2f}")
    print()

    # Check and set allowances
    print("Checking allowances...")
    print("-" * 60)

    for name, contract_address in POLYMARKET_CONTRACTS.items():
        contract_address = Web3.to_checksum_address(contract_address)

        # Check current allowance
        current_allowance = usdc_contract.functions.allowance(
            wallet_address,
            contract_address
        ).call()

        if current_allowance >= MAX_UINT256 // 2:
            print(f"✓ {name}: Already approved (unlimited)")
            continue

        print(f"○ {name}: Needs approval")
        print(f"  Approving unlimited USDC.e spending...")

        try:
            # Build transaction
            nonce = w3.eth.get_transaction_count(wallet_address)
            gas_price = w3.eth.gas_price

            tx = usdc_contract.functions.approve(
                contract_address,
                MAX_UINT256
            ).build_transaction({
                'from': wallet_address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': int(gas_price * 1.1),  # 10% buffer
                'chainId': 137
            })

            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            print(f"  TX Hash: {tx_hash.hex()}")
            print(f"  Waiting for confirmation...")

            # Wait for receipt
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt['status'] == 1:
                print(f"  ✓ Approved successfully!")
            else:
                print(f"  ✗ Transaction failed!")

        except Exception as e:
            print(f"  ✗ Error: {e}")

        print()
        # Wait between approvals to avoid rate limiting
        print("  Waiting 15 seconds before next operation...")
        time.sleep(15)

    print("-" * 60)
    print()

    # Now approve CTF tokens (ERC1155) for selling shares
    print("Checking CTF token approvals (for selling shares)...")
    print("-" * 60)

    ctf_contract = w3.eth.contract(
        address=Web3.to_checksum_address(CTF_ADDRESS),
        abi=ERC1155_ABI
    )

    for name, operator_address in CTF_OPERATORS.items():
        operator_address = Web3.to_checksum_address(operator_address)

        # Check if already approved
        is_approved = ctf_contract.functions.isApprovedForAll(
            wallet_address,
            operator_address
        ).call()

        if is_approved:
            print(f"✓ CTF -> {name}: Already approved")
            continue

        print(f"○ CTF -> {name}: Needs approval")
        print(f"  Approving CTF token transfers...")

        try:
            nonce = w3.eth.get_transaction_count(wallet_address)
            gas_price = w3.eth.gas_price

            tx = ctf_contract.functions.setApprovalForAll(
                operator_address,
                True
            ).build_transaction({
                'from': wallet_address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': int(gas_price * 1.1),
                'chainId': 137
            })

            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            print(f"  TX Hash: {tx_hash.hex()}")
            print(f"  Waiting for confirmation...")

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt['status'] == 1:
                print(f"  ✓ Approved successfully!")
            else:
                print(f"  ✗ Transaction failed!")

        except Exception as e:
            print(f"  ✗ Error: {e}")

        print()
        print("  Waiting 15 seconds before next operation...")
        time.sleep(15)

    print("-" * 60)
    print()
    print("Setup complete! You can now run the trading bot:")
    print("  python main.py")
    print()


if __name__ == "__main__":
    main()
