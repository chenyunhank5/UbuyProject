from eth_account import Account

# Enable the HD wallet features
Account.enable_unaudited_hdwallet_features()

# Your 12-word phrase
seed_phrase = "mixture culture winner worry item left corn session domain solution dizzy shadow"

# Standard derivation path for Ethereum (MetaMask/TrustWallet)
# We use account_path for newer versions of eth-account
account = Account.from_mnemonic(seed_phrase, account_path="m/44'/60'/0'/0/0")

print("-" * 40)
print(f"Address:     {account.address}")
print(f"Private Key: {account.key.hex()}")
print("-" * 40)
print("1. Copy the Private Key above.")
print("2. Paste it into ADMIN_PRIVATE_KEY in your utils.py.")
print("3. DELETE THIS FILE (get_key.py) when finished for security.")
