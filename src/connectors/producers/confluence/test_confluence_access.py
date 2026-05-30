import json
import os
import sys

try:
    from atlassian import Confluence
except ImportError:
    print("Error: 'atlassian-python-api' is not installed.")
    print("Please run: pip install atlassian-python-api")
    sys.exit(1)

def main():
    """Test Confluence API access using configuration from .config.json."""
    config_path = os.path.join(os.path.dirname(__file__), '.config.json')
    
    if not os.path.exists(config_path):
        print(f"❌ Error: Configuration file not found at {config_path}")
        print("Please copy .config.example.json to .config.json and add your credentials.")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error reading JSON config: {e}")
        sys.exit(1)

    accounts = config.get("account", [])
    if not accounts:
        print("❌ Error: No accounts found in .config.json")
        sys.exit(1)

    # Use the first account for testing
    account = accounts[0]
    url = account.get("url")
    email = account.get("email")
    api_token = account.get("api_token")

    if not all([url, email, api_token]):
        print("❌ Error: Missing 'url', 'email', or 'api_token' in .config.json account configuration.")
        sys.exit(1)

    print(f"Connecting to Confluence at {url} as {email}...")

    try:
        confluence = Confluence(
            url=url,
            username=email,
            password=api_token,
            cloud=True
        )

        # Test 1: Fetch a few spaces to validate read access
        print("\nFetching up to 5 spaces...")
        spaces = confluence.get_all_spaces(start=0, limit=5)
        
        if spaces and 'results' in spaces:
            print(f"✅ Successfully retrieved {len(spaces['results'])} spaces!")
            for space in spaces['results']:
                print(f"  - Space: {space.get('name')} (Key: {space.get('key')})")
        else:
            print("⚠️ Connected, but no spaces found or unexpected response format.")

    except Exception as e:
        print(f"\n❌ Failed to connect or retrieve data from Confluence:")
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()