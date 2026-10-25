# Operating OmniProx

Rotation strategies, testing, OPSEC and cost. Back to the [README](../README.md).

## Rotation strategies

### 1. Multi-Provider Rotation
```bash
# Create proxies across all providers for maximum IP diversity
./omni create https://yoururlgoeshere.local --all --number 5

# This creates:
# - 5 Azure containers (5 unique IPs)
# - 5 Cloudflare workers (header rotation)
# - 5 GCP API Gateways
# - 5 Alibaba API Groups
```

### 2. Geographic Distribution
```bash
# Deploy across regions for geographic IP diversity
./omni create https://yoururlgoeshere.local --provider gcp --region us-central1
./omni create https://yoururlgoeshere.local --provider gcp --region europe-west1
./omni create https://yoururlgoeshere.local --provider azure --location eastus
./omni create https://yoururlgoeshere.local --provider azure --location westeurope
./omni create https://yoururlgoeshere.local --provider alibaba --region cn-hangzhou
```

### 3. Round-Robin Client
```python
import random
import requests

# Get all proxy URLs
proxies = [
    "https://proxy1.yoururlgoeshere.local",
    "https://proxy2.yoururlgoeshere.local",
    # ... add all your proxy URLs
]

# Rotate through proxies for each request
for i in range(100):
    proxy = random.choice(proxies)  # Or use round-robin
    response = requests.get(f"{proxy}?url=https://yoururlgoeshere.local")
    print(f"Request {i}: {response.headers.get('X-Forwarded-For')}")
```

### 4. Header Rotation Details

All providers rotate these headers on each request:

| Header | Purpose | Example Value |
|--------|---------|--------------|
| X-Forwarded-For | Client IP chain | "73.24.118.92, 52.41.23.18" |
| X-Real-IP | "Real" client IP | "24.143.72.56" |
| X-Original-IP | Original IP | "71.192.84.103" |
| CF-Connecting-IP | Cloudflare client IP | "47.156.92.201" |
| True-Client-IP | Akamai/Enterprise | "185.23.41.102" |
| X-Client-IP | Generic client IP | "103.21.45.189" |

## Testing IP Rotation

### Test Headers
```bash
# Check what headers are being sent
curl 'https://[proxy-url]?url=https://httpbin.org/headers'
```

### Test Perceived IP
```bash
# Check what IP the target sees
curl 'https://[proxy-url]?url=https://httpbin.org/ip'

# Azure will show different IPs for each container
# Others will show provider's IP but different X-Forwarded-For
```

### Automated Rotation Test
```bash
# Test 10 requests to see rotation
for i in {1..10}; do
  echo "Request $i:"
  curl -s 'https://[proxy-url]?url=https://httpbin.org/headers' | grep -E "X-Forwarded-For|X-Real-IP"
  echo "---"
done
```

## Security & OPSEC

### Best Practices
1. **Use Multiple Accounts**: Create separate cloud accounts for different projects
2. **Rotate Credentials**: Regularly update API keys and tokens
3. **Geographic Distribution**: Spread proxies across regions
4. **Provider Diversity**: Use multiple cloud providers
5. **Cleanup Regular**: Delete unused proxies to avoid costs and detection

### Detection Avoidance
- Rotate between multiple proxies
- Use realistic header values
- Implement request delays
- Vary user agents
- Use residential IP ranges in headers

## Cost Optimisation

### Free Tier Limits
| Provider | Free Tier | Duration |
|----------|-----------|----------|
| Cloudflare | 100,000 requests/day | Forever |
| GCP | $300 credit | 90 days |
| Azure | $200 credit | 30 days |
| Alibaba | None | N/A |

### Cost-Saving Tips
1. **Cleanup after use**: `./omni cleanup --all`
2. **Use Cloudflare for testing**: Permanent free tier
3. **Azure containers are expensive**: Use sparingly
4. **Schedule cleanup**: Automate deletion after X hours
5. **Monitor usage**: Check cloud consoles regularly

