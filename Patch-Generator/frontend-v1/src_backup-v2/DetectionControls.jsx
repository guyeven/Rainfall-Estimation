
export default function DetectionControls({
  params,
  onChange,
  onDetect,
  detecting,
  selectedFilesCount,
}) {
  const handleNumberChange = (field) => (e) => {
    const value = e.target.value;
    const num = value === "" ? "" : Number(value);
    onChange({ ...params, [field]: Number.isNaN(num) ? "" : num });
  };

  const handleNullableNumberChange = (field) => (e) => {
    const value = e.target.value;
    if (value === "") {
      onChange({ ...params, [field]: null });
      return;
    }
    const num = Number(value);
    onChange({ ...params, [field]: Number.isNaN(num) ? null : num });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onDetect();
  };

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: "4px",
        padding: "8px",
        background: "#fff",
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "6px" }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
          }}
        >
          <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Detection</h2>
          <span style={{ fontSize: "0.7rem", color: "#555" }}>
            Selected files: {selectedFilesCount || "auto (max_files)"}
          </span>
        </div>

        <div style={rowStyle}>
          <label style={labelStyle}>
            Threshold (mm)
            <input
              type="number"
              step="0.1"
              value={params.threshold_mm}
              onChange={handleNumberChange("threshold_mm")}
              style={inputStyle}
            />
          </label>

          <label style={labelStyle}>
            Max files (if auto)
            <input
              type="number"
              value={params.max_files}
              onChange={handleNumberChange("max_files")}
              style={inputStyle}
            />
          </label>
        </div>

        <div style={rowStyle}>
          <label style={labelStyle}>
            Avg window Y (px)
            <input
              type="number"
              value={params.avg_window_y}
              onChange={handleNumberChange("avg_window_y")}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            Avg window X (px)
            <input
              type="number"
              value={params.avg_window_x}
              onChange={handleNumberChange("avg_window_x")}
              style={inputStyle}
            />
          </label>
        </div>

        <div style={rowStyle}>
          <label style={labelStyle}>
            Min width (km)
            <input
              type="number"
              value={params.min_width_km}
              onChange={handleNumberChange("min_width_km")}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            Min height (km)
            <input
              type="number"
              value={params.min_height_km}
              onChange={handleNumberChange("min_height_km")}
              style={inputStyle}
            />
          </label>
        </div>

        <div style={rowStyle}>
          <label style={labelStyle}>
            Max width (km)
            <input
              type="number"
              value={params.max_width_km ?? ""}
              onChange={handleNullableNumberChange("max_width_km")}
              style={inputStyle}
              placeholder="none"
            />
          </label>
          <label style={labelStyle}>
            Max height (km)
            <input
              type="number"
              value={params.max_height_km ?? ""}
              onChange={handleNullableNumberChange("max_height_km")}
              style={inputStyle}
              placeholder="none"
            />
          </label>
        </div>

        <button
          type="submit"
          disabled={detecting}
          style={{
            marginTop: "4px",
            padding: "6px 8px",
            fontSize: "0.85rem",
            borderRadius: "4px",
            border: "1px solid #0077cc",
            background: detecting ? "#cde9ff" : "#0094ff",
            color: "#fff",
            cursor: detecting ? "default" : "pointer",
          }}
        >
          {detecting ? "Detecting…" : "Detect patches"}
        </button>
      </form>
    </section>
  );
}

const rowStyle = {
  display: "flex",
  gap: "6px",
};

const labelStyle = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  fontSize: "0.75rem",
};

const inputStyle = {
  marginTop: "2px",
  padding: "3px 4px",
  fontSize: "0.8rem",
};
