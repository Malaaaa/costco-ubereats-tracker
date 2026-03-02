# Shared configuration constants for Costco UberEats Tracker

# Windows Chrome path (launched via PowerShell from WSL)
CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

# Isolated Chrome profile for scraping (avoids conflicts with personal browsing)
PROFILE_PATH = "C:\\ubereats_automation_costco"

# Chrome DevTools Protocol debugging port
CDP_PORT = "9322"

# Base64-encoded GPS payload for 88 Queen Street E, Toronto
# This injects coordinates directly into the UberEats search payload,
# bypassing the address modal reliably across logged-in/out states.
PAYLOAD_ADDRESS = (
    "JTdCJTIyYWRkcmVzcyUyMiUzQSUyMjg4JTIwUXVlZW4lMjBTdCUyMEUlMjIl"
    "MkMlMjJyZWZlcmVuY2UlMjIlM0ElMjJmZTE1NjY1OS1iNDU0LTc4ZmItOTM3"
    "NS03YmRkN2Y0YzA0MjElMjIlMkMlMjJyZWZlcmVuY2VUeXBlJTIyJTNBJTIy"
    "dWJlcl9wbGFjZXMlMjIlMkMlMjJsYXRpdHVkZSUyMiUzQTQzLjY1MzY4MTgl"
    "MkMlMjJsb25naXR1ZGUlMjIlM0EtNzkuMzc0NjUyMiU3RA%3D%3D"
)

# Scroll tuning parameters
MAX_SCROLLS = 300
SCROLL_DISTANCE = 4500
SCROLL_DELAY = 0.9            # seconds between scrolls
STALL_THRESHOLD = 6           # iterations without scroll progress before stopping
INITIAL_LOAD_DELAY = 5        # seconds to wait for initial page load
STORE_LOAD_DELAY = 6          # seconds to wait after navigating to a store

# UberEats UI text patterns to exclude from product names
EXCLUDED_NAME_PREFIXES = [
    "plus small", "plus medium", "plus large",
    "sold out", "deal", "trending",
    "offers available", "buy 1", "get 1",
]

# Deal keyword indicators in overlay text
DEAL_KEYWORDS = ["off", "save", "discount", "expires"]
