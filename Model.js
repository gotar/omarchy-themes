.pragma library
// Model.js — search + facet-filter logic for the omarchy-themes browser.
//
// Port of the site's app.js semantics (bjarneo.github.io/omarchy-themes):
//   * search: case-insensitive substring over path + title + tags
//   * tone:   single-select facet (dark / light)
//   * color:  single-select facet (9 hue buckets)
//   * res:    resolution tier RANGE (>= / <=, open-ended bounds allowed)
//   * live facet counts: entries are counted under a facet only if they
//     pass every OTHER facet, so selecting a value shows what it would yield
// Entries are the slim records produced by bin/fetch-manifest.py.

const TONES = ["dark", "light"]
const COLOR_ORDER = ["monochrome", "red", "orange", "yellow", "green", "cyan", "blue", "purple", "pink"]
const RES_TIERS = ["<=720p", "720p", "1080p", "1440p", "4K", "5K", "8K+"]
const VARIANT_ORDER = ["palette", "gruvbox", "nord", "material", "aether"]
const VARIANT_LABEL = {
  palette: "Palette",
  gruvbox: "Warm",
  nord: "Cool",
  material: "Material",
  aether: "Aether"
}
const VARIANT_HUE = {
  palette: "#e74c5b",
  gruvbox: "#f5994f",
  nord: "#5ec3d0",
  material: "#7bbf6f",
  aether: "#a87cd9"
}

// Same bucketing as the site, but on max dimension so portrait 2160×3840
// correctly lands in 4K instead of 1080p.
function bucketRes(w, h) {
  if (!w || !h) return null
  var m = Math.max(w, h)
  if (m >= 7000) return "8K+"
  if (m >= 4800) return "5K"
  if (m >= 3500) return "4K"
  if (m >= 2500) return "1440p"
  if (m >= 1900) return "1080p"
  if (m >= 1200) return "720p"
  return "<=720p"
}

// Precompute per-entry fields used by filtering. Returns entries.
function prep(entries) {
  for (var i = 0; i < entries.length; i++) {
    var e = entries[i]
    e.tier = bucketRes(e.w, e.h)
    e.hay = ((e.p || "") + " " + (e.t || "") + " " + ((e.tags && e.tags.join(" ")) || "")).toLowerCase()
  }
  return entries
}

// { filtered: [entryIndex...], facets: { tone:{}, color:{}, resMin:{}, resMax:{} } }
function apply(entries, q, tone, color, resMin, resMax) {
  var filtered = []
  var facets = { tone: {}, color: {}, resMin: {}, resMax: {} }
  var qi = q ? String(q).trim().toLowerCase() : ""
  var mi = resMin ? RES_TIERS.indexOf(resMin) : -1
  var xi = resMax ? RES_TIERS.indexOf(resMax) : -1
  for (var i = 0; i < entries.length; i++) {
    var e = entries[i]
    if (qi && e.hay.indexOf(qi) === -1) continue

    var passTone = !tone || e.tone === tone
    var passColor = !color || e.color === color
    var passRes = true
    if (mi !== -1 || xi !== -1) {
      var ti = RES_TIERS.indexOf(e.tier)
      if (ti < 0) passRes = false
      else {
        if (mi !== -1 && ti < mi) passRes = false
        if (passRes && xi !== -1 && ti > xi) passRes = false
      }
    }

    if (passTone && passColor && passRes) filtered.push(i)

    // Live counts: pass every OTHER facet.
    if (passColor && passRes && e.tone) facets.tone[e.tone] = (facets.tone[e.tone] || 0) + 1
    if (passTone && passRes && e.color) facets.color[e.color] = (facets.color[e.color] || 0) + 1
    if (passTone && passColor) {
      var ti2 = RES_TIERS.indexOf(e.tier)
      if (ti2 >= 0) {
        for (var a = 0; a <= ti2; a++) facets.resMin[RES_TIERS[a]] = (facets.resMin[RES_TIERS[a]] || 0) + 1
        for (var b = ti2; b < RES_TIERS.length; b++) facets.resMax[RES_TIERS[b]] = (facets.resMax[RES_TIERS[b]] || 0) + 1
      }
    }
  }
  return { filtered: filtered, facets: facets }
}

// Variant keys present on an entry, in the site's fixed display order.
function variantKeys(entry) {
  var out = []
  var th = entry && entry.th ? entry.th : {}
  for (var i = 0; i < VARIANT_ORDER.length; i++) {
    if (th[VARIANT_ORDER[i]]) out.push(VARIANT_ORDER[i])
  }
  return out
}

// Full variant records in display order.
function variantsOf(entry) {
  var out = []
  var keys = variantKeys(entry)
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i]
    var t = entry.th[k]
    out.push({
      key: k,
      label: VARIANT_LABEL[k] || k,
      hue: VARIANT_HUE[k] || "#888888",
      n: t.n,
      ct: t.ct,
      bg: t.bg,
      c: t.c
    })
  }
  return out
}

// "a-b-c" -> "A B C" (display helper).
function titleCase(slug) {
  return String(slug || "")
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, function (c) { return c.toUpperCase() })
}

// Reverse `omarchy theme current`: it title-cases and replaces only dashes
// with spaces, while underscores and dots remain literal.
function slugFromThemeCurrent(displayName) {
  return String(displayName || "").trim().toLowerCase().replace(/\s+/g, "-")
}

// Compact live facet counts so the two resolution controls never overlap.
function formatCount(value) {
  var n = Math.max(0, Number(value) || 0)
  if (n < 1000) return String(Math.floor(n))
  var digits = n >= 10000 ? 0 : 1
  return (n / 1000).toFixed(digits).replace(/\.0$/, "") + "k"
}
