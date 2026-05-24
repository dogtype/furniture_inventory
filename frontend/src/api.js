const API_URL = "http://89.244.85.149:1919";

function getToken() {
  return localStorage.getItem("auth_token");
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` };
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    localStorage.removeItem("auth_token");
    window.dispatchEvent(new Event("auth:logout"));
  }
  return response;
}

export async function login(password) {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) throw new Error("Falsches Passwort");
  const { token } = await response.json();
  localStorage.setItem("auth_token", token);
  return token;
}

export async function scrapeUrl(url) {
  const response = await request(`${API_URL}/scrape`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || "Fehler beim Importieren");
  }
  return response.json();
}

export async function getFurniture() {
  const response = await request(`${API_URL}/furniture`, {
    headers: authHeaders(),
  });
  return response.json();
}

export async function createFurniture(item) {
  const response = await request(`${API_URL}/furniture`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(item),
  });
  return response.json();
}

export async function deleteFurniture(id) {
  await request(`${API_URL}/furniture/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function updateFurniture(id, fields) {
  const response = await request(`${API_URL}/furniture/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(fields),
  });
  return response.json();
}

export async function uploadImage(id, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await request(`${API_URL}/furniture/${id}/image`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  return response.json();
}

export async function deleteImage(furnitureId, imageId) {
  await request(`${API_URL}/furniture/${furnitureId}/image/${imageId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export const imageUrl = (path) => `${API_URL}/uploads/${path}`;
