const API_URL = "http://127.0.0.1:8000";

export async function getFurniture() {
  const response = await fetch(`${API_URL}/furniture`);
  return response.json();
}

export async function createFurniture(item) {
  const response = await fetch(`${API_URL}/furniture`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
  return response.json();
}

export async function deleteFurniture(id) {
  await fetch(`${API_URL}/furniture/${id}`, { method: "DELETE" });
}

export async function updateFurniture(id, fields) {
  const response = await fetch(`${API_URL}/furniture/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  return response.json();
}

export async function uploadImage(id, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_URL}/furniture/${id}/image`, {
    method: "POST",
    body: formData,
  });
  return response.json();
}

export async function deleteImage(furnitureId, imageId) {
  await fetch(`${API_URL}/furniture/${furnitureId}/image/${imageId}`, { method: "DELETE" });
}

export const imageUrl = (path) => `${API_URL}/uploads/${path}`;
