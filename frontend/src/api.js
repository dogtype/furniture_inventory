const API_URL = "http://127.0.0.1:8000";

export async function getFurniture() {
  const response = await fetch(`${API_URL}/furniture`);
  return response.json();
}

export async function createFurniture(item) {
  const response = await fetch(`${API_URL}/furniture`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(item),
  });

  return response.json();
}

export async function deleteFurniture(id) {
  await fetch(`${API_URL}/furniture/${id}`, {
    method: "DELETE",
  });
}