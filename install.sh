#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# Jurnal Finder — installer otomatis (Linux / macOS)
#
# Cara pakai paling mudah (satu baris):
#   curl -fsSL https://raw.githubusercontent.com/Nomssky/jurnal-finder/main/install.sh | bash
#
# Atau kalau repo sudah ada di komputer:
#   bash install.sh
#
# Installer ini otomatis:
#   1. Memastikan Python 3.10+ tersedia (coba pasang bila belum ada)
#   2. Mengunduh kode Jurnal Finder
#   3. Membuat lingkungan terisolasi + memasang dependensi
#   4. Mendaftarkan perintah `jf`
# ═══════════════════════════════════════════════════════════════════════════

set -e

REPO_URL="${JF_REPO_URL:-https://github.com/Nomssky/jurnal-finder.git}"
INSTALL_DIR="${JF_INSTALL_DIR:-$HOME/.jf}"
BIN_DIR="$HOME/.local/bin"

# ── Warna & pesan ramah ─────────────────────────────────────────────────────
if [ -t 1 ]; then
    G="\033[92m"; Y="\033[93m"; R="\033[91m"; C="\033[96m"; B="\033[1m"; N="\033[0m"
else
    G=""; Y=""; R=""; C=""; B=""; N=""
fi
say()  { printf "%b\n" "$1"; }
ok()   { printf "${G}✓${N} %s\n" "$1"; }
warn() { printf "${Y}⚠${N} %s\n" "$1"; }
err()  { printf "${R}✗${N} %s\n" "$1"; }
step() { printf "\n${B}%s${N}\n" "$1"; }

banner() {
    say ""
    say "${B}╔══════════════════════════════════════════════╗${N}"
    say "${B}║          📚  JURNAL FINDER — Installer        ║${N}"
    say "${B}║   Cari jurnal gratis → Download → Excel       ║${N}"
    say "${B}╚══════════════════════════════════════════════╝${N}"
}

# ── Pastikan Python 3.10+ ───────────────────────────────────────────────────
find_python() {
    for p in python3 python; do
        if command -v "$p" >/dev/null 2>&1; then
            if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
                echo "$p"; return 0
            fi
        fi
    done
    return 1
}

try_install_python() {
    step "Python 3.10+ belum ada — mencoba memasang otomatis..."
    if command -v brew >/dev/null 2>&1; then
        ok "Memasang Python via Homebrew..."
        brew install python || return 1
    elif command -v apt-get >/dev/null 2>&1; then
        ok "Memasang Python via apt (butuh sandi sudo)..."
        sudo apt-get update -y && sudo apt-get install -y python3 python3-venv python3-pip || return 1
    elif command -v dnf >/dev/null 2>&1; then
        ok "Memasang Python via dnf (butuh sandi sudo)..."
        sudo dnf install -y python3 python3-pip || return 1
    elif command -v pacman >/dev/null 2>&1; then
        ok "Memasang Python via pacman (butuh sandi sudo)..."
        sudo pacman -Sy --noconfirm python || return 1
    elif command -v zypper >/dev/null 2>&1; then
        ok "Memasang Python via zypper (butuh sandi sudo)..."
        sudo zypper install -y python3 python3-pip || return 1
    else
        return 1
    fi
}

ensure_python() {
    PY="$(find_python)" && return 0
    if try_install_python && PY="$(find_python)"; then
        return 0
    fi
    err "Gagal menyiapkan Python 3.10+ secara otomatis."
    say ""
    say "  Silakan pasang Python 3.10+ dulu, lalu jalankan installer ini lagi:"
    say "    • macOS        : brew install python   (atau unduh di python.org)"
    say "    • Ubuntu/Debian: sudo apt install python3 python3-venv"
    say "    • Fedora       : sudo dnf install python3"
    say "    • Arch         : sudo pacman -S python"
    say ""
    exit 1
}

# ── Unduh kode sumber ───────────────────────────────────────────────────────
# Prioritas: folder repo lokal (bila installer dijalankan sebagai file) →
# git clone → unduh tarball via curl/wget (tanpa perlu git).
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

copy_local() {
    local src="$1"
    mkdir -p "$INSTALL_DIR"
    if [ "$src" = "$INSTALL_DIR" ]; then
        ok "Repo sudah berada di $INSTALL_DIR"
        return 0
    fi
    ( cd "$src"
      find . -mindepth 1 -maxdepth 1 \
          ! -name '.git' ! -name '.venv' ! -name 'venv' \
          ! -name 'build' ! -name 'dist' ! -name '.opencode' \
          ! -name 'node_modules' ! -name '__pycache__' ! -name '*.egg-info' \
          -exec cp -r {} "$INSTALL_DIR"/ \; )
}

download_source() {
    step "Mengunduh Jurnal Finder..."
    mkdir -p "$INSTALL_DIR"

    # 1) Folder lokal (installer dijalankan dari repo yang sudah ada)
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
        ok "Memakai kode dari folder ini: $SCRIPT_DIR"
        copy_local "$SCRIPT_DIR"
        return 0
    fi

    # 2) git clone (bila git tersedia)
    if command -v git >/dev/null 2>&1; then
        if [ -d "$INSTALL_DIR/.git" ]; then
            ok "Memperbarui repo yang sudah ada..."
            if git -C "$INSTALL_DIR" pull --quiet 2>/dev/null; then return 0; fi
            warn "Gagal update via git, mencoba unduh ulang..."
        else
            if git clone --depth 1 --quiet "$REPO_URL" "$INSTALL_DIR" 2>/dev/null; then
                ok "Berhasil mengunduh via git"
                return 0
            fi
            warn "git clone gagal, mencoba cara lain..."
        fi
    fi

    # 3) Unduh tarball tanpa git
    local tarball="$INSTALL_DIR/.jf-src.tar.gz"
    # Ubah URL repo (https://github.com/user/repo.git) → URL arsip main.
    local base="${REPO_URL%.git}"
    local tar_url="$base/archive/refs/heads/main.tar.gz"
    if ! printf '%s' "$base" | grep -q 'github.com'; then
        err "Tidak punya git dan URL repo bukan GitHub — tidak bisa lanjut."
        exit 1
    fi

    local dl=""
    command -v curl >/dev/null 2>&1 && dl="curl"
    [ -z "$dl" ] && command -v wget >/dev/null 2>&1 && dl="wget"
    if [ -z "$dl" ]; then
        err "Butuh 'curl', 'wget', atau 'git' untuk mengunduh. Tidak ada yang tersedia."
        exit 1
    fi

    rm -rf "$INSTALL_DIR/.jf-tmp"; mkdir -p "$INSTALL_DIR/.jf-tmp"
    if [ "$dl" = "curl" ]; then
        curl -fsSL "$tar_url" -o "$tarball" || { err "Gagal mengunduh dari $tar_url"; exit 1; }
    else
        wget -q "$tar_url" -O "$tarball" || { err "Gagal mengunduh dari $tar_url"; exit 1; }
    fi
    tar -xzf "$tarball" -C "$INSTALL_DIR/.jf-tmp" || { err "Gagal membuka arsip."; exit 1; }
    rm -f "$tarball"

    local extracted
    extracted="$(find "$INSTALL_DIR/.jf-tmp" -mindepth 1 -maxdepth 1 -type d | head -n1)"
    if [ -z "$extracted" ]; then
        err "Isi arsip tidak dikenali."
        exit 1
    fi
    ( cd "$extracted"
      find . -mindepth 1 -maxdepth 1 -exec cp -r {} "$INSTALL_DIR"/ \; )
    rm -rf "$INSTALL_DIR/.jf-tmp"
    ok "Berhasil mengunduh"
}

# ── Jalan ───────────────────────────────────────────────────────────────────
banner
ensure_python
ok "Python ditemukan: $($PY --version 2>&1)"

download_source

step "Menyiapkan lingkungan & memasang dependensi..."
cd "$INSTALL_DIR"
rm -rf .venv
if ! "$PY" -m venv .venv; then
    err "Gagal membuat lingkungan (venv)."
    say "  Debian/Ubuntu: sudo apt install python3-venv"
    exit 1
fi
.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1 || true
if ! .venv/bin/pip install -q .; then
    err "Gagal memasang dependensi. Periksa koneksi internet lalu coba lagi."
    exit 1
fi
ok "Dependensi terpasang"

# ── Daftarkan perintah `jf` ─────────────────────────────────────────────────
step "Mendaftarkan perintah 'jf'..."
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/jf" << WRAPPER
#!/bin/bash
INSTALL_DIR="$INSTALL_DIR"

# Auto-update (hanya bila di-clone via git & tree bersih)
if [ -d "\$INSTALL_DIR/.git" ]; then
    cd "\$INSTALL_DIR" 2>/dev/null || exit 1
    if [ -z "\$(git status --porcelain 2>/dev/null)" ]; then
        CURRENT=\$(git rev-parse HEAD 2>/dev/null)
        git pull --quiet 2>/dev/null
        NEW=\$(git rev-parse HEAD 2>/dev/null)
        if [ -n "\$CURRENT" ] && [ "\$CURRENT" != "\$NEW" ]; then
            echo "🔄 Update ditemukan! Memasang..."
            .venv/bin/pip install -q . || echo "⚠ Gagal update, lanjut versi lama."
        fi
    fi
fi

exec "\$INSTALL_DIR/.venv/bin/python3" -m jurnal_finder "\$@"
WRAPPER
chmod +x "$BIN_DIR/jf"
ok "Perintah 'jf' siap di $BIN_DIR/jf"

# ── Pastikan $BIN_DIR ada di PATH ───────────────────────────────────────────
PATH_ADDED=0
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        RC_FILES=""
        for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
            [ -f "$rc" ] && RC_FILES="$RC_FILES $rc"
        done
        # Bila belum ada file rc sama sekali, buat .profile agar 'jf' tetap dikenali.
        if [ -z "$RC_FILES" ]; then
            touch "$HOME/.profile"
            RC_FILES="$HOME/.profile"
        fi
        for rc in $RC_FILES; do
            grep -q 'HOME/.local/bin' "$rc" 2>/dev/null && continue
            printf '\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$rc"
            PATH_ADDED=1
        done
        # Agar 'jf' langsung bisa dipakai di sesi ini juga:
        export PATH="$BIN_DIR:$PATH"
        ;;
esac

say ""
say "${G}${B}✅ Instalasi selesai!${N}"
say ""
if [ "$PATH_ADDED" = "1" ]; then
    say "${Y}Langkah terakhir: buka terminal baru, atau jalankan ini sekali:${N}"
    say "   ${C}export PATH=\"\$HOME/.local/bin:\$PATH\"${N}"
    say ""
fi
say "${B}Cara pakai:${N}"
say "   ${C}jf${N}                                  # mode dipandu (paling mudah)"
say "   ${C}jf --topik \"pengaruh inflasi\"${N}      # langsung dari terminal"
say ""
say "💡 Mulai dari folder mana saja. Panduan lengkap ada di README."
say ""
