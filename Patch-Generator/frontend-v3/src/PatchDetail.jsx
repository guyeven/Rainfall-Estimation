import { API_BASE } from "./apiBase";
import { formatTimestamp, formatKm, formatMm } from "./utils/formatters";

export default function PatchDetail({ patch, imageUrl, loading }) {
  const filePath = patch?.source_file || "";
  const filename = filePath ? filePath.split(/[\\/]/).pop() : "";
  const hasStats =
    patch &&
    (patch.max_rainfall !== undefined || patch.mean_rainfall !== undefined);

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: "4px",
        padding: "8px",
        background: "#fff",
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <h2 style={{ margin: 0, fontSize: "0.95rem", marginBottom: "4px" }}>
        Patch detail
      </h2>

      {!patch ? (
        <div style={{ fontSize: "0.8rem", color: "#555" }}>
          Select a patch to see details and image.
        </div>
      ) : (
        <>
          <div
            style={{
              fontSize: "0.78rem",
              marginBottom: "6px",
            }}
          >
            <div>
              <strong>ID:</strong>{" "}
              <span style={{ wordBreak: "break-all" }}>{patch.id}</span>
            </div>
            <div>
              <strong>File:</strong>{" "}
              <span
                style={{ wordBreak: "break-all" }}
                title={filePath || undefined}
              >
                {filename || "-"}
              </span>
            </div>
            <div>
              <strong>Time:</strong>{" "}
              {patch.timestamp ? formatTimestamp(patch.timestamp) : "-"}
            </div>
            <div>
              <strong>Size:</strong>{" "}
              {patch.width_km && patch.height_km
                ? `${formatKm(patch.width_km)} × ${formatKm(patch.height_km)}`
                : "-"}
            </div>
            {typeof patch.center_lat === "number" &&
              typeof patch.center_lon === "number" && (
                <div>
                  <strong>Center:</strong>{" "}
                  {patch.center_lat.toFixed(3)}, {patch.center_lon.toFixed(3)}
                </div>
              )}
            {patch.nearest_city && (
              <div>
                <strong>Nearest city:</strong> {patch.nearest_city}
              </div>
            )}

            <div style={{ marginTop: "4px" }}>
              <strong>Statistics:</strong>{" "}
              {hasStats ? (
                <ul
                  style={{
                    margin: "2px 0 0",
                    paddingLeft: "16px",
                    listStyleType: "disc",
                  }}
                >
                  <li>
                    Max rainfall:{" "}
                    {patch.max_rainfall !== undefined
                      ? formatMm(patch.max_rainfall)
                      : "-"}
                  </li>
                  <li>
                    Average rainfall:{" "}
                    {patch.mean_rainfall !== undefined
                      ? formatMm(patch.mean_rainfall)
                      : "-"}
                  </li>
                </ul>
              ) : (
                "-"
              )}
            </div>
          </div>

          <div
            style={{
              flex: 1,
              minHeight: 0,
              border: "1px solid #eee",
              borderRadius: "4px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "#fafafa",
              overflow: "hidden",
            }}
          >
            {loading ? (
              <span style={{ fontSize: "0.8rem" }}>Loading image…</span>
            ) : imageUrl ? (
              <img
                src={imageUrl}
                alt="Rainfall patch"
                style={{
                  maxWidth: "100%",
                  maxHeight: "100%",
                  objectFit: "contain",
                }}
              />
            ) : (
              <span style={{ fontSize: "0.8rem" }}>No image available.</span>
            )}
          </div>

          {imageUrl && (
            <div
              style={{
                marginTop: "4px",
                display: "flex",
                justifyContent: "flex-end",
              }}
            >
              <a
                href={imageUrl}
                target="_blank"
                rel="noreferrer"
                style={{
                  fontSize: "0.75rem",
                  textDecoration: "none",
                  color: "#0077cc",
                }}
              >
                Open image in new tab
              </a>
            </div>
          )}
        </>
      )}
    </section>
  );
}
