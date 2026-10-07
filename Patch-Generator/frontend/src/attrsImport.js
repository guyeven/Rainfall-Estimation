// Attribute JSONL/NDJSON import with full reporting.
//
// Rules (as requested):
// - Always merge; never erase existing selection or attributes.
// - rain_type: union merge
// - area_type: union merge; report disagreements
// - intensity: keep existing UI value if set; report mismatches
// - notes: concatenate with \n---\n
// - approved: keep existing if already present; otherwise take imported; report mismatches

const AREA_TYPES = new Set(["lake", "sea", "land", "urban", "desert", "mountain", "forest", "agriculture", "other"]);
const RAIN_TYPES = new Set(["convective", "stratiform", "frontal", "orographic", "cyclone", "mixed", "spiral"]);
const INTENSITIES = new Set(["", "light", "moderate", "heavy", "extreme"]);

function norm(v) {
  return String(v ?? "").trim().toLowerCase();
}

function asArray(v) {
  if (Array.isArray(v)) return v;
  if (typeof v === "string" && v.trim()) return [v];
  return [];
}

function uniq(arr) {
  return Array.from(new Set(arr));
}

function mergeNotes(a, b) {
  const left = String(a ?? "").trim();
  const right = String(b ?? "").trim();
  if (!left) return right;
  if (!right) return left;
  if (left === right) return left;
  return `${left}\n---\n${right}`;
}

function safeJson(line, lineNo) {
  try {
    return { ok: true, value: JSON.parse(line) };
  } catch (e) {
    return { ok: false, error: { line: lineNo, kind: "parse", message: e?.message || String(e) } };
  }
}

function addToMapList(map, key, val) {
  const arr = map.get(key) || [];
  arr.push(val);
  map.set(key, arr);
}

export async function importAttributesNdjsonFromFile({ file, existingByPatch, loadedPatchIds }) {
  const text = await file.text();
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  const report = {
    ok: true,
    file: file?.name || "(unknown)",
    lines_total: lines.length,
    parsed_ok: 0,
    patch_ids: 0,
    selected_added: 0,
    matched_loaded: 0,
    missing_loaded: 0,
    parse_errors: [],
    schema_errors: [],
    type_warnings: [],
    duplicates: {},
    area_disagreements: [],
    intensity_mismatches: [],
    approved_mismatches: [],
    unknown_values: { area_type: [], rain_type: [], intensity: [] },
  };

  // Detect duplicates within file (all line numbers)
  const seen = new Map();
  for (let i = 0; i < lines.length; i++) {
    const j = safeJson(lines[i], i + 1);
    if (!j.ok) continue;
    const pid = String(j.value?.patch_id ?? "").trim();
    if (!pid) continue;
    addToMapList(seen, pid, i + 1);
  }
  for (const [pid, arr] of seen.entries()) if (arr.length > 1) report.duplicates[pid] = arr;

  const importedPatchIds = new Set();
  const mergedByPatch = {};

  for (let i = 0; i < lines.length; i++) {
    const lineNo = i + 1;
    const j = safeJson(lines[i], lineNo);
    if (!j.ok) {
      report.parse_errors.push(j.error);
      continue;
    }

    const obj = j.value;
    const patchId = String(obj?.patch_id ?? "").trim();
    if (!patchId) {
      report.schema_errors.push({ line: lineNo, kind: "schema", message: "Missing patch_id" });
      continue;
    }
    const attrs = obj?.attributes;
    if (!attrs || typeof attrs !== "object") {
      report.schema_errors.push({
        line: lineNo,
        kind: "schema",
        message: `patch_id=${patchId}: Missing attributes object`,
      });
      continue;
    }

    report.parsed_ok += 1;
    importedPatchIds.add(patchId);

    const prev = mergedByPatch[patchId] || existingByPatch?.[patchId];
    const base = prev
      ? { ...prev }
      : {
          area_type: [],
          rain_type: [],
          intensity: "",
          notes: "",
          approved: false,
        };

    // area_type
    const areaRaw = attrs.area_type;
    const areaArr = asArray(areaRaw).map(norm).filter(Boolean);
    if (!Array.isArray(areaRaw) && areaArr.length) {
      report.type_warnings.push({ line: lineNo, field: "area_type", message: "coerced to array" });
    }

    // rain_type
    const rainRaw = attrs.rain_type;
    const rainArr = asArray(rainRaw).map(norm).filter(Boolean);
    if (!Array.isArray(rainRaw) && rainArr.length) {
      report.type_warnings.push({ line: lineNo, field: "rain_type", message: "coerced to array" });
    }

    // intensity
    const intensityRaw = attrs.intensity;
    const intensity = norm(intensityRaw);
    if (intensityRaw != null && typeof intensityRaw !== "string") {
      report.type_warnings.push({ line: lineNo, field: "intensity", message: "coerced to string" });
    }

    // notes
    const notesRaw = attrs.notes;
    const notes = String(notesRaw ?? "");
    if (notesRaw != null && typeof notesRaw !== "string") {
      report.type_warnings.push({ line: lineNo, field: "notes", message: "coerced to string" });
    }

    // approved
    const approvedRaw = obj?.approved;
    const approvedImported = Boolean(approvedRaw);
    if (approvedRaw != null && typeof approvedRaw !== "boolean") {
      report.type_warnings.push({ line: lineNo, field: "approved", message: "coerced to boolean" });
    }

    // Unknown values reporting (kept; may not render as checked)
    for (const v of areaArr) if (!AREA_TYPES.has(v)) report.unknown_values.area_type.push({ line: lineNo, value: v });
    for (const v of rainArr) if (!RAIN_TYPES.has(v)) report.unknown_values.rain_type.push({ line: lineNo, value: v });
    if (intensity && !INTENSITIES.has(intensity)) report.unknown_values.intensity.push({ line: lineNo, value: intensity });

    // Merge area/rain
    const beforeArea = new Set((base.area_type || []).map(norm).filter(Boolean));
    const beforeRain = new Set((base.rain_type || []).map(norm).filter(Boolean));
    const mergedArea = uniq([...beforeArea, ...areaArr]);
    const mergedRain = uniq([...beforeRain, ...rainArr]);
    if (beforeArea.size && areaArr.some((v) => !beforeArea.has(v))) {
      report.area_disagreements.push({
        line: lineNo,
        patch_id: patchId,
        existing: Array.from(beforeArea),
        imported: areaArr,
        merged: mergedArea,
      });
    }

    // intensity mismatch rule: keep existing if set
    let mergedIntensity = base.intensity || "";
    if (intensity) {
      if (mergedIntensity && norm(mergedIntensity) !== intensity) {
        report.intensity_mismatches.push({
          line: lineNo,
          patch_id: patchId,
          existing: mergedIntensity,
          imported: intensity,
        });
      } else if (!mergedIntensity) {
        mergedIntensity = intensity;
      }
    }

    // approved mismatch rule: keep existing if already present (i.e., was edited or previously imported)
    let mergedApproved = Boolean(base.approved);
    if (prev) {
      if (Boolean(base.approved) !== approvedImported) {
        report.approved_mismatches.push({
          line: lineNo,
          patch_id: patchId,
          existing: Boolean(base.approved),
          imported: approvedImported,
        });
      }
    } else {
      mergedApproved = approvedImported;
    }

    mergedByPatch[patchId] = {
      ...base,
      area_type: mergedArea,
      rain_type: mergedRain,
      intensity: mergedIntensity,
      notes: mergeNotes(base.notes, notes),
      approved: mergedApproved,
    };
  }

  // Join diagnostics (no deferred handling)
  let matched = 0;
  let missing = 0;
  for (const pid of importedPatchIds) {
    if (loadedPatchIds?.has?.(pid)) matched += 1;
    else missing += 1;
  }
  report.patch_ids = importedPatchIds.size;
  report.matched_loaded = matched;
  report.missing_loaded = missing;

  report.ok = report.parse_errors.length === 0 && report.schema_errors.length === 0;
  report.summary = [
    `file=${report.file}`,
    `lines_total=${report.lines_total}`,
    `parsed_ok=${report.parsed_ok}`,
    `patch_ids=${report.patch_ids}`,
    `matched_loaded=${report.matched_loaded}`,
    `missing_loaded=${report.missing_loaded}`,
    `parse_errors=${report.parse_errors.length}`,
    `schema_errors=${report.schema_errors.length}`,
    `type_warnings=${report.type_warnings.length}`,
    `duplicates=${Object.keys(report.duplicates).length}`,
    `area_disagreements=${report.area_disagreements.length}`,
    `intensity_mismatches=${report.intensity_mismatches.length}`,
    `approved_mismatches=${report.approved_mismatches.length}`,
    `unknown_area=${report.unknown_values.area_type.length}`,
    `unknown_rain=${report.unknown_values.rain_type.length}`,
    `unknown_intensity=${report.unknown_values.intensity.length}`,
  ].join(" | ");

  // Full details (no hiding): keep reasonably sized; UI block scrolls.
  const details = [];
  const pushMany = (title, arr, fmt) => {
    if (!arr.length) return;
    details.push(`${title} (${arr.length}):`);
    for (const x of arr) details.push(`- ${fmt(x)}`);
    details.push("");
  };
  pushMany("PARSE ERRORS", report.parse_errors, (e) => `line ${e.line}: ${e.message}`);
  pushMany("SCHEMA ERRORS", report.schema_errors, (e) => `line ${e.line}: ${e.message}`);
  pushMany("TYPE WARNINGS", report.type_warnings, (e) => `line ${e.line}: ${e.field}: ${e.message}`);
  if (Object.keys(report.duplicates).length) {
    details.push(`DUPLICATE patch_id LINES (merged; no winners):`);
    for (const [pid, arr] of Object.entries(report.duplicates)) details.push(`- ${pid}: lines ${arr.join(", ")}`);
    details.push("");
  }
  pushMany(
    "AREA DISAGREEMENTS (union merged)",
    report.area_disagreements,
    (x) => `patch_id=${x.patch_id} line ${x.line}: existing=${JSON.stringify(x.existing)} imported=${JSON.stringify(x.imported)} merged=${JSON.stringify(x.merged)}`
  );
  pushMany(
    "INTENSITY MISMATCHES (kept UI value)",
    report.intensity_mismatches,
    (x) => `patch_id=${x.patch_id} line ${x.line}: existing='${x.existing}' imported='${x.imported}'`
  );
  pushMany(
    "APPROVED MISMATCHES (kept UI value)",
    report.approved_mismatches,
    (x) => `patch_id=${x.patch_id} line ${x.line}: existing=${x.existing} imported=${x.imported}`
  );
  pushMany(
    "UNKNOWN area_type VALUES (stored; may not render)",
    report.unknown_values.area_type,
    (x) => `line ${x.line}: '${x.value}'`
  );
  pushMany(
    "UNKNOWN rain_type VALUES (stored; may not render)",
    report.unknown_values.rain_type,
    (x) => `line ${x.line}: '${x.value}'`
  );
  pushMany(
    "UNKNOWN intensity VALUES (stored; may not render)",
    report.unknown_values.intensity,
    (x) => `line ${x.line}: '${x.value}'`
  );

  report.details = details.join("\n").trim();

  return { mergedByPatch, importedPatchIds, report };
}
