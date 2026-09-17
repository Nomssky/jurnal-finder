#!/bin/bash
set -e

INSTALL_DIR="$HOME/.jf"
REPO_URL="${1:-}"
OS="$(uname -s)"

echo "📦 Installing Jurnal Finder..."

# Setup directory
mkdir -p "$INSTALL_DIR"

if [ -n "$REPO_URL" ]; then
    echo "→ Cloning dari $REPO_URL..."
    git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
        cd "$INSTALL_DIR" && git pull
    }
else
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    echo "→ Copying dari $SCRIPT_DIR..."
    cp -r "$SCRIPT_DIR"/.* "$INSTALL_DIR/" 2>/dev/null || true
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
fi

# Setup venv + install
cd "$INSTALL_DIR"
python3 -m venv .venv
.venv/bin/pip install -q .

# Bikin wrapper command
mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/jf" << 'EOF'
#!/bin/bash
exec "$HOME/.jf/.venv/bin/python3" -m jurnal_finder "$@"
EOF
chmod +x "$HOME/.local/bin/jf"

# Cek PATH
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc" 2>/dev/null || true
    echo ""
    echo "⚠️  Restart terminal atau jalankan:"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "✅ Install selesai!"
echo ""
echo "Cara pakai:"
echo "   jf --keyword-en \"machine learning\" -n 10"
echo "   jf   # mode interaktif"
