#!/bin/bash
set -e

INSTALL_DIR="$HOME/.jf"
REPO_URL="${1:-}"

echo "📦 Installing Jurnal Finder..."

# ── Cek Python ──────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python3 tidak ditemukan. Install Python 3.10+ dulu."
    echo "   Debian/Ubuntu: sudo apt install python3 python3-venv"
    echo "   macOS        : brew install python"
    exit 1
fi

mkdir -p "$INSTALL_DIR"

# ── Ambil source code ───────────────────────────────────────────────────────
if [ -n "$REPO_URL" ]; then
    echo "→ Cloning dari $REPO_URL..."
    if [ -d "$INSTALL_DIR/.git" ]; then
        git -C "$INSTALL_DIR" pull --quiet
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
else
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

    if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
        echo "→ Script sudah berada di $INSTALL_DIR — lewati copy."
    else
        echo "→ Copying dari $SCRIPT_DIR..."
        # Copy isi SCRIPT_DIR (termasuk file hidden) tanpa artefak build/venv/repo.
        # CATATAN: jangan pakai `cp -r "$SCRIPT_DIR"/.*` — glob `.*` bisa ikut
        # menyalin `.` dan `..` sehingga seluruh isi parent (mis. $HOME) tersedot.
        (
            cd "$SCRIPT_DIR"
            find . -mindepth 1 -maxdepth 1 \
                ! -name '.git' \
                ! -name '.venv' \
                ! -name 'venv' \
                ! -name 'build' \
                ! -name 'dist' \
                ! -name '.opencode' \
                ! -name 'node_modules' \
                ! -name '__pycache__' \
                ! -name '*.egg-info' \
                -exec cp -r {} "$INSTALL_DIR"/ \;
        )
    fi
fi

# ─ Setup venv + install ────────────────────────────────────────────────────
cd "$INSTALL_DIR"
if ! python3 -m venv .venv; then
    echo "❌ Gagal membuat virtualenv. Pastikan paket venv terpasang"
    echo "   (Debian/Ubuntu: sudo apt install python3-venv)."
    exit 1
fi
.venv/bin/pip install -q --upgrade pip
if ! .venv/bin/pip install -q .; then
    echo "❌ Gagal memasang dependensi. Cek koneksi internet lalu coba lagi."
    exit 1
fi

# ─ Wrapper command dengan auto-update ──────────────────────────────────────
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/jf" << 'WRAPPER'
#!/bin/bash
INSTALL_DIR="$HOME/.jf"

# Auto-update: pull latest setiap kali dijalankan (hanya jika tree bersih)
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR" || exit 1
    if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
        CURRENT=$(git rev-parse HEAD 2>/dev/null)
        git pull --quiet 2>/dev/null
        NEW=$(git rev-parse HEAD 2>/dev/null)
        if [ -n "$CURRENT" ] && [ "$CURRENT" != "$NEW" ]; then
            echo "🔄 Update ditemukan! Installing..."
            .venv/bin/pip install -q . || echo "⚠ Gagal update, lanjut versi lama."
        fi
    fi
fi

exec "$INSTALL_DIR/.venv/bin/python3" -m jurnal_finder "$@"
WRAPPER
chmod +x "$HOME/.local/bin/jf"

# ─ Cek PATH ───────────────────────────────────────────────────────────────
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
        for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
            [ -f "$rc" ] || continue
            grep -q 'export PATH="\$HOME/.local/bin:\$PATH"' "$rc" 2>/dev/null && continue
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
        done
        echo ""
        echo "⚠️  Restart terminal atau jalankan:"
        echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac

echo ""
echo "✅ Install selesai!"
echo ""
echo "Cara pakai:"
echo "   jf --keyword-en \"machine learning\" -n 10"
echo "   jf   # mode interaktif"
echo ""
echo "💡 Auto-update: jf akan otomatis update setiap kali dijalankan"