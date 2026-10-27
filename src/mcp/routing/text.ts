const STOPWORDS = new Set(
  "a an and are as at be by can do for from give has have i in into is it its me my of on or so some that the their them then there these this to up use want we what when which with without you your all one two out over".split(" "),
);

const KEEP = new Set(["uvs", "lods", "glb", "gltf", "fbx", "obj", "hdri", "pbr", "orm", "exr", "png", "jpeg", "ids"]);

export function stem(word: string): string {
  if (KEEP.has(word)) return word.endsWith("s") && word.length > 3 ? word.slice(0, -1) : word;
  if (word.length <= 3) return word;
  const stripped = stripSuffix(word);
  return stripped.length > 4 && stripped.endsWith("e") ? stripped.slice(0, -1) : stripped;
}

function stripSuffix(word: string): string {
  if (word.endsWith("ies") && word.length > 4) return `${word.slice(0, -3)}y`;
  if (word.endsWith("sses")) return word.slice(0, -2);
  if (word.endsWith("ing") && word.length > 5) return trimDouble(word.slice(0, -3));
  if (word.endsWith("ed") && word.length > 4) return trimDouble(word.slice(0, -2));
  if (word.endsWith("es") && /(ch|sh|x|z)es$/.test(word)) return word.slice(0, -2);
  if (word.endsWith("s") && !word.endsWith("ss") && !word.endsWith("us") && !word.endsWith("is")) return word.slice(0, -1);
  return word;
}

function trimDouble(word: string): string {
  return /([b-df-hj-np-tv-z])\1$/.test(word) && !/(ll|ss)$/.test(word) ? word.slice(0, -1) : word;
}

export function words(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .split(/[^a-z0-9]+/)
    .filter((word) => word !== "" && !STOPWORDS.has(word) && !/^\d+$/.test(word));
}

export function tokens(text: string): string[] {
  return words(text).map(stem);
}
