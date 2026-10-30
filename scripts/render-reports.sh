#!/usr/bin/env bash
# Render the Assignment 5 reports (Markdown in docs/) to self-contained HTML files in
# output/html/. Re-run after adding screenshots to docs/img/assignment-5/.
# Requires pandoc 3.x; Mermaid diagrams are drawn by mermaid.js, embedded in the file.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$repo/output/html"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$out"

cat >"$tmp/style.css" <<'CSS'
body { font-family: "Times New Roman", Times, serif; font-size: 12pt; line-height: 1.5;
       max-width: 48em; padding: 2em 1em; }
h1 { font-size: 1.5em; line-height: 1.25; }
h2 { font-size: 1.2em; margin-top: 1.5em; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #999; padding: 0.3em 0.6em; vertical-align: top; }
figure { margin: 1.5em 0; }
figure img { max-width: 100%; border: 1px solid #ccc; }
figcaption { font-size: 0.9em; margin-top: 0.3em; }
code { font-size: 0.9em; }
div.mermaid { text-align: center; margin: 1em 0; }
CSS

# pandoc writes ```mermaid blocks as <pre class="mermaid"><code>…; mermaid.js needs the
# bare text in a div. The library is downloaded first so pandoc can embed it; a second
# CDN is the fallback when the first is slow.
for cdn in https://cdn.jsdelivr.net/npm https://unpkg.com; do
    if curl -fsSL --connect-timeout 10 --max-time 60 -o "$tmp/mermaid.min.js" \
        "$cdn/mermaid@11/dist/mermaid.min.js"; then
        break
    fi
    rm -f "$tmp/mermaid.min.js"
done
[[ -s "$tmp/mermaid.min.js" ]] || { echo "could not download mermaid.js" >&2; exit 1; }
printf '<script src="%s"></script>\n' "$tmp/mermaid.min.js" >"$tmp/mermaid.html"
cat >>"$tmp/mermaid.html" <<'HTML'
<script>
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("pre.mermaid").forEach((pre) => {
    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = pre.textContent;
    pre.replaceWith(div);
  });
  mermaid.initialize({ startOnLoad: false, theme: "neutral" });
  mermaid.run();
});
</script>
HTML

for name in assignment-5-devops-theory assignment-5-practical-report; do
    src="$repo/docs/$name.md"
    title="$(sed -n 's/^# //p' "$src" | head -n 1)"
    extra=()
    if grep -q '^```mermaid' "$src"; then
        extra=(--include-after-body "$tmp/mermaid.html")
    fi
    pandoc "$src" \
        --standalone --embed-resources \
        --resource-path="$repo/docs" \
        --css "$tmp/style.css" \
        ${extra[@]+"${extra[@]}"} \
        --metadata pagetitle="$title" \
        --output "$out/$name.html"
    echo "$out/$name.html"
done
