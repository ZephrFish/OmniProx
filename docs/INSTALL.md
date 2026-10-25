# Installation

Back to the [README](../README.md).


## Option 1: Install with pipx (Recommended)

```bash
# Install pipx if you haven't already
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install OmniProx directly from GitHub
pipx install git+https://github.com/ZephrFish/OmniProx.git

# OmniProx is now available globally
omniprox --help
```

## Option 2: Clone and Install Locally

```bash
# Clone the repository
git clone https://github.com/ZephrFish/OmniProx.git
cd OmniProx

# Install dependencies
pip3 install -r requirements.txt

# Run setup wizard
python3 omniprox.py --setup
```

## Option 3: Install with pip in Virtual Environment

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

## Updating OmniProx (pipx)

```bash
# Update to latest version
pipx upgrade omniprox

# Or reinstall to get latest version
pipx uninstall omniprox
pipx install git+https://github.com/ZephrFish/OmniProx.git
```


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


