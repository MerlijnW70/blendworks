function decode(text,    out, i, c, digits) {
  out = ""
  for (i = 1; i <= length(text); i++) {
    c = substr(text, i, 1)
    digits = substr(text, i + 1, 3)
    if (c == "\\" && digits ~ /^[0-3][0-7][0-7]$/) {
      out = out sprintf("%c", substr(digits, 1, 1) * 64 + substr(digits, 2, 1) * 8 + substr(digits, 3, 1))
      i += 3
    } else {
      out = out c
    }
  }
  return out
}

function remount_options(options,    parts, count, i, kept) {
  count = split(options, parts, ",")
  kept = "remount,bind,ro"
  for (i = 2; i <= count; i++) kept = kept "," parts[i]
  return kept
}

function read_only(options,    parts) {
  split(options, parts, ",")
  return parts[1] == "ro"
}

BEGIN {
  top = ENVIRON["BLENDWORKS_TOP"]
  mode = ENVIRON["BLENDWORKS_MODE"]
  found = 0
  writable = 0
}

{
  point = decode($5)
  if (point != top && index(point, top "/") != 1) next
  found++
  if (mode == "points") print remount_options($6) "\t" point
  else if (!read_only($6)) {
    writable++
    print "writable: " point
  }
}

END {
  if (mode == "check" && (found == 0 || writable > 0)) {
    if (found == 0) print "not mounted: " top
    exit 1
  }
}
