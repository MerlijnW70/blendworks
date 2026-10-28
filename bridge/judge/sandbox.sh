set -eu
new=$1
shift
mountinfo_script="$(dirname "$0")/mountinfo.awk"
fail() {
  echo "blendworks-sandbox: $1" >&2
  exit 97
}
mount -t tmpfs -o mode=0755 blendworks-root "$new"
mkdir -p "$new/proc" "$new/tmp" "$new/dev"
mount -t proc proc "$new/proc"
mount -t tmpfs -o mode=1777 blendworks-tmp "$new/tmp"
mount -t tmpfs -o mode=0755 blendworks-dev "$new/dev"
mkdir -p "$new/dev/shm"
mount -t tmpfs -o mode=1777 blendworks-shm "$new/dev/shm"
for device in null zero full random urandom tty; do
  : > "$new/dev/$device"
  mount --bind "/dev/$device" "$new/dev/$device"
done
place() {
  case "$1" in
    *"
"*) fail "a sandbox path holds a line break: refused" ;;
  esac
  if [ ! -e "$1" ] && [ ! -L "$1" ]; then
    return 1
  fi
  if [ -L "$1" ]; then
    mkdir -p "$new$(dirname "$1")"
    ln -s "$(readlink "$1")" "$new$1"
    return 1
  fi
  if [ -d "$1" ]; then
    mkdir -p "$new$1"
  else
    mkdir -p "$new$(dirname "$1")"
    : > "$new$1"
  fi
  mount --rbind "$1" "$new$1"
}
mounts() {
  BLENDWORKS_TOP="$new$1" BLENDWORKS_MODE="$2" awk -f "$mountinfo_script" /proc/self/mountinfo
}
read_only() {
  points=$(mounts "$1" points) || fail "cannot read the mounts under $1"
  tab=$(printf '\t')
  printf '%s\n' "$points" | while IFS= read -r line; do
    if [ -n "$line" ]; then
      mount -o "${line%%"$tab"*}" "${line#*"$tab"}" || true
    fi
  done
  report=$(mounts "$1" check) || fail "$1 is not read-only in the sandbox: $report"
}
while [ "$1" != "--" ]; do
  place "$1" || true
  shift
done
shift
while [ "$1" != "--" ]; do
  if place "$1"; then read_only "$1"; fi
  shift
done
shift
cd "$new"
mkdir .old
pivot_root . .old
umount -l /.old
rmdir /.old
cd /
exec "$@"
