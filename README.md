# OmniProx

OmniProx is a multi-cloud HTTP proxy manager that provides IP rotation and header manipulation capabilities across different cloud providers. It offers a unified interface for managing proxies on various cloud platforms.

> [!IMPORTANT]
> This has been tested from a Linux/MacOS base build. **Windows users should use WSL (Windows Subsystem for Linux)** with Ubuntu 22.04 or later for best compatibility. Native Windows installations may encounter encoding issues, particularly with the Azure provider and python lib support.

## Features

- **Multi-Cloud Support**: Deploy proxies on Azure, GCP, Cloudflare, and Alibaba Cloud
- **IP Rotation**: Different strategies per provider for changing IPs/headers on each request
- **Header Rotation**: All providers rotate X-Forwarded-For and other headers
- **Simple CLI**: Unified command-line interface for all providers
- **Profile Management**: Secure credential storage with multiple profiles
- **Batch Operations**: Create multiple proxies for better rotation
- **Free Tier Optimised**: Leverage cloud provider free tiers where available

## IP Rotation Capabilities

| Provider | True IP Rotation | Header Rotation | Strategy |
|----------|-----------------|-----------------|----------|
| **Azure** | Yes | Yes | Multiple containers with unique IPs |
| **Cloudflare** | No | Yes | Rotates X-Forwarded-For headers per request |
| **GCP** | Limited | Yes | Multiple regions possible, headers rotate |
| **Alibaba** | Limited | Yes | Multiple regions possible, headers rotate |

## Quick Start

### Installation

#### Option 1: Install with pipx (Recommended)

```bash
# Install pipx if you haven't already
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install OmniProx directly from GitHub
pipx install git+https://github.com/ZephrFish/OmniProx.git

# OmniProx is now available globally
omniprox --help
```

#### Option 2: Clone and Install Locally

```bash
# Clone the repository
git clone https://github.com/ZephrFish/OmniProx.git
cd OmniProx

# Install dependencies
pip3 install -r requirements.txt

# Run setup wizard
python3 omniprox.py --setup
```

#### Option 3: Install with pip in Virtual Environment

```bash
# Clone the repository
git clone https://github.com/ZephrFish/OmniProx.git
cd OmniProx

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package
pip install -e .

# OmniProx is now available in the virtual environment
omniprox --setup
```

#### Updating OmniProx (pipx)

```bash
# Update to latest version
pipx upgrade omniprox

# Or reinstall to get latest version
pipx uninstall omniprox
pipx install git+https://github.com/ZephrFish/OmniProx.git
```

### Basic Usage

```bash
# Create proxies with IP rotation
./omni create https://api.yoururlgoeshere.local --provider azure --number 5  # 5 different IPs
./omni create https://api.yoururlgoeshere.local --provider cf --number 10    # 10 workers, rotating headers

# List all proxies
./omni list --all

# Cleanup all proxies
./omni cleanup --all
```

## Example Output
<img width="646" height="520" alt="image" src="https://github.com/user-attachments/assets/79320c7c-9aeb-455f-930d-a4e822f9e965" />

<img width="750" height="643" alt="image" src="https://github.com/user-attachments/assets/f8288e89-51c3-4731-b052-a196086e7377" />

<img width="534" height="679" alt="image" src="https://github.com/user-attachments/assets/e39959ef-dbd3-40e2-8712-1106ab66f8b2" />

## Provider Setup Guides

### 1. Cloudflare Workers Setup

**IP Rotation**: Headers only (X-Forwarded-For rotates each request)

#### Getting Started
1. **Create Account**: https://dash.cloudflare.com/sign-up
   - Use email address
   - Verify email
   - Free plan is sufficient (100,000 requests/day)

2. **Get API Token**:
   - Go to https://dash.cloudflare.com/profile/api-tokens
   - Click "Create Token"
   - Use template "Edit Cloudflare Workers"
   - OR create custom token with permissions:
     - Account > Cloudflare Workers Scripts > Edit
     - Account > Account Settings > Read

3. **Get Account ID**:
   - Go to any domain in your account (or Workers page)
   - Right sidebar shows "Account ID"
   - Copy this 32-character string

4. **Configure OmniProx**:
```bash
python3 omniprox.py --setup
# Select Cloudflare
# Enter API Token: [paste token]
# Enter Account ID: [paste account ID]
```

#### Important Notes
- Subdomain is permanent once set (can't be changed)
- For sensitive ops, create new account with generic subdomain

#### IP Rotation Strategy
```bash
# Create multiple workers for better distribution
./omni create https://yoururlgoeshere.local --provider cf --number 10

# Each request automatically rotates X-Forwarded-For headers
```

---

### 2. Azure Container Instances Setup

**IP Rotation**: TRUE - Each container has unique public IP

#### Getting Started
1. **Create Azure Account**: https://azure.microsoft.com/free/
   - $200 free credit for 30 days
   - 12 months of free services
   - Credit card required (not charged)

2. **Install Azure CLI**:
```bash
# macOS
brew install azure-cli

# Linux
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Windows
# Download from https://aka.ms/installazurecliwindows
```

3. **Login and Get Credentials**:
```bash
# Login
az login

# Get subscription ID
az account show --query id -o tsv

# Create service principal
az ad sp create-for-rbac --name "omniprox" --role Contributor
# Save the output - you need appId, password, tenant
```

4. **Configure OmniProx**:
```bash
python3 omniprox.py --setup
# Select Azure
# Subscription ID: [from az account show]
# Client ID: [appId from service principal]
# Client Secret: [password from service principal]
# Tenant ID: [tenant from service principal]
```

#### IP Rotation Strategy
```bash
# Create 10 containers with 10 different public IPs
./omni create https://yoururlgoeshere.local --provider azure --number 10

# Each container gets unique IP address
# Requests rotate between containers automatically
```

#### Costs
- ~$0.0000125 per second per container
- ~$0.045 per hour for 1 container
- ~$0.45 per hour for 10 containers
- Free tier: Limited, best to cleanup after use

---

### 3. Google Cloud Platform Setup

**IP Rotation**: Headers rotate, limited true IP (different regions possible)

#### Getting Started
1. **Create GCP Account**: https://cloud.google.com/free
   - $300 free credit for 90 days
   - Credit card required (not charged during trial)

2. **Create Project**:
   - Go to https://console.cloud.google.com
   - Create new project: `omniprox`
   - Note the Project ID

3. **Enable APIs**:
```bash
# Install gcloud CLI first
# macOS: brew install google-cloud-sdk
# Linux/Windows: https://cloud.google.com/sdk/install

gcloud auth login
gcloud config set project [PROJECT_ID]

# Enable required APIs
gcloud services enable apigateway.googleapis.com
gcloud services enable servicemanagement.googleapis.com
gcloud services enable servicecontrol.googleapis.com
```

4. **Create Service Account**:
```bash
# Create service account
gcloud iam service-accounts create omniprox \
  --display-name="OmniProx Service Account"

# Get email
gcloud iam service-accounts list

# Create key
gcloud iam service-accounts keys create ~/omniprox-key.json \
  --iam-account=omniprox@[PROJECT_ID].iam.gserviceaccount.com

# Grant permissions
gcloud projects add-iam-policy-binding [PROJECT_ID] \
  --member="serviceAccount:omniprox@[PROJECT_ID].iam.gserviceaccount.com" \
  --role="roles/apigateway.admin"
```

5. **Configure OmniProx**:
```bash
python3 omniprox.py --setup
# Select GCP
# Project ID: [your project ID]
# Service Account Key Path: ~/omniprox-key.json
```

#### IP Rotation Strategy
```bash
# Create multiple gateways
./omni create https://yoururlgoeshere.local --provider gcp --number 5

# Deploy in multiple regions
./omni create https://yoururlgoeshere.local --provider gcp --region us-central1
./omni create https://yoururlgoeshere.local --provider gcp --region europe-west1
```

#### Costs
- Free tier: $300 credit for 90 days
- After: ~$3.00 per million API calls

---

### 4. Alibaba Cloud Setup

**IP Rotation**: Headers rotate, limited true IP (different regions possible)

#### Getting Started
1. **Create Account**: https://www.alibabacloud.com/
   - International version (not .cn)
   - Free trial available in some regions
   - Credit card required

2. **Create RAM User**:
   - Go to RAM Console: https://ram.console.aliyun.com
   - Create User: `omniprox`
   - Access Type: Programmatic access
   - Save AccessKey ID and AccessKey Secret

3. **Attach Permissions**:
   - Select user → Add Permissions
   - Add: `AliyunAPIGatewayFullAccess`

4. **Activate API Gateway**:
   - Go to API Gateway Console
   - Click "Activate Now" if not activated
   - Choose region (cn-hangzhou recommended)

5. **Configure OmniProx**:
```bash
python3 omniprox.py --setup
# Select Alibaba
# Access Key ID: [from RAM user]
# Access Key Secret: [from RAM user]
# Region: cn-hangzhou (or preferred)
```

#### IP Rotation Strategy
```bash
# Create multiple API groups
./omni create https://yoururlgoeshere.local --provider alibaba --number 5

# Deploy in multiple regions (China regions)
./omni create https://yoururlgoeshere.local --provider alibaba --region cn-hangzhou
./omni create https://yoururlgoeshere.local --provider alibaba --region cn-shanghai
./omni create https://yoururlgoeshere.local --provider alibaba --region cn-beijing
```

#### Costs
- No free tier for API Gateway
- Pay-as-you-go pricing
- ~$0.35 per million API calls

---

## Advanced IP Rotation Techniques

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

## Troubleshooting

### Windows Installation

OmniProx is primarily developed and tested on Linux/macOS. For Windows users:

**Recommended: Use WSL2 (Windows Subsystem for Linux)**

```powershell
# Install WSL2 with Ubuntu (run in PowerShell as Administrator)
wsl --install -d Ubuntu-22.04

# After restart, open Ubuntu and install dependencies
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# Clone and install OmniProx
git clone https://github.com/ZephrFish/OmniProx.git
cd OmniProx
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

**Why WSL is recommended:**
- The Azure provider uses inline Node.js scripts that can have encoding issues on native Windows
- Shell command execution is more reliable in a POSIX environment
- Azure CLI integration works more consistently

**If you must use native Windows:**
- Use Python 3.10+ from python.org (not Windows Store)
- Install Git Bash and run commands from there
- Set `PYTHONUTF8=1` environment variable
- The Cloudflare provider works best on native Windows

### Common Issues

**Cannot authenticate**:
- Verify API keys/tokens are correct
- Check permissions are set properly
- Ensure services are activated (especially Alibaba)

**High costs**:
- Azure containers: ~$0.45/hour for 10 containers
- Always cleanup after testing
- Use free tiers wisely


## Development

### Adding New Provider with IP Rotation

```python
from ..core.base import BaseOmniProx
import random

class NewProvider(BaseOmniProx):
    def create(self) -> bool:
        # Create multiple instances for rotation
        num_proxies = getattr(self.args, 'number', 1)

        for i in range(num_proxies):
            # Deploy in different regions if possible
            region = self.get_random_region()
            proxy_url = self.deploy_to_region(region)

            # Configure header rotation
            self.setup_header_rotation(proxy_url)

    def setup_header_rotation(self, proxy_url):
        # Implement X-Forwarded-For rotation
        headers = {
            'X-Forwarded-For': self.generate_ip_chain(),
            'X-Real-IP': self.generate_random_ip(),
            'X-Original-IP': self.generate_random_ip()
        }
        # Apply to proxy configuration

    def generate_random_ip(self):
        # Use realistic IP ranges
        ranges = [
            (73, 255),   # Comcast
            (24, 255),   # Charter
            (71, 255),   # Verizon
            (35, 255),   # GCP
        ]
        base = random.choice(ranges)[0]
        return f"{base}.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}"
```


**Note**: IP rotation features are designed for legitimate use cases like web scraping with permission, API testing, and geographic testing. Do not use for malicious purposes.
