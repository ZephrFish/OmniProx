#!/bin/bash
# OmniProx Quick Setup Script

echo "======================================================"
echo "           OmniProx Quick Setup                      "
echo "======================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[X] Python 3 is required but not installed"
    exit 1
fi
echo "[OK] Python 3 found"

# Install base requirements
echo ""
echo "Installing base requirements..."
pip3 install -q tldextract requests 2>/dev/null

# Check which providers to install
echo ""
echo "Which cloud providers do you want to use?"
echo "(You can install multiple, separated by spaces)"
echo ""
echo "  1) cloudflare  - Cloudflare Workers (Recommended - 100k free/day)"
echo "  2) gcp         - Google Cloud Platform API Gateway"
echo "  3) azure       - Microsoft Azure Container Instances"
echo "  4) alibaba     - Alibaba Cloud API Gateway"
echo "  5) all         - Install all providers"
echo ""
read -p "Enter numbers or names (default: 1): " providers

# Default to Cloudflare if nothing selected
if [ -z "$providers" ]; then
    providers="1"
fi

echo ""
echo "Installing provider dependencies..."

for provider in $providers; do
    case $provider in
        1|cloudflare|cf)
            # Already installed with base requirements (requests)
            echo "[OK] Cloudflare ready"
            ;;
        2|gcp)
            echo "Installing GCP requirements..."
            pip3 install -q google-cloud-api-gateway google-cloud-resource-manager
            echo "[OK] GCP ready"
            ;;
        3|azure|az)
            echo "Installing Azure requirements..."
            pip3 install -q azure-mgmt-containerinstance azure-mgmt-resource azure-identity
            echo "[OK] Azure ready"
            ;;
        4|alibaba)
            echo "Installing Alibaba requirements..."
            pip3 install -q aliyun-python-sdk-cloudapi
            echo "[OK] Alibaba ready"
            ;;
        5|all)
            echo "Installing all provider requirements..."
            pip3 install -q google-cloud-api-gateway google-cloud-resource-manager
            pip3 install -q azure-mgmt-containerinstance azure-mgmt-resource azure-identity
            pip3 install -q aliyun-python-sdk-cloudapi
            echo "[OK] All providers ready"
            ;;
        *)
            echo "[?] Unknown provider: $provider"
            ;;
    esac
done

# Create config directory
echo ""
echo "Setting up configuration..."
mkdir -p ~/.omniprox

# Check if profiles.ini exists
if [ -f ~/.omniprox/profiles.ini ]; then
    echo "[OK] Configuration file already exists"
    read -p "Do you want to overwrite it? (y/n): " overwrite
    if [ "$overwrite" != "y" ]; then
        echo "[OK] Keeping existing configuration"
    else
        # Create default config
        cat > ~/.omniprox/profiles.ini << EOF
[cloudflare:default]
api_token = your_cloudflare_api_token
account_id = your_cloudflare_account_id

[gcp:default]
project_id = your_gcp_project
credentials_path = /path/to/service-account.json

[azure:default]
subscription_id = your_azure_subscription
tenant_id = your_azure_tenant
client_id = your_azure_client_id
client_secret = your_azure_client_secret

[alibaba:default]
access_key_id = your_alibaba_key
access_key_secret = your_alibaba_secret
region = cn-hangzhou
EOF
        echo "[OK] Created default configuration template"
    fi
else
    # Create default config
    cat > ~/.omniprox/profiles.ini << EOF
[cloudflare:default]
api_token = your_cloudflare_api_token
account_id = your_cloudflare_account_id

[gcp:default]
project_id = your_gcp_project
credentials_path = /path/to/service-account.json

[azure:default]
subscription_id = your_azure_subscription
tenant_id = your_azure_tenant
client_id = your_azure_client_id
client_secret = your_azure_client_secret

[alibaba:default]
access_key_id = your_alibaba_key
access_key_secret = your_alibaba_secret
region = cn-hangzhou
EOF
    echo "[OK] Created configuration template at ~/.omniprox/profiles.ini"
fi

# Make omni command executable
chmod +x omni 2>/dev/null
chmod +x omniprox.py 2>/dev/null

echo ""
echo "======================================================"
echo "           Setup Complete!                           "
echo "======================================================"
echo ""
echo "Next steps:"
echo "1. Run: python3 omniprox.py --setup"
echo "   This will guide you through setting up each provider"
echo ""
echo "2. Or manually edit: ~/.omniprox/profiles.ini"
echo "   Add your actual API credentials"
echo ""
echo "3. Start using OmniProx:"
echo "   ./omni create https://example.com --provider cloudflare"
echo "   ./omni list"
echo "   ./omni cleanup"
echo ""
echo "For help: ./omni --help"
echo ""