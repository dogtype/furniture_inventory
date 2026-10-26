import { useEffect, useRef, useState } from "react";
import { getFurniture, createFurniture, deleteFurniture, updateFurniture, uploadImage, deleteImage, setImageColor, imageUrl, login, scrapeUrl, uploadImageFromUrl } from "./api";
import { CATEGORIES } from "./categories";

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

function LoginPage({ onLogin }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(password);
      onLogin();
    } catch {
      setError("Falsches Passwort.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100svh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: "100%", maxWidth: 400, padding: "0 32px" }}>
        <div style={{ background: "var(--accent-bg)", border: "1px solid var(--accent-border)", borderRadius: 20, padding: "48px 40px" }}>
          <h1 style={{ textAlign: "center", margin: "0 0 16px", lineHeight: 1.2 }}>Julias<br />Interior Store</h1>
          <p style={{ textAlign: "center", color: "var(--text)", fontSize: 15, margin: "0 0 40px" }}>Bitte Passwort eingeben</p>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <input
              type="password"
              placeholder="Passwort"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoFocus
              style={{ ...field, fontSize: 15, padding: "12px 16px" }}
            />
            {error && <p style={{ color: "#ef4444", fontSize: 13, margin: 0, textAlign: "center" }}>{error}</p>}
            <button
              type="submit"
              disabled={loading}
              style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 10, padding: "13px", fontSize: 15, fontWeight: 600, cursor: loading ? "default" : "pointer", opacity: loading ? 0.7 : 1, marginTop: 4 }}
            >
              {loading ? "…" : "Anmelden"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

const emptyFilters = {
  category: "", subcategory: "", families: [], priceMin: null, priceMax: null,
  size: { length: ["", ""], width: ["", ""], height: ["", ""] },
};

const COLOR_FAMILIES = {
  Schwarz: "#111111", Weiß: "#ffffff", Grau: "#888888", Rot: "#dc2626", Orange: "#f97316", Braun: "#92400e",
  Gelb: "#eab308", Grün: "#16a34a", Türkis: "#14b8a6", Blau: "#2563eb", Lila: "#9333ea", Rosa: "#ec4899",
};

// Maps any hex color to the nearest named color family, so that similar shades are filtered together.
function colorFamily(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (l < 0.12) return "Schwarz";
  if (l > 0.92) return "Weiß";
  if (s < 0.12) return "Grau";
  let h;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  h = (h * 60 + 360) % 360;
  if (h < 15 || h >= 345) return "Rot";
  if (h < 45) return l < 0.4 ? "Braun" : "Orange";
  if (h < 70) return "Gelb";
  if (h < 165) return "Grün";
  if (h < 200) return "Türkis";
  if (h < 255) return "Blau";
  if (h < 290) return "Lila";
  return "Rosa";
}

// Range slider with two thumbs (two overlapping range inputs, styled in index.css)
function DualRange({ min, max, step = 1, low, high, onChange }) {
  const ratio = v => (max === min ? 0 : (v - min) / (max - min));
  // the thumb center does not reach the track ends, by half a thumb (10px)
  const pos = v => `calc(${ratio(v) * 100}% + ${(0.5 - ratio(v)) * 20}px)`;
  const nearRightEnd = ratio(low) > 0.5 && ratio(high) - ratio(low) < 0.1;
  return (
    <div className="dual-range">
      <div className="dual-range-track" />
      <div className="dual-range-fill" style={{ left: pos(low), right: `calc(100% - ${pos(high)})` }} />
      <input
        type="range" min={min} max={max} step={step} value={low}
        onChange={e => onChange(Math.min(Number(e.target.value), high), high)}
        style={{ zIndex: nearRightEnd ? 4 : 2 }}
        aria-label="Mindestpreis"
      />
      <input
        type="range" min={min} max={max} step={step} value={high}
        onChange={e => onChange(low, Math.max(Number(e.target.value), low))}
        style={{ zIndex: 3 }}
        aria-label="Höchstpreis"
      />
    </div>
  );
}

function FilterSection({ title, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px" }}>{title}</span>
      {children}
    </div>
  );
}

// Category and sub-category selects. Values that are not in the list (e.g. older free-text entries) stay selectable.
function CategorySelects({ category, subcategory, onChange, style, labeled }) {
  const categories = Object.keys(CATEGORIES);
  if (category && !categories.includes(category)) categories.push(category);
  const subs = [...(CATEGORIES[category] || [])];
  if (subcategory && !subs.includes(subcategory)) subs.push(subcategory);

  const wrap = (label, el) => labeled ? (
    <label style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px" }}>{label}</span>
      {el}
    </label>
  ) : el;

  return (
    <>
      {wrap("Kategorie",
        <select value={category} onChange={e => onChange(e.target.value, "")} style={style}>
          <option value="">Kategorie</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      )}
      {wrap("Unterkategorie",
        <select value={subcategory} onChange={e => onChange(category, e.target.value)} disabled={!category} style={style}>
          <option value="">Unterkategorie</option>
          {subs.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      )}
    </>
  );
}

const emptyForm = { name: "", category: "", subcategory: "", location: "", price: "", used: false, length: "", width: "", height: "" };

const sizeFields = [
  { key: "length", label: "Länge (cm)" },
  { key: "width", label: "Breite (cm)" },
  { key: "height", label: "Höhe (cm)" },
];

const toSize = v => (v === "" || v == null ? null : Number(v));

function formatSize(item) {
  const parts = [item.length, item.width, item.height];
  if (parts.every(p => p == null)) return "";
  return parts.map(p => p ?? "?").join(" × ") + " cm";
}

const RAINBOW = "conic-gradient(red, yellow, lime, aqua, blue, magenta, red)";

// Color list with a picker. Until a color is picked, the picker shows a rainbow circle instead of a plain swatch.
function ColorPalette({ colors, onChange }) {
  const [picked, setPicked] = useState(null);
  const add = () => {
    if (picked && !colors.includes(picked)) onChange([...colors, picked]);
    setPicked(null);
  };
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      {colors.map(c => (
        <button
          key={c}
          type="button"
          title={`${c} entfernen`}
          onClick={() => onChange(colors.filter(x => x !== c))}
          style={{ width: 30, height: 30, borderRadius: "50%", background: c, border: "2px solid var(--border)", cursor: "pointer", padding: 0 }}
        />
      ))}
      <div
        title="Farbe auswählen"
        style={{ position: "relative", width: 34, height: 34, borderRadius: "50%", background: picked ?? RAINBOW, border: "2px solid var(--border)", flexShrink: 0 }}
      >
        <input
          type="color"
          aria-label="Farbe auswählen"
          value={picked ?? "#3b82f6"}
          onChange={e => setPicked(e.target.value)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0, cursor: "pointer", padding: 0, border: "none" }}
        />
      </div>
      <button
        type="button"
        onClick={add}
        disabled={!picked}
        style={{ fontSize: 13, background: "transparent", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 12px", cursor: picked ? "pointer" : "default", opacity: picked ? 1 : 0.5 }}
      >
        + Farbe
      </button>
    </div>
  );
}

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setMatches(m.matches);
    onChange();
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export default function App() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem("auth_token"));
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [uploading, setUploading] = useState(null);
  const [formImage, setFormImage] = useState(null);
  const [formTags, setFormTags] = useState([]);
  const [formColors, setFormColors] = useState([]);
  const [tagInput, setTagInput] = useState("");
  const [importUrl, setImportUrl] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [filters, setFilters] = useState(emptyFilters);
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [editTagInput, setEditTagInput] = useState("");
  const [sliderIndices, setSliderIndices] = useState({});
  const [colorFilters, setColorFilters] = useState({});
  // Image whose color was just changed. It stays in the slider even if it no longer matches the color filter.
  const [pinnedImages, setPinnedImages] = useState({});
  const [activeTags, setActiveTags] = useState([]);
  const [search, setSearch] = useState("");
  const narrow = useMediaQuery("(max-width: 900px)");
  const touch = useMediaQuery("(pointer: coarse)");
  const [filterOpen, setFilterOpen] = useState(false);
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem("theme") || "system"; } catch { return "system"; }
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef(null);
  const asideRef = useRef(null);
  const [asideTall, setAsideTall] = useState(false);

  const fileInputRef = useRef(null);
  const formFileRef = useRef(null);
  const uploadTargetId = useRef(null);

  useEffect(() => {
    if (authed) load();
    const logout = () => setAuthed(false);
    window.addEventListener("auth:logout", logout);
    return () => window.removeEventListener("auth:logout", logout);
  }, [authed]);

  // "light" and "dark" set data-theme on <html>, "system" removes it so the device setting applies
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
    else root.removeAttribute("data-theme");
    try { localStorage.setItem("theme", theme); } catch { /* storage not available */ }
  }, [theme]);

  useEffect(() => {
    const el = asideRef.current;
    if (!el) return;
    const measure = () => setAsideTall(el.offsetHeight > window.innerHeight - 32);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [narrow, filterOpen, authed]);

  useEffect(() => {
    if (!settingsOpen) return;
    const close = e => {
      if (e.type === "keydown" ? e.key === "Escape" : !settingsRef.current?.contains(e.target)) setSettingsOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [settingsOpen]);

  useEffect(() => {
    function onGlobalPaste(e) {
      const active = document.activeElement;
      if (active && ["INPUT", "TEXTAREA"].includes(active.tagName) && active.type !== "button") return;
      const file = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/"))?.getAsFile();
      if (!file) return;
      const cardEl = active?.closest?.("[data-card-id]");
      if (cardEl) {
        const id = parseInt(cardEl.dataset.cardId);
        setUploading(id);
        uploadImage(id, file).then(() => { setUploading(null); load(); });
      } else {
        setFormImage(file);
      }
    }
    document.addEventListener("paste", onGlobalPaste);
    return () => document.removeEventListener("paste", onGlobalPaste);
  }, []);

  async function load() {
    const data = await getFurniture();
    setItems(data);
  }

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  function clearForm() {
    setForm(emptyForm);
    setFormImage(null);
    setFormTags([]);
    setFormColors([]);
    setTagInput("");
    if (formFileRef.current) formFileRef.current.value = "";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    try {
      const result = await createFurniture({
        ...form,
        price: Number(form.price),
        length: toSize(form.length), width: toSize(form.width), height: toSize(form.height),
        tags: formTags,
        colors: formColors,
      });
      if (formImage && result.id) await uploadImage(result.id, formImage);
    } finally {
      clearForm();
      setAddOpen(false);
      load();
    }
  }

  async function handleImport(e) {
    e.preventDefault();
    setImporting(true);
    setImportError("");
    try {
      const data = await scrapeUrl(importUrl);
      const result = await createFurniture({
        name: data.name, category: data.category, subcategory: data.subcategory || "",
        location: data.location, price: Number(data.price) || 0,
        length: data.length ?? null, width: data.width ?? null, height: data.height ?? null,
        tags: data.tags || [], colors: data.colors || [],
      });
      if (!result.id) throw new Error("Item konnte nicht angelegt werden");
      for (const img of (data.images || []).slice(0, 12)) {
        const uploaded = await uploadImageFromUrl(result.id, img.url);
        if (img.color && uploaded.id) await setImageColor(result.id, uploaded.id, img.color);
      }
      setImportUrl("");
      setImportOpen(false);
      setAddOpen(false);
      load();
    } catch (err) {
      setImportError(err.message);
    } finally {
      setImporting(false);
    }
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
    setEditForm({ name: item.name, category: item.category, subcategory: item.subcategory || "", location: item.location, price: item.price, used: !!item.used, length: item.length ?? "", width: item.width ?? "", height: item.height ?? "", tags: item.tags || [], colors: item.colors || [] });
    setEditTagInput("");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm({});
    setEditTagInput("");
  }

  async function saveEdit(id) {
    await updateFurniture(id, {
      ...editForm,
      price: Number(editForm.price),
      length: toSize(editForm.length), width: toSize(editForm.width), height: toSize(editForm.height),
    });
    setEditingId(null);
    setEditForm({});
    setEditTagInput("");
    load();
  }

  function pastedFile(e) {
    return [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/"))?.getAsFile() || null;
  }

  async function handlePastedImage(id, file) {
    setUploading(id);
    await uploadImage(id, file);
    setUploading(null);
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

  function clearPin(itemId) {
    setPinnedImages(prev => {
      if (!(itemId in prev)) return prev;
      const next = { ...prev };
      delete next[itemId];
      return next;
    });
  }

  function toggleColorFilter(itemId, color) {
    clearPin(itemId);
    setColorFilters(prev => ({ ...prev, [itemId]: prev[itemId] === color ? null : color }));
    setSliderIndices(prev => ({ ...prev, [itemId]: 0 }));
  }

  async function handleImageColor(furnitureId, image, color) {
    setPinnedImages(prev => ({ ...prev, [furnitureId]: image.id }));
    await setImageColor(furnitureId, image.id, image.color === color ? null : color);
    load();
  }

  function toggleFilter(tag) {
    setActiveTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    );
  }

  const priceStep = 1;
  const priceBound = Math.max(1, Math.ceil(Math.max(0, ...items.map(i => i.price || 0))));
  const priceLo = filters.priceMin ?? 0;
  const priceHi = filters.priceMax ?? priceBound;
  const priceFilterActive = filters.priceMin !== null || filters.priceMax !== null;
  const filterCategories = [...new Set(items.map(i => i.category).filter(Boolean))].sort();
  const filterSubcategories = [...new Set(items.filter(i => i.category === filters.category).map(i => i.subcategory).filter(Boolean))].sort();
  const filterFamilies = Object.keys(COLOR_FAMILIES).filter(f => items.some(i => (i.colors || []).some(c => colorFamily(c) === f)));
  const sizeFilterActive = Object.values(filters.size).some(([lo, hi]) => lo !== "" || hi !== "");
  const anyFilterActive = !!(filters.category || filters.subcategory || filters.families.length || priceFilterActive || sizeFilterActive || activeTags.length);

  function setSizeFilter(dim, i, value) {
    setFilters(f => ({ ...f, size: { ...f.size, [dim]: f.size[dim].map((v, j) => (j === i ? value : v)) } }));
  }

  function toggleFamily(family) {
    setFilters(f => ({ ...f, families: f.families.includes(family) ? f.families.filter(x => x !== family) : [...f.families, family] }));
  }

  const filteredItems = items.filter(item => {
    if (activeTags.length && !activeTags.every(t => (item.tags || []).includes(t))) return false;
    if (filters.category && item.category !== filters.category) return false;
    if (filters.subcategory && item.subcategory !== filters.subcategory) return false;
    if (filters.families.length && !(item.colors || []).some(c => filters.families.includes(colorFamily(c)))) return false;
    if (priceFilterActive && (item.price < priceLo || item.price > priceHi)) return false;
    for (const dim of ["length", "width", "height"]) {
      const [lo, hi] = filters.size[dim];
      if (lo === "" && hi === "") continue;
      const v = item[dim];
      if (v == null || (lo !== "" && v < Number(lo)) || (hi !== "" && v > Number(hi))) return false;
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      const matches =
        item.name?.toLowerCase().includes(q) ||
        item.category?.toLowerCase().includes(q) ||
        item.subcategory?.toLowerCase().includes(q) ||
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
    clearPin(itemId);
    const current = sliderIdx(itemId, length);
    setSliderIndices(prev => ({ ...prev, [itemId]: (current + delta + length) % length }));
  }

  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />;

  return (
    <div style={{ minHeight: "100svh", background: "var(--bg)" }}>
      <input ref={fileInputRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handleFileChange} />

      {/* HEADER */}
      <header style={{ padding: narrow ? "24px 16px 16px" : "48px 32px 24px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
        <div style={{ textAlign: "left" }}>
          <h1 style={{ margin: 0 }}>Julias Interior Store</h1>
          <p style={{ marginTop: 14, color: "var(--text)", fontSize: 15 }}>
            {items.length} {items.length === 1 ? "item" : "items"} gespeichert
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flex: "1 1 320px", justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button
            onClick={() => setAddOpen(o => !o)}
            style={{ fontSize: 14, fontWeight: 600, background: addOpen ? "transparent" : "var(--accent)", color: addOpen ? "var(--accent)" : "#fff", border: "1px solid var(--accent)", borderRadius: 8, padding: "8px 16px", cursor: "pointer", whiteSpace: "nowrap" }}
          >
            {addOpen ? "Schließen" : "+ Item hinzufügen"}
          </button>
          <div style={{ position: "relative", flex: "1 1 160px", minWidth: 140, maxWidth: 260 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text)", opacity: 0.5, pointerEvents: "none" }}>
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              placeholder="Suchen…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ ...field, paddingLeft: 36, fontSize: 14 }}
            />
          </div>
          <button
            onClick={() => { localStorage.removeItem("auth_token"); setAuthed(false); }}
            style={{ fontSize: 13, background: "transparent", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 14px", cursor: "pointer", whiteSpace: "nowrap" }}
          >
            Abmelden
          </button>
          <div ref={settingsRef} style={{ position: "relative" }}>
            <button
              type="button"
              aria-label="Einstellungen"
              aria-haspopup="menu"
              aria-expanded={settingsOpen}
              title="Einstellungen"
              onClick={() => setSettingsOpen(o => !o)}
              style={{ display: "flex", alignItems: "center", justifyContent: "center", width: touch ? 40 : 34, height: touch ? 40 : 34, background: settingsOpen ? "var(--accent-bg)" : "transparent", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer", padding: 0 }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
            {settingsOpen && (
              <div
                role="menu"
                style={{ position: "absolute", right: 0, top: "calc(100% + 8px)", zIndex: 30, minWidth: 190, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--shadow)", padding: 8 }}
              >
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px", padding: "6px 10px" }}>Darstellung</div>
                {[
                  { value: "light", label: "Hell" },
                  { value: "dark", label: "Dunkel" },
                  { value: "system", label: "System" },
                ].map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    role="menuitemradio"
                    aria-checked={theme === value}
                    onClick={() => { setTheme(value); setSettingsOpen(false); }}
                    style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", textAlign: "left", fontSize: 14, padding: touch ? "12px 10px" : "8px 10px", background: theme === value ? "var(--accent-bg)" : "transparent", color: theme === value ? "var(--accent)" : "var(--text-h)", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: theme === value ? 600 : 400 }}
                  >
                    {label}
                    {theme === value && <span aria-hidden="true">✓</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      <main style={{ padding: narrow ? "16px" : "32px", maxWidth: 1320, margin: "0 auto", width: "100%", boxSizing: "border-box", textAlign: "left" }}>

        {/* FORM */}
        {addOpen && (
        <div style={{ background: "var(--accent-bg)", border: "1px solid var(--accent-border)", borderRadius: 16, padding: narrow ? 16 : 24, marginBottom: narrow ? 24 : 40 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
            <h2 style={{ margin: 0 }}>Interior Item hinzufügen</h2>
            <button
              type="button"
              onClick={() => { setImportOpen(o => !o); setImportError(""); }}
              style={{ fontSize: 13, fontWeight: 600, background: "var(--bg)", color: "var(--accent)", border: "1px solid var(--accent-border)", borderRadius: 8, padding: "6px 14px", cursor: "pointer" }}
            >
              Von Website importieren
            </button>
          </div>

          {importOpen && (
            <form onSubmit={handleImport} style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
              <input
                type="text"
                placeholder="https://www.ikea.com/…"
                value={importUrl}
                onChange={e => setImportUrl(e.target.value)}
                autoFocus
                style={{ ...field, flex: 1, minWidth: 200, fontSize: 14 }}
              />
              <button
                type="submit"
                disabled={importing || !importUrl.trim()}
                style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 10, padding: "10px 20px", fontSize: 14, fontWeight: 600, cursor: importing ? "default" : "pointer", opacity: importing || !importUrl.trim() ? 0.6 : 1, whiteSpace: "nowrap" }}
              >
                {importing ? "Lädt…" : "Importieren"}
              </button>
              {importError && <p style={{ width: "100%", margin: 0, fontSize: 13, color: "#ef4444" }}>{importError}</p>}
            </form>
          )}
          <form onSubmit={handleSubmit} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
            <input name="name"     placeholder="Name"       value={form.name}     onChange={handleChange} style={field} />
            <CategorySelects category={form.category} subcategory={form.subcategory} onChange={(category, subcategory) => setForm({ ...form, category, subcategory })} style={field} />
            <input name="location" placeholder="Location"   value={form.location} onChange={handleChange} style={field} />
            <input name="price"    placeholder="Preis (€)"  value={form.price}    onChange={handleChange} style={field} type="number" min="0" step="0.01" />
            {sizeFields.map(({ key, label }) => (
              <input key={key} name={key} placeholder={label} value={form[key]} onChange={handleChange} style={field} type="number" min="0" step="0.1" />
            ))}

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

            <label style={{ ...field, display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={form.used} onChange={e => setForm({ ...form, used: e.target.checked })} />
              Schon verwendet
            </label>

            {/* COLOR PALETTE */}
            <div style={{ gridColumn: "1 / -1", border: "1px solid var(--border)", borderRadius: 10, padding: "6px 10px", background: "var(--bg)" }}>
              <ColorPalette colors={formColors} onChange={setFormColors} />
            </div>

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
        )}

        <div style={{ display: "flex", flexWrap: "wrap", gap: narrow ? 16 : 32, alignItems: "flex-start" }}>

        {narrow && (
          <button
            type="button"
            onClick={() => setFilterOpen(o => !o)}
            style={{ flex: "1 1 100%", fontSize: 14, fontWeight: 600, background: "var(--bg)", color: anyFilterActive ? "var(--accent)" : "var(--text-h)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 16px", cursor: "pointer", textAlign: "left" }}
          >
            {filterOpen ? "Filter ausblenden" : `Filter anzeigen${anyFilterActive ? " (aktiv)" : ""}`}
          </button>
        )}

        {/* FILTER SIDEBAR */}
        {(!narrow || filterOpen) && (
        <aside ref={asideRef} style={{ flex: narrow ? "1 1 100%" : "0 0 240px", boxSizing: "border-box", border: "1px solid var(--border)", borderRadius: 16, padding: 16, display: "flex", flexDirection: "column", gap: 20, position: narrow || asideTall ? "static" : "sticky", top: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0, fontSize: 16, color: "var(--text-h)" }}>Filter</h3>
            {anyFilterActive && (
              <button
                onClick={() => { setFilters(emptyFilters); setActiveTags([]); }}
                style={{ fontSize: 12, color: "var(--text)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}
              >
                Zurücksetzen
              </button>
            )}
          </div>

          <FilterSection title="Kategorie">
            <select value={filters.category} onChange={e => setFilters({ ...filters, category: e.target.value, subcategory: "" })} style={{ ...field, padding: "8px 12px", fontSize: 14 }}>
              <option value="">Alle Kategorien</option>
              {filterCategories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select value={filters.subcategory} onChange={e => setFilters({ ...filters, subcategory: e.target.value })} disabled={!filters.category} style={{ ...field, padding: "8px 12px", fontSize: 14 }}>
              <option value="">Alle Unterkategorien</option>
              {filterSubcategories.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </FilterSection>

          <FilterSection title="Preis">
            <div style={{ fontSize: 13, color: "var(--text-h)" }}>€{priceLo} – €{priceHi}</div>
            <DualRange
              min={0}
              max={priceBound}
              step={priceStep}
              low={priceLo}
              high={priceHi}
              onChange={(lo, hi) => setFilters({ ...filters, priceMin: lo <= 0 ? null : lo, priceMax: hi >= priceBound ? null : hi })}
            />
          </FilterSection>

          <FilterSection title="Größe (cm)">
            {sizeFields.map(({ key, label }) => (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 12, color: "var(--text)", width: 52 }}>{label.split(" ")[0]}</span>
                {[0, 1].map(i => (
                  <input
                    key={i}
                    type="number" min="0" step="0.1"
                    placeholder={i === 0 ? "min" : "max"}
                    value={filters.size[key][i]}
                    onChange={e => setSizeFilter(key, i, e.target.value)}
                    style={{ ...field, padding: "6px 8px", fontSize: 13, width: "100%", minWidth: 0 }}
                  />
                ))}
              </div>
            ))}
          </FilterSection>

          {filterFamilies.length > 0 && (
            <FilterSection title="Farbe">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {filterFamilies.map(f => {
                  const on = filters.families.includes(f);
                  return (
                    <button
                      key={f}
                      type="button"
                      title={f}
                      onClick={() => toggleFamily(f)}
                      style={{ width: touch ? 34 : 26, height: touch ? 34 : 26, borderRadius: "50%", background: COLOR_FAMILIES[f], padding: 0, cursor: "pointer", border: on ? "2px solid var(--accent)" : "1px solid var(--border)", boxShadow: on ? "0 0 0 2px var(--accent-border)" : "none" }}
                    />
                  );
                })}
              </div>
            </FilterSection>
          )}
          {allTags.length > 0 && (
            <FilterSection title="Tags">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {allTags.map(tag => {
                  const active = activeTags.includes(tag);
                  return (
                    <button
                      key={tag}
                      type="button"
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
              </div>
            </FilterSection>
          )}
        </aside>
        )}

        <div style={{ flex: narrow ? "1 1 100%" : "1 1 560px", minWidth: 0 }}>

        {/* EMPTY STATE */}
        {items.length === 0 && (
          <div style={{ textAlign: "center", padding: "80px 0", color: "var(--text)" }}>
            <div style={{ fontSize: 52, marginBottom: 16 }}>🪑</div>
            <p style={{ fontSize: 16 }}>Noch keine Items hinzugefügt. Füge oben dein erstes Interior Item hinzu.</p>
          </div>
        )}

        {items.length > 0 && filteredItems.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text)" }}>
            <p style={{ fontSize: 16 }}>Keine Items für die gewählten Filter gefunden.</p>
            <button onClick={() => { setActiveTags([]); setFilters(emptyFilters); }} style={{ marginTop: 12, fontSize: 13, color: "var(--accent)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
              Filter zurücksetzen
            </button>
          </div>
        )}

        {/* GRID */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 24 }}>
          {filteredItems.map((item) => {
            const activeColor = (item.colors || []).includes(colorFilters[item.id]) ? colorFilters[item.id] : null;
            const images = (item.images || []).filter(img => !activeColor || img.color === activeColor || img.id === pinnedImages[item.id]);
            const idx = sliderIdx(item.id, images.length);

            return (
              <div
                key={item.id}
                data-card-id={item.id}
                tabIndex={0}
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: 16,
                  overflow: "hidden",
                  boxShadow: "var(--shadow)",
                  outline: "none",
                }}
              >
                {/* IMAGE SLIDER */}
                <div
                  style={{ position: "relative", aspectRatio: "1 / 1", background: images.length > 0 ? "#fff" : "var(--code-bg)", overflow: "hidden" }}
                >
                  {images.length > 0 ? (
                    <>
                      <img
                        src={imageUrl(images[idx].filename)}
                        alt={item.name}
                        style={{ width: "100%", height: "100%", objectFit: "contain" }}
                      />

                      {/* Prev / Next */}
                      {images.length > 1 && (
                        <>
                          <button
                            onClick={() => navigate(item.id, -1, images.length)}
                            style={{ ...overlayBtn, position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", width: touch ? 38 : 28, height: touch ? 38 : 28, fontSize: 16 }}
                          >‹</button>
                          <button
                            onClick={() => navigate(item.id, 1, images.length)}
                            style={{ ...overlayBtn, position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", width: touch ? 38 : 28, height: touch ? 38 : 28, fontSize: 16 }}
                          >›</button>
                        </>
                      )}

                      {/* Delete current image */}
                      <button
                        onClick={() => handleDeleteImage(item.id, images[idx].id, idx, images.length)}
                        style={{ ...overlayBtn, position: "absolute", top: 8, right: 8, width: touch ? 34 : 24, height: touch ? 34 : 24, fontSize: 14 }}
                      >×</button>

                      {/* Add image */}
                      <button
                        onClick={() => handleUploadClick(item.id)}
                        style={{ ...overlayBtn, position: "absolute", top: 8, left: 8, width: touch ? 34 : 24, height: touch ? 34 : 24, fontSize: 16 }}
                        title="Bild hinzufügen"
                      >+</button>

                      {/* Assign color to current image */}
                      {(item.colors || []).length > 0 && (
                        <div style={{ position: "absolute", bottom: 6, left: 8, display: "flex", gap: 4 }}>
                          {item.colors.map(c => (
                            <button
                              key={c}
                              type="button"
                              title={images[idx].color === c ? "Farbzuordnung entfernen" : `Bild der Farbe ${c} zuordnen`}
                              onClick={() => handleImageColor(item.id, images[idx], c)}
                              style={{ width: touch ? 24 : 16, height: touch ? 24 : 16, borderRadius: "50%", background: c, padding: 0, cursor: "pointer", border: images[idx].color === c ? "2px solid #fff" : "1px solid rgba(255,255,255,0.6)", boxShadow: "0 0 0 1px rgba(0,0,0,0.35)" }}
                            />
                          ))}
                        </div>
                      )}

                      {/* Dots */}
                      {images.length > 1 && (
                        <div style={{ position: "absolute", bottom: touch ? 0 : 8, left: 0, right: 0, display: "flex", justifyContent: "center", gap: touch ? 0 : 5 }}>
                          {images.map((_, i) => (
                            <div
                              key={i}
                              onClick={() => { clearPin(item.id); setSliderIndices(prev => ({ ...prev, [item.id]: i })); }}
                              style={{ padding: touch ? "12px 7px" : 0, cursor: "pointer" }}
                            >
                              <div style={{ width: 6, height: 6, borderRadius: "50%", background: i === idx ? "#fff" : "rgba(255,255,255,0.45)", transition: "background 0.15s" }} />
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  ) : activeColor ? (
                    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text)", fontSize: 13 }}>
                      Keine Bilder in dieser Farbe
                    </div>
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
                          { key: "location", label: "Ort" },
                          { key: "price", label: "Preis (€)", type: "number", step: "0.01" },
                          ...sizeFields.map(f => ({ ...f, type: "number", step: "0.1" })),
                        ].map(({ key, label, type = "text", step }) => (
                          <label key={key} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px" }}>{label}</span>
                            <input
                              type={type}
                              step={step}
                              value={editForm[key]}
                              onChange={e => setEditForm({ ...editForm, [key]: e.target.value })}
                              style={{ ...field, padding: "8px 12px", fontSize: 14 }}
                            />
                          </label>
                        ))}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
                        <CategorySelects
                          labeled
                          category={editForm.category}
                          subcategory={editForm.subcategory}
                          onChange={(category, subcategory) => setEditForm({ ...editForm, category, subcategory })}
                          style={{ ...field, padding: "8px 12px", fontSize: 14 }}
                        />
                      </div>
                      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, color: "var(--text-h)", marginBottom: 12, cursor: "pointer" }}>
                        <input type="checkbox" checked={!!editForm.used} onChange={e => setEditForm({ ...editForm, used: e.target.checked })} />
                        Schon verwendet
                      </label>
                      <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 12 }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", textTransform: "uppercase", letterSpacing: "0.6px" }}>Farben</span>
                        <ColorPalette colors={editForm.colors || []} onChange={colors => setEditForm({ ...editForm, colors })} />
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
                        <button
                          type="button"
                          title="Klicken zum Umschalten"
                          onClick={async () => { await updateFurniture(item.id, { used: !item.used }); load(); }}
                          style={{
                            fontSize: 12, fontWeight: 600, borderRadius: 20, padding: "2px 10px", cursor: "pointer",
                            border: item.used ? "1px solid #16a34a" : "1px solid var(--border)",
                            background: item.used ? "#16a34a" : "transparent",
                            color: item.used ? "#fff" : "var(--text)",
                          }}
                        >
                          {item.used ? "✓ Verwendet" : "Nicht verwendet"}
                        </button>
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
                        <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--text)" }}>
                          {item.category}{item.subcategory ? ` › ${item.subcategory}` : ""}
                        </p>
                      )}
                      {!item.category && <div style={{ marginBottom: 14 }} />}
                      {(item.colors || []).length > 0 && (
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "-8px 0 12px" }}>
                          {item.colors.map(c => (
                            <button
                              key={c}
                              type="button"
                              title={activeColor === c ? "Filter aufheben" : `Bilder in ${c} zeigen`}
                              onClick={() => toggleColorFilter(item.id, c)}
                              style={{ width: touch ? 28 : 20, height: touch ? 28 : 20, borderRadius: "50%", background: c, padding: 0, cursor: "pointer", border: activeColor === c ? "2px solid var(--accent)" : "1px solid var(--border)", boxShadow: activeColor === c ? "0 0 0 2px var(--accent-border)" : "none" }}
                            />
                          ))}
                        </div>
                      )}
                      {formatSize(item) && (
                        <p style={{ margin: "-8px 0 14px", fontSize: 13, color: "var(--text)" }}>Größe: {formatSize(item)}</p>
                      )}

                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
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

        </div>
        </div>
      </main>
    </div>
  );
}
