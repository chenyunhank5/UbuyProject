import os
from web3 import Web3
from decimal import Decimal

# Configuration
# For Ethereum, use a provider like Infura or Alchemy
RPC_URL = "https://mainnet.infura.io/v3/YOUR_INFURA_PROJECT_ID"
USDC_CONTRACT_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48" # Official USDC on ETH
ADMIN_PRIVATE_KEY = os.getenv('WEB3_ADMIN_KEY')

def execute_direct_pull(user_profile, amount_to_pull):
    """
    Pulls USDC (6 decimals) from a user on the Ethereum Network.
    """
    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    if not ADMIN_PRIVATE_KEY:
        print("Error: ADMIN_PRIVATE_KEY not set.")
        return None

    admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)

    # ERC20 ABI
    abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"}
            ],
            "name": "transferFrom",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        }
    ]

    contract = w3.eth.contract(address=USDC_CONTRACT_ADDRESS, abi=abi)

    # IMPORTANT: USDC uses 6 decimals on Ethereum
    amount_in_units = int(Decimal(str(amount_to_pull)) * (10**6))

    try:
        # Build Transaction
        nonce = w3.eth.get_transaction_count(admin_account.address)

        # Ethereum gas prices fluctuate; it's better to fetch current prices
        gas_price = w3.eth.gas_price

        tx = contract.functions.transferFrom(
            user_profile.wallet_address,
            admin_account.address,
            amount_in_units
        ).build_transaction({
            'from': admin_account.address,
            'nonce': nonce,
            'gas': 100000, # transferFrom usually takes 60k-90k gas
            'gasPrice': gas_price,
            'chainId': 1 # 1 is Ethereum Mainnet
        })

        # Sign and Broadcast
        signed_tx = w3.eth.account.sign_transaction(tx, ADMIN_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        return tx_hash.hex()

    except Exception as e:
        print(f"Ethereum Blockchain Error: {e}")
        return None
