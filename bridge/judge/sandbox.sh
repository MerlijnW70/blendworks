set -eu
new=$1
shift
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
read_only() {
  awk -v top="$new$1" '$5 == top || index($5, top "/") == 1 { print $5 }' /proc/self/mountinfo | while read -r point; do
    mount -o remount,bind,ro "$point"
  done
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
