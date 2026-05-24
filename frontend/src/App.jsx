import { useEffect, useRef, useState } from "react";
import { getFurniture, createFurniture, deleteFurniture, updateFurniture, uploadImage, deleteImage, imageUrl } from "./api";

function normalizeUrl(str) {
  const s = /^https?:\/\//i.test(str) ? str : `https://${str}`;
  try { return new URL(s); } catch { return null; }
}

const field = {
  border: "1px solid var(--border)",
  borderRadius: 10,
  padding: "10px 14px",
  fontSize: 15,
  background: "var(--bg)",
  color: "var(--text-h)",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const overlayBtn = {
  background: "rgba(0,0,0,0.45)",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  lineHeight: 1,
};

export default function App() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ name: "", category: "", location: "", price: "" });
  const [uploading, setUploading] = useState(null);
  const [formImage, setFormImage] = useState(null);
  const [formTags, setFormTags] = useState([]);
  const [tagInput, setTagInput] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [editTagInput, setEditTagInput] = useState("");
  const [sliderIndices, setSliderIndices] = useState({});
  const [activeTags, setActiveTags] = useState([]);
  const [search, setSearch] = useState("");

  const fileInputRef = useRef(null);
  const formFileRef = useRef(null);
  const uploadTargetId = useRef(null);

  useEffect(() => { load(); }, []);

  async function load() {
    const data = await getFurniture();
    setItems(data);
  }

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = await createFurniture({ ...form, price: Number(form.price), tags: formTags });
    if (formImage && result.id) {
      await uploadImage(result.id, formImage);
    }
    setForm({ name: "", category: "", location: "", price: "" });
    setFormImage(null);
    setFormTags([]);
    setTagInput("");
    formFileRef.current.value = "";
    load();
  }

  function addTag(raw, currentTags, setTags, setInput) {
    const tag = raw.trim().replace(/,+$/, "").trim();
    if (tag && !currentTags.includes(tag)) setTags([...currentTags, tag]);
    setInput("");
  }

  function handleTagKeyDown(e, currentTags, setTags, setInput) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag(e.target.value, currentTags, setTags, setInput);
    } else if (e.key === "Backspace" && e.target.value === "" && currentTags.length) {
      setTags(currentTags.slice(0, -1));
    }
  }

  async function handleDelete(id) {
    await deleteFurniture(id);
    load();
  }

  function startEdit(item) {
    setEditingId(item.id);
    setEditForm({ name: item.name, category: item.category, location: item.location, price: item.price, tags: item.tags || [] });
    setEditTagInput("");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm({});
    setEditTagInput("");
  }

  async function saveEdit(id) {
    await updateFurniture(id, { ...editForm, price: Number(editForm.price) });
    setEditingId(null);
    setEditForm({});
    setEditTagInput("");
    load();
  }

  function handleUploadClick(id) {
    uploadTargetId.current = id;
    fileInputRef.current.click();
  }

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    const id = uploadTargetId.current;
    setUploading(id);
    await uploadImage(id, file);
    e.target.value = "";
    setUploading(null);
    load();
  }

  async function handleDeleteImage(furnitureId, imgId, currentIdx, totalImages) {
    await deleteImage(furnitureId, imgId);
    if (currentIdx >= totalImages - 1) {
      setSliderIndices(prev => ({ ...prev, [furnitureId]: Math.max(0, currentIdx - 1) }));
    }
    load();
  }

  function toggleFilter(tag) {
    setActiveTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    );
  }

  const filteredItems = items.filter(item => {
    if (activeTags.length && !activeTags.every(t => (item.tags || []).includes(t))) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      const matches =
        item.name?.toLowerCase().includes(q) ||
        item.category?.toLowerCase().includes(q) ||
        item.location?.toLowerCase().includes(q) ||
        (item.tags || []).some(t => t.toLowerCase().includes(q));
      if (!matches) return false;
    }
    return true;
  });

  const allTags = [...new Set(items.flatMap(item => item.tags || []))].sort();

  function sliderIdx(itemId, length) {
    return Math.min(sliderIndices[itemId] ?? 0, Math.max(0, length - 1));
  }

  function navigate(itemId, delta, length) {
    const current = sliderIdx(itemId, length);
    setSliderIndices(prev => ({ ...prev, [itemId]: (current + delta + length) % length }));
  }

  return (
    <div style={{ minHeight: "100svh", background: "var(--bg)" }}>
      <input ref={fileInputRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handleFileChange} />

      {/* HEADER */}
      <header style={{ padding: "48px 32px 24px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
        <div style={{ textAlign: "left" }}>
          <h1 style={{ margin: 0 }}>Julias Interior Store</h1>
          <p style={{ marginTop: 6, color: "var(--text)", fontSize: 15 }}>
            {items.length} {items.length === 1 ? "item" : "items"} gespeichert
          </p>
        </div>
        <div style={{ position: "relative", flexShrink: 0 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text)", opacity: 0.5, pointerEvents: "none" }}>
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
          <input
            type="text"
            placeholder="Suchen…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ ...field, width: 220, paddingLeft: 36, fontSize: 14 }}
          />
        </div>
      </header>

      <main style={{ padding: "32px", maxWidth: 1060, margin: "0 auto", width: "100%", boxSizing: "border-box", textAlign: "left" }}>

        {/* FORM */}
        <div style={{ background: "var(--accent-bg)", border: "1px solid var(--accent-border)", borderRadius: 16, padding: 24, marginBottom: 40 }}>
          <h2 style={{ marginBottom: 16 }}>Interior Item hinzufügen</h2>
          <form onSubmit={handleSubmit} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
            <input name="name"     placeholder="Name"       value={form.name}     onChange={handleChange} style={field} />
            <input name="category" placeholder="Kategorie"   value={form.category} onChange={handleChange} style={field} />
            <input name="location" placeholder="Location"   value={form.location} onChange={handleChange} style={field} />
            <input name="price"    placeholder="Preis (€)"  value={form.price}    onChange={handleChange} style={field} type="number" min="0" />

            <input ref={formFileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={e => setFormImage(e.target.files[0] || null)} />
            <button
              type="button"
              onClick={() => formFileRef.current.click()}
              style={{
                ...field,
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer",
                color: formImage ? "var(--accent)" : "var(--text)",
                borderColor: formImage ? "var(--accent-border)" : "var(--border)",
                background: formImage ? "var(--accent-bg)" : "var(--bg)",
                overflow: "hidden",
                whiteSpace: "nowrap",
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="m21 15-5-5L5 21" />
              </svg>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                {formImage ? formImage.name : "Bild hinzufügen"}
              </span>
            </button>

            {/* TAG INPUT */}
            <div style={{ gridColumn: "1 / -1", border: "1px solid var(--border)", borderRadius: 10, padding: "6px 10px", background: "var(--bg)", display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", minHeight: 42 }}>
              {formTags.map(tag => (
                <span key={tag} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: 600, background: "var(--code-bg)", color: "var(--text-h)", borderRadius: 20, padding: "2px 8px" }}>
                  {tag}
                  <button type="button" onClick={() => setFormTags(formTags.filter(t => t !== tag))} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text)", fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                </span>
              ))}
              <input
                type="text"
                placeholder={formTags.length === 0 ? "Tags hinzufügen (Durch Komma trennen)" : "Weiteren Tag hinzufügen…"}
                value={tagInput}
                onChange={e => setTagInput(e.target.value)}
                onKeyDown={e => handleTagKeyDown(e, formTags, setFormTags, setTagInput)}
                onBlur={e => e.target.value.trim() && addTag(e.target.value, formTags, setFormTags, setTagInput)}
                style={{ border: "none", outline: "none", background: "transparent", fontSize: 14, color: "var(--text-h)", flex: 1, minWidth: 160 }}
              />
            </div>

            <button
              type="submit"
              style={{
                gridColumn: "1 / -1",
                background: "var(--accent)",
                color: "#fff",
                border: "none",
                borderRadius: 10,
                padding: "11px",
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Item hinzufügen
            </button>
          </form>
        </div>

        {/* TAG FILTER BAR */}
        {allTags.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 24 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px", flexShrink: 0 }}>Filter</span>
            {allTags.map(tag => {
              const active = activeTags.includes(tag);
              return (
                <button
                  key={tag}
                  onClick={() => toggleFilter(tag)}
                  style={{
                    fontSize: 12, fontWeight: 600, borderRadius: 20, padding: "3px 12px", cursor: "pointer",
                    border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
                    background: active ? "var(--accent)" : "var(--bg)",
                    color: active ? "#fff" : "var(--text)",
                    transition: "all 0.15s",
                  }}
                >
                  {tag}
                </button>
              );
            })}
            {activeTags.length > 0 && (
              <button
                onClick={() => setActiveTags([])}
                style={{ fontSize: 12, color: "var(--text)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", opacity: 0.6 }}
              >
                Zurücksetzen
              </button>
            )}
          </div>
        )}

        {/* EMPTY STATE */}
        {items.length === 0 && (
          <div style={{ textAlign: "center", padding: "80px 0", color: "var(--text)" }}>
            <div style={{ fontSize: 52, marginBottom: 16 }}>🪑</div>
            <p style={{ fontSize: 16 }}>Noch keine Items hinzugefügt. Füge oben dein erstes Interior Item hinzu.</p>
          </div>
        )}

        {items.length > 0 && filteredItems.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text)" }}>
            <p style={{ fontSize: 16 }}>Keine Items für die gewählten Tags gefunden.</p>
            <button onClick={() => setActiveTags([])} style={{ marginTop: 12, fontSize: 13, color: "var(--accent)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
              Filter zurücksetzen
            </button>
          </div>
        )}

        {/* GRID */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 24 }}>
          {filteredItems.map((item) => {
            const images = item.images || [];
            const idx = sliderIdx(item.id, images.length);

            return (
              <div
                key={item.id}
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: 16,
                  overflow: "hidden",
                  boxShadow: "var(--shadow)",
                }}
              >
                {/* IMAGE SLIDER */}
                <div style={{ position: "relative", height: 156, background: "var(--code-bg)", overflow: "hidden" }}>
                  {images.length > 0 ? (
                    <>
                      <img
                        src={imageUrl(images[idx].filename)}
                        alt={item.name}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      />

                      {/* Prev / Next */}
                      {images.length > 1 && (
                        <>
                          <button
                            onClick={() => navigate(item.id, -1, images.length)}
                            style={{ ...overlayBtn, position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", width: 28, height: 28, fontSize: 16 }}
                          >‹</button>
                          <button
                            onClick={() => navigate(item.id, 1, images.length)}
                            style={{ ...overlayBtn, position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", width: 28, height: 28, fontSize: 16 }}
                          >›</button>
                        </>
                      )}

                      {/* Delete current image */}
                      <button
                        onClick={() => handleDeleteImage(item.id, images[idx].id, idx, images.length)}
                        style={{ ...overlayBtn, position: "absolute", top: 8, right: 8, width: 24, height: 24, fontSize: 14 }}
                      >×</button>

                      {/* Add image */}
                      <button
                        onClick={() => handleUploadClick(item.id)}
                        style={{ ...overlayBtn, position: "absolute", top: 8, left: 8, width: 24, height: 24, fontSize: 16 }}
                        title="Bild hinzufügen"
                      >+</button>

                      {/* Dots */}
                      {images.length > 1 && (
                        <div style={{ position: "absolute", bottom: 8, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 5 }}>
                          {images.map((_, i) => (
                            <div
                              key={i}
                              onClick={() => setSliderIndices(prev => ({ ...prev, [item.id]: i }))}
                              style={{ width: 6, height: 6, borderRadius: "50%", background: i === idx ? "#fff" : "rgba(255,255,255,0.45)", cursor: "pointer", transition: "background 0.15s" }}
                            />
                          ))}
                        </div>
                      )}
                    </>
                  ) : uploading === item.id ? (
                    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text)", fontSize: 13 }}>
                      Wird hochgeladen…
                    </div>
                  ) : (
                    <div
                      onClick={() => handleUploadClick(item.id)}
                      style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", cursor: "pointer" }}
                    >
                      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" style={{ color: "var(--text)", opacity: 0.35, marginBottom: 8 }}>
                        <path d="M20 8H4a2 2 0 0 0-2 2v6h2v2h2v-2h8v2h2v-2h2V10a2 2 0 0 0-2-2Z" />
                        <path d="M18 8V6a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v2" />
                      </svg>
                      <span style={{ fontSize: 12, color: "var(--text)", opacity: 0.6 }}>Klicken zum Hochladen</span>
                    </div>
                  )}
                </div>

                {/* CONTENT */}
                <div style={{ padding: 16 }}>
                  {editingId === item.id ? (
                    <>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
                        {[
                          { key: "name", label: "Name" },
                          { key: "category", label: "Kategorie" },
                          { key: "location", label: "Ort" },
                          { key: "price", label: "Preis (€)", type: "number" },
                        ].map(({ key, label, type = "text" }) => (
                          <label key={key} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px" }}>{label}</span>
                            <input
                              type={type}
                              value={editForm[key]}
                              onChange={e => setEditForm({ ...editForm, [key]: e.target.value })}
                              style={{ ...field, padding: "8px 12px", fontSize: 14 }}
                            />
                          </label>
                        ))}
                      </div>
                      <label style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px" }}>Tags</span>
                        <div style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "6px 10px", background: "var(--bg)", display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", minHeight: 38 }}>
                          {(editForm.tags || []).map(tag => (
                            <span key={tag} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: 600, background: "var(--code-bg)", color: "var(--text-h)", borderRadius: 20, padding: "2px 8px" }}>
                              {tag}
                              <button type="button" onClick={() => setEditForm({ ...editForm, tags: editForm.tags.filter(t => t !== tag) })} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text)", fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                            </span>
                          ))}
                          <input
                            type="text"
                            placeholder="Tag hinzufügen…"
                            value={editTagInput}
                            onChange={e => setEditTagInput(e.target.value)}
                            onKeyDown={e => handleTagKeyDown(e, editForm.tags || [], tags => setEditForm({ ...editForm, tags }), setEditTagInput)}
                            onBlur={e => e.target.value.trim() && addTag(e.target.value, editForm.tags || [], tags => setEditForm({ ...editForm, tags }), setEditTagInput)}
                            style={{ border: "none", outline: "none", background: "transparent", fontSize: 13, color: "var(--text-h)", flex: 1, minWidth: 100 }}
                          />
                        </div>
                      </label>

                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          onClick={() => saveEdit(item.id)}
                          style={{ flex: 1, background: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "7px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
                        >
                          Speichern
                        </button>
                        <button
                          onClick={cancelEdit}
                          style={{ flex: 1, background: "transparent", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px", fontSize: 13, cursor: "pointer" }}
                        >
                          Abbrechen
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      {/* TAGS + LOCATION */}
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                        {(item.tags || []).map(tag => {
                          const active = activeTags.includes(tag);
                          return (
                            <button
                              key={tag}
                              onClick={() => toggleFilter(tag)}
                              style={{
                                fontSize: 12, fontWeight: 600, borderRadius: 20, padding: "2px 10px", cursor: "pointer",
                                border: active ? "1px solid var(--accent)" : "none",
                                background: active ? "var(--accent)" : "var(--code-bg)",
                                color: active ? "#fff" : "var(--text-h)",
                                transition: "all 0.15s",
                              }}
                            >
                              {tag}
                            </button>
                          );
                        })}
                        {item.location && (() => {
                          const parsed = normalizeUrl(item.location);
                          return parsed ? (
                            <a href={parsed.href} target="_blank" rel="noreferrer" style={{ fontSize: 12, background: "var(--code-bg)", color: "var(--accent)", borderRadius: 20, padding: "2px 10px", textDecoration: "none" }}>
                              🔗 {parsed.hostname}
                            </a>
                          ) : (
                            <span style={{ fontSize: 12, background: "var(--code-bg)", color: "var(--text)", borderRadius: 20, padding: "2px 10px" }}>
                              📍 {item.location}
                            </span>
                          );
                        })()}
                      </div>

                      <h3 style={{ margin: "0 0 4px", fontSize: 18, color: "var(--text-h)", fontWeight: 600 }}>
                        {item.name}
                      </h3>
                      {item.category && (
                        <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--text)" }}>{item.category}</p>
                      )}
                      {!item.category && <div style={{ marginBottom: 14 }} />}

                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 20, fontWeight: 700, color: "var(--text-h)" }}>€{item.price}</span>
                        <div style={{ display: "flex", gap: 6 }}>
                          <button
                            onClick={() => startEdit(item)}
                            style={{ fontSize: 13, background: "transparent", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 12px", cursor: "pointer" }}
                          >
                            Bearbeiten
                          </button>
                          <button
                            onClick={() => handleDelete(item.id)}
                            style={{ fontSize: 13, background: "transparent", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 12px", cursor: "pointer" }}
                          >
                            Löschen
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>

      </main>
    </div>
  );
}
